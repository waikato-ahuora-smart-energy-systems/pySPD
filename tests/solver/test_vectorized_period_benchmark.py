import hashlib
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from types import MappingProxyType

import pyomo.environ as pyo
import pytest

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.architecture import BuiltModel, Formulation, ModelArtifacts, ModelAssembler
from pyspd.orchestration.solver import _updated_case
from pyspd.reserve import RESERVE_FORMULATION_ID, reserve_formulation
from tools.benchmark_vectorized_periods import (
    CaseMergeError,
    _cross_period_constraints,
    _merge_dataclass_instances,
    _parity_summary,
    _take_distinct_trading_periods,
)


@dataclass(frozen=True)
class _Nested:
    members: frozenset[tuple[str, str]]
    values: MappingProxyType
    policy: float = 1.0


@dataclass(frozen=True)
class _Case:
    case_id: str
    periods: frozenset[tuple[str, str]]
    nested: _Nested
    preprocessing_signature: str | None = None


def _case(case_id: str, period: str, value: float) -> _Case:
    key = (case_id, period)
    return _Case(
        case_id,
        frozenset({key}),
        _Nested(frozenset({key}), MappingProxyType({key: value})),
        f"signature-{case_id}",
    )


def test_recursive_case_merge_unions_disjoint_period_data() -> None:
    merged = _merge_dataclass_instances(
        (_case("c1", "p1", 1.0), _case("c2", "p2", 2.0))
    )

    assert merged.case_id == "batch[c1,c2]"
    assert merged.periods == frozenset({("c1", "p1"), ("c2", "p2")})
    assert dict(merged.nested.values) == {("c1", "p1"): 1.0, ("c2", "p2"): 2.0}
    assert merged.preprocessing_signature not in {"signature-c1", "signature-c2"}


def test_recursive_case_merge_fails_on_conflicting_mapping_keys() -> None:
    left = _case("c1", "p1", 1.0)
    right = _Case(
        "c2",
        frozenset({("c2", "p2")}),
        _Nested(
            frozenset({("c2", "p2")}),
            MappingProxyType({("c1", "p1"): 9.0}),
        ),
        "signature-c2",
    )

    with pytest.raises(CaseMergeError, match="conflicting mapping key"):
        _merge_dataclass_instances((left, right))


def test_parity_summary_reports_objective_and_variable_differences() -> None:
    summary = _parity_summary(
        separate_objective=30.0,
        vectorized_objective=30.00000001,
        separate_values={"generation": {("c1",): 10.0, ("c2",): 20.0}},
        vectorized_values={"generation": {("c1",): 10.0, ("c2",): 20.00000002}},
        tolerance=1e-6,
    )

    assert summary["passed"] is True
    assert summary["objective_absolute_difference"] == pytest.approx(1e-8)
    assert summary["maximum_variable_absolute_difference"] == pytest.approx(2e-8)


def test_distinct_period_selection_skips_additional_cases_in_same_period() -> None:
    def prepared(period: str, case_id: str):
        specification = type(
            "Specification", (), {"trading_period": period, "case_id": case_id}
        )()
        return type("Prepared", (), {"specification": specification})()

    selected = _take_distinct_trading_periods(
        iter(
            (
                prepared("TP1", "c1"),
                prepared("TP1", "c2"),
                prepared("TP2", "c3"),
                prepared("TP3", "c4"),
            )
        ),
        2,
    )

    assert [item.specification.case_id for item in selected] == ["c1", "c3"]


def test_cross_period_constraint_audit_identifies_only_mixed_rows() -> None:
    model = pyo.ConcreteModel()
    periods = frozenset({("c1", "d1"), ("c2", "d2")})
    model.periods = pyo.Set(dimen=2, initialize=sorted(periods))
    model.x = pyo.Var(model.periods)
    model.local = pyo.Constraint(expr=model.x["c1", "d1"] >= 0.0)
    model.mixed = pyo.Constraint(expr=model.x["c1", "d1"] + model.x["c2", "d2"] >= 0.0)
    formulation = Formulation("test", (), (), object, object, object, object)
    built = BuiltModel(
        model,
        ModelArtifacts(),
        formulation,
        type("Case", (), {"periods": periods})(),
        (),
        "signature",
    )

    assert _cross_period_constraints(built) == [
        {"constraint": "mixed", "periods": [["c1", "d1"], ["c2", "d2"]]}
    ]


@pytest.mark.oracle
@pytest.mark.skipif(find_spec("gamspy") is None, reason="requires the GDX extra")
def test_real_vectorized_matrix_has_no_physical_cross_period_rows() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "tests/fixtures/cplex_reference/2023/20230922/input/Pricing_20230922.gdx"
    )
    system = root / ".venv/lib/python3.13/site-packages/gamspy_base"
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=source,
        output_directory=root / ".pytest-vectorized-unused",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        gams_system_directory=system,
    )
    prepared = _take_distinct_trading_periods(
        PyspdApplication().iter_prepared_cases(configuration), 2
    )
    merged = _merge_dataclass_instances(tuple(_updated_case(item) for item in prepared))
    built = ModelAssembler().assemble(reserve_formulation(), merged)

    assert [item["constraint"] for item in _cross_period_constraints(built)] == [
        "Economics.TotalViolationCostDefinition"
    ]
