"""Produce pinned full-formulation Gate 7 solve, price, and validation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import GdxAdapter
from pyspd.hvdc import audit_pricing_model
from pyspd.reserve import (
    IndependentReserveValidator,
    ReservePreprocessor,
    ReservePricingEngine,
    ReserveSolvePolicy,
    reserve_formulation,
    validate_reserve_price_finite_difference,
)
from pyspd.reserve.data import RISK_CLASSES


def qualify(
    *,
    input_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
    residual_tolerance: float = 1e-6,
    energy_price_tolerance: float = 1e-2,
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    source = CaseData("vspd-v5.0.6", identifier, raw)
    case = ReservePreprocessor().transform(source)
    built = ModelAssembler().assemble(reserve_formulation(), case)
    started = time.perf_counter()
    outcome = ReserveSolvePolicy().solve(built)
    if outcome.primary_mip is None:
        raise AssertionError("Gate 7 representative must execute the primary MIP")
    elapsed = time.perf_counter() - started
    prices = ReservePricingEngine().price(built, outcome)
    validation = IndependentReserveValidator().validate(
        outcome, tolerance=residual_tolerance
    )
    audit = audit_pricing_model(outcome)
    assert case.network is not None
    assert case.reserve is not None
    node = max(case.network.node_load, key=case.network.node_load.__getitem__)
    perturbation = 1e-4
    perturbed_case = replace(
        case,
        network=case.network.with_node_load(
            node, case.network.node_load[node] + perturbation
        ),
    )
    perturbed_model = ModelAssembler().assemble(reserve_formulation(), perturbed_case)
    perturbed = ReserveSolvePolicy().solve(perturbed_model)
    finite_difference = (
        outcome.primary_snapshot.objective - perturbed.primary_snapshot.objective
    ) / perturbation
    energy_error = abs(prices.energy.node[node] - finite_difference)
    reserve_key = max(prices.reserve, key=prices.reserve.__getitem__)
    reserve_check = validate_reserve_price_finite_difference(outcome, reserve_key)
    risk_coverage = _risk_coverage(outcome)
    variables = tuple(built.model.component_data_objects(pyo.Var, active=True))
    constraints = tuple(
        built.model.component_data_objects(pyo.Constraint, active=True)
    )
    portable_columns = len(built.artifacts["lambda_hvdc_energy_interval"]) + len(
        built.artifacts["lambda_hvdc_reserve_interval"]
    )
    portable_rows = len(built.model.ReserveSharing.PortableSOS2)
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-reserve-stage7",
        "case": asdict(identifier),
        "source": {
            "name": input_gdx.name,
            "sha256": hashlib.sha256(input_gdx.read_bytes()).hexdigest(),
        },
        "model": {
            "structural_signature": built.structural_signature,
            "variable_count_with_portable_sos2": len(variables),
            "constraint_count_with_portable_sos2": len(constraints),
            "oracle_projection_variable_count": len(variables) - portable_columns,
            "oracle_projection_constraint_count": len(constraints) - portable_rows,
            "portable_sos2_binary_count": portable_columns,
            "portable_sos2_constraint_count": portable_rows,
            "native_sos_count": len(
                tuple(
                    built.model.component_data_objects(
                        pyo.SOSConstraint, active=True
                    )
                )
            ),
        },
        "state_machine": {
            "primary_backend": outcome.primary_mip.solve.backend,
            "primary_status": outcome.primary_mip.solve.status.value,
            "pricing_backend": outcome.pricing_lp.backend,
            "pricing_status": outcome.pricing_lp.status.value,
            "detected_issues": list(outcome.detected_issues),
            "elapsed_seconds": elapsed,
        },
        "solution": {
            "primary_objective_nzd": outcome.primary_snapshot.objective,
            "pricing_objective_nzd": outcome.pricing_snapshot.objective,
            "objective_absolute_difference": abs(
                outcome.primary_snapshot.objective
                - outcome.pricing_snapshot.objective
            ),
            "fixed_discrete_count": len(outcome.fixed_discrete),
            "node_price_count": len(prices.energy.node),
            "reserve_price_count": len(prices.reserve),
            "all_prices_finite": all(
                math.isfinite(value)
                for value in (*prices.energy.node.values(), *prices.reserve.values())
            ),
        },
        "independent_validation": {
            "tolerance": validation.tolerance,
            "residual_count": len(validation.residuals),
            "maximum_residual": max(validation.residuals.values(), default=0.0),
            "passed": validation.passed,
        },
        "pricing_model_audit": asdict(audit),
        "energy_price_finite_difference": {
            "node": list(node),
            "perturbation_mw": perturbation,
            "dual_price_nzd_per_mwh": prices.energy.node[node],
            "finite_difference_price_nzd_per_mwh": finite_difference,
            "absolute_error": energy_error,
            "tolerance": energy_price_tolerance,
            "fixed_decisions_unchanged": dict(outcome.fixed_discrete)
            == dict(perturbed.fixed_discrete),
            "passed": energy_error <= energy_price_tolerance
            and dict(outcome.fixed_discrete) == dict(perturbed.fixed_discrete),
        },
        "reserve_price_finite_difference": asdict(reserve_check),
        "risk_coverage": risk_coverage,
        "economic_perturbations": {
            "rtd_generation_change": case.movement_penalty,
            "shared_nfr": 1e-5,
            "shared_reserve": 2e-5,
            "effective_shared_reserve_ce_ece": 3e-5,
            "exact": case.movement_penalty == 0.0005,
        },
    }
    report["passed"] = bool(
        validation.passed
        and audit.passed
        and report["energy_price_finite_difference"]["passed"]
        and reserve_check.passed
        and report["solution"]["all_prices_finite"]
        and report["economic_perturbations"]["exact"]
        and report["state_machine"]["primary_status"] == "optimal"
        and report["state_machine"]["pricing_status"] == "optimal"
    )
    return report


def _risk_coverage(outcome: Any) -> dict[str, Any]:
    model = outcome.primary_model
    risk = model.artifacts["island_risk"]
    reserve = model.artifacts["island_reserve"]
    deficit_ce = model.artifacts["reserve_deficit_ce"]
    deficit_ece = model.artifacts["reserve_deficit_ece"]
    by_class: dict[str, dict[str, int]] = {
        name: {"binding": 0, "nonbinding": 0} for name in RISK_CLASSES
    }
    for key in risk:
        deficit = deficit_ce[key[:4]] if key[-1] in {
            "genRisk",
            "DCCE",
            "manual",
            "HVDCsecRisk",
        } else deficit_ece[key[:4]]
        slack = pyo.value(reserve[key[:4]]) - (
            pyo.value(risk[key]) - pyo.value(deficit)
        )
        classification = "binding" if abs(float(slack)) <= 1e-6 else "nonbinding"
        by_class[key[-1]][classification] += 1
    return {
        "representative_case": by_class,
        "analytic_binding_and_nonbinding_coverage": "tests/reserve/test_reserve_formulation.py",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-gdx", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--trading-period", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = qualify(
        input_gdx=args.input_gdx.resolve(),
        system_directory=args.system_directory.resolve(),
        identifier=CaseIdentifier(args.case_id, args.datetime, args.trading_period),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
