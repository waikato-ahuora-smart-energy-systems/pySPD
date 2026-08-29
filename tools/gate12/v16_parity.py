"""Qualify representative SPD v16 parity against a pinned GAMS oracle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import GdxAdapter
from pyspd.preprocess import PreprocessingSettings
from pyspd.solver import HighsBackend, SolverConfiguration
from pyspd.v16 import IndependentSpd16Validator
from pyspd.v16.data import Spd16Case
from pyspd.v16.formulation import (
    Spd16PricingEngine,
    Spd16SolvePolicy,
    spd16_formulation,
)
from pyspd.v16.preprocess import SPD16_SOURCE_PROFILE_ID, Spd16SourcePreprocessor
from tools.gate12.evidence import (
    DegeneracyCertificate,
    Observable,
    ParityComparator,
    SolverProfile,
    TwoSidedDegeneracyEvidence,
)

type Key = tuple[str, ...]


@dataclass(frozen=True)
class V16Oracle:
    """Published v16 oracle surfaces with full observable identities."""

    objective: float
    energy: tuple[Observable, ...]
    reserve: tuple[Observable, ...]


def load_v16_oracle(*, prefix: Path, case_id: str) -> V16Oracle:
    """Load the three authoritative vSPD CSV surfaces used by qualification."""

    summary = _csv_rows(prefix.with_name(f"{prefix.name}_SummaryResults_TP.csv"))
    if len(summary) != 1 or summary[0]["CaseID"] != case_id:
        raise ValueError("v16 oracle summary must contain exactly the requested case")
    energy = tuple(
        Observable(
            case_id,
            "energy_price",
            (row["DateTime"], row["TradingPeriod"], row["Pnodename"]),
            float(row["vSPDDollarsPerMegawattHour"]),
        )
        for row in _csv_rows(
            prefix.with_name(f"{prefix.name}_PublishedEnergyPrices_TP.csv")
        )
    )
    reserve_rows = _csv_rows(
        prefix.with_name(f"{prefix.name}_PublishedReservePrices_TP.csv")
    )
    reserve = tuple(
        Observable(
            case_id,
            "reserve_price",
            (row["DateTime"], row["TradingPeriod"], row["Island"], reserve_class),
            float(row[field]),
        )
        for row in reserve_rows
        for reserve_class, field in (
            ("FIR", "vSPDFIRDollarsPerMegawattHour"),
            ("SIR", "vSPDSIRDollarsPerMegawattHour"),
        )
    )
    return V16Oracle(float(summary[0]["SystemOFV"]), energy, reserve)


def qualify(
    *,
    input_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
    oracle_prefix: Path,
    reference_qualification: Path,
    objective_tolerance: float = 1e-4,
    price_tolerance: float = 1e-4,
    perturbation_mw: float = 1e-3,
    derivative_tolerance: float = 2e-5,
) -> dict[str, Any]:
    """Execute and compare the portable v16 MIP/fixed-RMIP pathway."""

    oracle = load_v16_oracle(prefix=oracle_prefix, case_id=identifier.case_id)
    reference = json.loads(reference_qualification.read_text(encoding="utf-8"))
    reference_kkt_passed = bool(
        reference["authority_oracle"]["all_optimal"]
        and reference["authority_oracle"]["matrix"]["validator"] == "passed"
    )
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    source = CaseData(SPD16_SOURCE_PROFILE_ID, identifier, raw)
    preprocessed = Spd16SourcePreprocessor(
        PreprocessingSettings(apply_rtd_load_reconstruction=True)
    ).transform(source)
    case = Spd16Case.from_sources(preprocessed, source)
    built = ModelAssembler().assemble(spd16_formulation(), case)
    outcome = Spd16SolvePolicy().solve(built)
    if outcome.primary_mip is None:
        raise AssertionError("v16 portable profile must execute the primary SCIP MIP")
    prices = Spd16PricingEngine().price(built, outcome)
    validation = IndependentSpd16Validator().validate(outcome, prices.reserve)

    period_by_datetime = {
        observable.identity[0]: observable.identity[1]
        for observable in (*oracle.energy, *oracle.reserve)
    }
    actual_energy = tuple(
        Observable(
            identifier.case_id,
            "energy_price",
            (key[1], period_by_datetime[key[1]], key[2]),
            value,
        )
        for key, value in sorted(prices.energy.node.items())
    )
    actual_reserve = tuple(
        Observable(
            identifier.case_id,
            "reserve_price",
            (key[1], period_by_datetime[key[1]], key[2], key[3]),
            value,
        )
        for key, value in sorted(prices.reserve.items())
    )

    objective_error = abs(outcome.pricing_snapshot.objective - oracle.objective)
    certificates: list[DegeneracyCertificate] = []
    analyses: list[dict[str, Any]] = []
    oracle_reserve = {item.key: item for item in oracle.reserve}
    for actual in actual_reserve:
        expected = oracle_reserve.get(actual.key)
        if expected is None or abs(expected.value - actual.value) <= price_tolerance:
            continue
        model_key = (
            identifier.case_id,
            actual.identity[0],
            actual.identity[2],
            actual.identity[3],
        )
        negative = _reserve_derivative(outcome, model_key, -perturbation_mw)
        positive = _reserve_derivative(outcome, model_key, perturbation_mw)
        evidence = TwoSidedDegeneracyEvidence(
            case_id=identifier.case_id,
            observable_kind="reserve_price",
            identity=actual.identity,
            reference_value=expected.value,
            candidate_value=actual.value,
            negative_perturbation_derivative=negative,
            positive_perturbation_derivative=positive,
            derivative_tolerance=derivative_tolerance,
            common_objective_absolute_error=objective_error,
            common_objective_tolerance=objective_tolerance,
            reference_kkt_passed=reference_kkt_passed,
            candidate_kkt_passed=validation.passed,
        )
        certificate = evidence.certificate()
        analyses.append({"evidence": asdict(evidence), "certificate": asdict(certificate)})
        certificates.append(certificate)

    energy_comparison = ParityComparator(
        absolute_tolerance=price_tolerance
    ).compare(oracle.energy, actual_energy)
    reserve_comparison = ParityComparator(
        absolute_tolerance=price_tolerance
    ).compare(
        oracle.reserve,
        actual_reserve,
        certificates=tuple(certificates),
    )
    variables = tuple(built.model.component_data_objects(pyo.Var, active=True))
    constraints = tuple(
        built.model.component_data_objects(pyo.Constraint, active=True)
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "gate": 12,
        "profile": SolverProfile.PORTABLE_SCIP_HIGHS.value,
        "formulation_id": built.formulation.formulation_id,
        "case": asdict(identifier),
        "source": {
            "name": input_gdx.name,
            "sha256": _sha256(input_gdx),
        },
        "reference": {
            "qualification": str(reference_qualification),
            "kkt_and_matrix_validator_passed": reference_kkt_passed,
            "objective": oracle.objective,
        },
        "model": {
            "structural_signature": built.structural_signature,
            "variable_count": len(variables),
            "constraint_count": len(constraints),
        },
        "solve": {
            "primary_backend": outcome.primary_mip.solve.backend,
            "primary_status": outcome.primary_mip.solve.status.value,
            "pricing_backend": outcome.pricing_lp.backend,
            "pricing_status": outcome.pricing_lp.status.value,
            "primary_objective": outcome.primary_snapshot.objective,
            "pricing_objective": outcome.pricing_snapshot.objective,
            "reference_objective_absolute_error": objective_error,
            "objective_tolerance": objective_tolerance,
            "fixed_discrete_count": len(outcome.fixed_discrete),
            "fixed_sos_member_count": len(outcome.fixed_sos_members),
        },
        "independent_validation": {
            "passed": validation.passed,
            "tolerance": validation.tolerance,
            "maximum_residual": max(validation.residuals.values(), default=0.0),
            "pricing_model_audit_passed": validation.pricing_model_audit_passed,
        },
        "energy_price_comparison": asdict(energy_comparison),
        "reserve_price_comparison": asdict(reserve_comparison),
        "degeneracy_analyses": analyses,
    }
    report["passed"] = bool(
        objective_error <= objective_tolerance
        and validation.passed
        and energy_comparison.passed
        and reserve_comparison.passed
        and report["solve"]["primary_status"] == "optimal"
        and report["solve"]["pricing_status"] == "optimal"
    )
    return report


def _reserve_derivative(outcome: Any, key: Key, delta: float) -> float:
    source_constraint = outcome.pricing_model.artifacts[
        "island_reserve_definition"
    ][key]
    model = outcome.pricing_model.model.clone()
    constraint = model.find_component(source_constraint.name)
    if constraint is None:
        raise KeyError(f"pricing constraint not found: {source_constraint.name}")
    upper = float(pyo.value(constraint.upper))
    constraint.set_value((constraint.lower, constraint.body, upper + delta))
    result = HighsBackend().solve(
        model,
        SolverConfiguration(
            {
                "solver": "simplex",
                "primal_feasibility_tolerance": 1e-8,
                "dual_feasibility_tolerance": 1e-8,
                "random_seed": 0,
                "threads": 1,
            }
        ),
    )
    if not result.solution_loaded:
        raise ValueError("v16 reserve-price perturbation did not load a solution")
    objective = next(model.component_data_objects(pyo.Objective, active=True))
    return (
        float(pyo.value(objective)) - outcome.pricing_snapshot.objective
    ) / delta


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-gdx", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--trading-period", required=True)
    parser.add_argument("--oracle-prefix", type=Path, required=True)
    parser.add_argument("--reference-qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = qualify(
        input_gdx=args.input_gdx.resolve(),
        system_directory=args.system_directory.resolve(),
        identifier=CaseIdentifier(
            args.case_id, args.datetime, args.trading_period
        ),
        oracle_prefix=args.oracle_prefix.resolve(),
        reference_qualification=args.reference_qualification.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
