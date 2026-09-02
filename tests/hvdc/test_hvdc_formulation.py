from __future__ import annotations

from dataclasses import replace

import pyomo.environ as pyo
import pytest
from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.architecture import ModelAssembler
from pyspd.hvdc import (
    HvdcDiagnosticExporter,
    HvdcPricingEngine,
    HvdcResultSchema,
    HvdcSolvePolicy,
    IndependentHvdcValidator,
    active_discrete_count,
    audit_pricing_model,
    detect_nonphysical_hvdc,
    hvdc_formulation,
    portable_and_native_sos_curves_equivalent,
    validate_fixed_mip_price_finite_difference,
)
from pyspd.hvdc.diagnostics import DiagnosticCapabilityError
from pyspd.hvdc.formulation import (
    WarmStartSnapshot,
    _canonical_sos_value,
    _fix_continuous_state,
    pricing_model_belongs_to_request,
)
from pyspd.solver import HighsBackend, NativeScipBackend
from tests.hvdc.conftest import make_hvdc_case


def build(case):
    return ModelAssembler().assemble(hvdc_formulation(), case)


def solve(case):
    built = build(case)
    outcome = HvdcSolvePolicy().solve(built)
    prices = HvdcPricingEngine().price(built, outcome)
    report = IndependentHvdcValidator().validate(outcome, tolerance=1e-6)
    assert report.passed, report.residuals
    return built, outcome, prices


def test_primary_scip_uses_corpus_stable_feasibility_tolerance(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def capture(_backend, _model, configuration, *, warm_start_discrete=False):
        captured.update(configuration.options)
        captured["warm_start_discrete"] = warm_start_discrete
        return sentinel

    monkeypatch.setattr(NativeScipBackend, "solve_mip", capture)

    assert HvdcSolvePolicy._solve_scip(build(make_hvdc_case(enforce=True))) is sentinel
    assert captured["numerics/feastol"] == 1e-6
    assert captured["warm_start_discrete"] is False


def test_fixed_rmip_uses_gams_highs_tolerances(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def capture(_backend, _model, configuration, *, warm_start=False):
        captured.update(configuration.options)
        captured["warm_start"] = warm_start
        return sentinel

    monkeypatch.setattr("pyspd.hvdc.formulation.HighsBackend.solve", capture)

    assert HvdcSolvePolicy._solve_highs(build(make_hvdc_case())) is sentinel
    assert captured["primal_feasibility_tolerance"] == 1e-9
    assert captured["dual_feasibility_tolerance"] == 1e-9
    assert captured["primal_residual_tolerance"] == 1e-9
    assert captured["dual_residual_tolerance"] == 1e-9
    assert captured["warm_start"] is False


def test_warm_start_remaps_period_identity_and_rejects_incompatible_values() -> None:
    previous = pyo.ConcreteModel()
    previous.dispatch = pyo.Var(
        [("CASE-1", "TIME-1", "GEN")], domain=pyo.Binary, initialize=1.0
    )
    previous.flow = pyo.Var(
        [("CASE-1", "TIME-1", "HVDC")], bounds=(-10.0, 10.0), initialize=4.0
    )
    previous.fixed = pyo.Var(
        [("CASE-1", "TIME-1", "FIXED")], domain=pyo.Binary, initialize=1.0
    )
    snapshot = WarmStartSnapshot.capture(previous)
    discrete_snapshot = WarmStartSnapshot.capture(previous, discrete_only=True)
    assert len(discrete_snapshot.values) == 2

    candidate = pyo.ConcreteModel()
    candidate.dispatch = pyo.Var(
        [("CASE-2", "TIME-2", "GEN")], domain=pyo.Binary
    )
    candidate.flow = pyo.Var(
        [("CASE-2", "TIME-2", "HVDC")], bounds=(-2.0, 2.0)
    )
    candidate.fixed = pyo.Var(
        [("CASE-2", "TIME-2", "FIXED")], domain=pyo.Binary, initialize=0.0
    )
    candidate.fixed["CASE-2", "TIME-2", "FIXED"].fix()

    assert snapshot.apply(candidate, discrete_only=True) == 1
    assert candidate.dispatch["CASE-2", "TIME-2", "GEN"].value == 1.0
    assert candidate.flow["CASE-2", "TIME-2", "HVDC"].value is None
    assert candidate.fixed["CASE-2", "TIME-2", "FIXED"].value == 0.0
    assert snapshot.apply(candidate) == 1
    assert candidate.flow["CASE-2", "TIME-2", "HVDC"].value is None


def test_policy_records_cross_period_and_same_period_warm_starts(monkeypatch) -> None:
    observed: list[bool] = []
    original = HighsBackend.solve

    def capture(
        self,
        model,
        configuration,
        *,
        load_solution=True,
        accept_nonoptimal=False,
        warm_start=False,
    ):
        observed.append(warm_start)
        return original(
            self,
            model,
            configuration,
            load_solution=load_solution,
            accept_nonoptimal=accept_nonoptimal,
            warm_start=False,
        )

    monkeypatch.setattr(HighsBackend, "solve", capture)
    first = HvdcSolvePolicy(
        warm_start_primary=True,
        warm_start_pricing=True,
    ).solve(
        build(make_hvdc_case(enforce=True))
    )
    second = HvdcSolvePolicy(
        warm_start_primary=True,
        warm_start_pricing=True,
        previous_period_start=first.next_warm_start,
    ).solve(build(make_hvdc_case(enforce=True)))

    assert first.warm_start.prior_value_count == 0
    assert first.warm_start.pricing_value_count > 0
    assert second.warm_start.prior_value_count > 0
    assert second.warm_start.primary_discrete_count > 0
    assert second.warm_start.pricing_value_count > 0
    assert True in observed
    assert second.primary_snapshot.objective == pytest.approx(
        first.primary_snapshot.objective
    )


def test_fixed_rmip_preserves_sos_support_without_fixing_active_weights() -> None:
    model = pyo.ConcreteModel()
    model.members = pyo.Var(("inactive", "left", "right"), bounds=(0.0, 1.0))

    _fix_continuous_state(
        model,
        {
            "members[inactive]": 0.0,
            "members[left]": 0.25,
            "members[right]": 0.75,
        },
    )

    assert model.members["inactive"].fixed
    assert pyo.value(model.members["inactive"]) == 0.0
    assert not model.members["left"].fixed
    assert not model.members["right"].fixed


def test_sos_support_uses_the_governed_solvefinal_threshold() -> None:
    assert _canonical_sos_value(1e-7) == 0.0
    assert _canonical_sos_value(-1e-7) == 0.0
    assert _canonical_sos_value(1.01e-7) == pytest.approx(1.01e-7)


def test_hvdc_forward_flow_loss_and_bus_prices() -> None:
    _built, outcome, prices = solve(make_hvdc_case())
    primary = outcome.primary_model
    flow = pyo.value(primary.artifacts["hvdc_flow"]["C1", "T1", "H1"])
    loss = pyo.value(primary.artifacts["hvdc_loss"]["C1", "T1", "H1"])
    assert flow == pytest.approx(41.6666666667)
    assert loss == pytest.approx(1.6666666667)
    assert prices.bus[("C1", "T1", "B2")] > prices.bus[("C1", "T1", "B1")]


def test_hvdc_build_treats_missing_sparse_node_bus_allocation_as_zero() -> None:
    case = make_hvdc_case()
    assert case.network is not None
    missing = ("C1", "T1", "N1", "B1")
    case = replace(
        case,
        network=replace(
            case.network,
            node_bus_allocation={
                key: value
                for key, value in case.network.node_bus_allocation.items()
                if key != missing
            },
        ),
    )

    built = build(case)
    balance = built.artifacts["energy_balance"]["C1", "T1", "B1"]
    representation = generate_standard_repn(balance.body)

    assert representation.nonlinear_expr is None


def test_hvdc_reversal_uses_reverse_link_orientation() -> None:
    _built, outcome, _prices = solve(make_hvdc_case(generation_bus="B2", load_bus="B1"))
    assert pyo.value(
        outcome.primary_model.artifacts["hvdc_flow"]["C1", "T1", "H1"]
    ) == pytest.approx(41.6666666667)


def test_hvdc_fixed_loss_is_split_across_link_ends() -> None:
    _built, outcome, _prices = solve(make_hvdc_case(fixed_loss=2.0))
    primary = outcome.primary_model
    flow = pyo.value(primary.artifacts["hvdc_flow"]["C1", "T1", "H1"])
    generation = pyo.value(primary.artifacts["generation"]["C1", "T1", "GEN"])
    assert flow == pytest.approx(42.7083333333)
    assert generation == pytest.approx(flow + 1.0)


def test_hvdc_piecewise_boundary_selects_exact_breakpoint() -> None:
    _built, outcome, _prices = solve(make_hvdc_case(load=48.0))
    lambdas = outcome.primary_model.artifacts["hvdc_lambda"]
    assert pyo.value(lambdas["C1", "T1", "H1", "bp2"]) == pytest.approx(1.0)


def test_zero_flow_and_pole_outage_are_bounded_without_stale_flow() -> None:
    _built, zero, _prices = solve(make_hvdc_case(load=0.0))
    assert pyo.value(
        zero.primary_model.artifacts["hvdc_flow"]["C1", "T1", "H1"]
    ) == pytest.approx(0.0)
    _built, outage, _prices = solve(make_hvdc_case(capacity=0.0))
    assert pyo.value(
        outage.primary_model.artifacts["hvdc_flow"]["C1", "T1", "H1"]
    ) == pytest.approx(0.0)


def test_nonadjacent_lambda_detection_triggers_real_scip_then_fixed_highs() -> None:
    case = make_hvdc_case(
        load=30.0,
        breakpoint_loss=(0.0, 20.0, 25.0),
    )
    built = build(case)
    outcome = HvdcSolvePolicy().solve(built)
    assert any(
        issue.startswith("nonadjacent-lambda") for issue in outcome.detected_issues
    )
    assert outcome.primary_mip is not None
    assert outcome.primary_mip.solve.backend == "native-scip"
    assert outcome.primary_mip.solve.status.value == "optimal"
    assert outcome.pricing_lp.backend == "highs"
    assert active_discrete_count(outcome.pricing_model.model) == 0
    assert outcome.fixed_discrete
    assert outcome.primary_snapshot.objective == pytest.approx(
        outcome.pricing_snapshot.objective
    )
    assert IndependentHvdcValidator().validate(outcome, tolerance=1e-6).passed


def test_explicit_portable_sos_mip_uses_scip_and_immutable_pricing_snapshot() -> None:
    case = make_hvdc_case(enforce=True)
    original = build(case)
    outcome = HvdcSolvePolicy().solve(original)
    assert outcome.primary_mip is not None
    assert outcome.primary_model is original
    assert outcome.pricing_model is not original
    assert outcome.primary_snapshot.variables is not outcome.pricing_snapshot.variables
    assert outcome.primary_mip.discrete_variable_count > 0
    results = HvdcResultSchema().collect(original, outcome)
    assert results.primary_objective == pytest.approx(results.pricing_objective)
    audit = audit_pricing_model(outcome)
    assert audit.passed
    assert audit.primary_discrete_count == len(outcome.fixed_discrete)
    assert audit.pricing_discrete_count == 0
    assert audit.primary_state_sha256 != audit.pricing_state_sha256


def test_exact_breakpoint_alternative_interval_optimum_is_safely_fixed() -> None:
    _built, outcome, _prices = solve(make_hvdc_case(load=48.0, enforce=True))
    interval_fixings = {
        name: value
        for name, value in outcome.fixed_discrete.items()
        if "SOSIntervalBinary" in name
    }
    assert sum(interval_fixings.values()) == 1.0
    assert outcome.primary_snapshot.objective == pytest.approx(
        outcome.pricing_snapshot.objective
    )


def test_fixed_mip_price_matches_independent_load_perturbation() -> None:
    check = validate_fixed_mip_price_finite_difference(
        make_hvdc_case(enforce=True),
        ("C1", "T1", "N2"),
        perturbation_mw=1e-4,
        tolerance=1e-3,
    )
    assert check.passed, check


def test_discrete_demand_is_fixed_before_rmip_pricing() -> None:
    case = make_hvdc_case(load=0.0, bid_limit=40.0)
    _built, outcome, _prices = solve(case)
    binary_name = next(
        name for name in outcome.fixed_discrete if "PurchaseBlockBinary" in name
    )
    assert outcome.fixed_discrete[binary_name] == 1.0
    assert pyo.value(
        outcome.primary_model.artifacts["purchase_block"]["C1", "T1", "BID", "1"]
    ) == pytest.approx(40.0)


def test_native_sos_profile_retains_named_sos2_structure() -> None:
    case = make_hvdc_case(enforce=True, native_sos=True)
    built = build(case)
    assert portable_and_native_sos_curves_equivalent(case)
    assert len(tuple(built.model.component_data_objects(pyo.SOSConstraint))) == 1


def test_circulation_detector_flags_opposing_positive_links() -> None:
    built = build(make_hvdc_case(opposing_links=True))
    for link in built.artifacts["hvdc_flow"]:
        built.artifacts["hvdc_flow"][link].set_value(10.0)
    assert detect_nonphysical_hvdc(built) == ("circulation:('C1', 'T1')",)


def test_pricing_provenance_accepts_only_the_enforced_equivalent_case() -> None:
    case = make_hvdc_case(enforce=False)
    assert case.hvdc is not None
    requested = build(case)
    enforced = build(replace(case, hvdc=case.hvdc.with_mip_enforcement()))
    unrelated = build(make_hvdc_case(load=41.0, enforce=True))

    assert pricing_model_belongs_to_request(requested, requested)
    assert pricing_model_belongs_to_request(requested, enforced)
    assert not pricing_model_belongs_to_request(requested, unrelated)


def test_lp_mps_diagnostics_and_iis_capability_are_explicit(tmp_path) -> None:
    built = build(make_hvdc_case())
    exporter = HvdcDiagnosticExporter()
    bundle = exporter.export(built, tmp_path / "diagnostics", backend="gams-scip")
    assert set(bundle.files) == {"lp", "mps"}
    assert all(path.is_file() for path in bundle.files.values())
    assert all(len(digest) == 64 for digest in bundle.sha256.values())
    assert bundle.iis_supported is False
    with pytest.raises(
        DiagnosticCapabilityError, match="IIS extraction is unavailable"
    ):
        exporter.require_iis("gams-scip")


def test_primary_dispatch_snapshot_is_not_replaced_by_pricing_primals() -> None:
    _built, outcome, _prices = solve(make_hvdc_case(enforce=True))
    primary_values = dict(outcome.primary_snapshot.variables)
    first_pricing_variable = next(
        outcome.pricing_model.model.component_data_objects(pyo.Var, active=True)
    )
    if not first_pricing_variable.fixed:
        first_pricing_variable.set_value(pyo.value(first_pricing_variable) + 1.0)
    assert dict(outcome.primary_snapshot.variables) == primary_values
