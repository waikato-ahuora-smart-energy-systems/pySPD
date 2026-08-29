"""Produce pinned-case Gate 6 HVDC solve, pricing, and audit evidence."""

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
from pyspd.hvdc import (
    HvdcPreprocessor,
    HvdcPricingEngine,
    HvdcSolvePolicy,
    IndependentHvdcValidator,
    audit_pricing_model,
    hvdc_formulation,
)
from pyspd.solver import MipSolveResult


def qualify(
    *,
    input_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
    residual_tolerance: float = 1e-7,
    price_tolerance: float = 1e-2,
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    source = CaseData("vspd-v5.0.6", identifier, raw)
    case = HvdcPreprocessor().transform(source)
    built = ModelAssembler().assemble(hvdc_formulation(), case)
    started = time.perf_counter()
    outcome = HvdcSolvePolicy().solve(built)
    elapsed = time.perf_counter() - started
    prices = HvdcPricingEngine().price(built, outcome)
    validation = IndependentHvdcValidator().validate(
        outcome, tolerance=residual_tolerance
    )
    audit = audit_pricing_model(outcome)
    initial_solve = (
        outcome.initial_solve.solve
        if isinstance(outcome.initial_solve, MipSolveResult)
        else outcome.initial_solve
    )
    assert case.network is not None
    assert case.hvdc is not None
    node = max(case.network.node_load, key=case.network.node_load.__getitem__)
    perturbation = 1e-4
    perturbed_case = replace(
        case,
        network=case.network.with_node_load(
            node, case.network.node_load[node] + perturbation
        ),
    )
    perturbed_built = ModelAssembler().assemble(hvdc_formulation(), perturbed_case)
    perturbed = HvdcSolvePolicy().solve(perturbed_built)
    finite_difference = (
        outcome.primary_snapshot.objective - perturbed.primary_snapshot.objective
    ) / perturbation
    price_error = abs(prices.node[node] - finite_difference)
    variables = tuple(built.model.component_data_objects(pyo.Var, active=True))
    constraints = tuple(
        built.model.component_data_objects(pyo.Constraint, active=True)
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-hvdc-stage6",
        "case": asdict(identifier),
        "source": {
            "name": input_gdx.name,
            "sha256": hashlib.sha256(input_gdx.read_bytes()).hexdigest(),
        },
        "model": {
            "structural_signature": built.structural_signature,
            "variable_count": len(variables),
            "constraint_count": len(constraints),
            "hvdc_link_count": len(case.hvdc.links),
            "hvdc_breakpoint_count": len(case.hvdc.breakpoints),
        },
        "state_machine": {
            "initial_backend": initial_solve.backend,
            "detected_issues": list(outcome.detected_issues),
            "mip_resolve_triggered": outcome.primary_mip is not None,
            "primary_backend": outcome.primary_mip.solve.backend
            if outcome.primary_mip is not None
            else initial_solve.backend,
            "primary_status": outcome.primary_mip.solve.status.value
            if outcome.primary_mip is not None
            else initial_solve.status.value,
            "pricing_backend": outcome.pricing_lp.backend,
            "pricing_status": outcome.pricing_lp.status.value,
            "elapsed_seconds": elapsed,
        },
        "solution": {
            "primary_objective_nzd": outcome.primary_snapshot.objective,
            "pricing_objective_nzd": outcome.pricing_snapshot.objective,
            "fixed_discrete_count": len(outcome.fixed_discrete),
            "node_price_count": len(prices.node),
            "all_node_prices_finite": all(
                math.isfinite(value) for value in prices.node.values()
            ),
        },
        "independent_validation": {
            "tolerance": validation.tolerance,
            "residual_count": len(validation.residuals),
            "maximum_residual": max(validation.residuals.values(), default=0.0),
            "passed": validation.passed,
        },
        "pricing_model_audit": asdict(audit),
        "finite_difference_price": {
            "node": list(node),
            "perturbation_mw": perturbation,
            "dual_price_nzd_per_mwh": prices.node[node],
            "finite_difference_price_nzd_per_mwh": finite_difference,
            "absolute_error": price_error,
            "tolerance": price_tolerance,
            "fixed_decisions_unchanged": dict(outcome.fixed_discrete)
            == dict(perturbed.fixed_discrete),
            "passed": price_error <= price_tolerance,
        },
    }
    report["passed"] = bool(
        validation.passed
        and audit.passed
        and report["finite_difference_price"]["passed"]
        and report["solution"]["all_node_prices_finite"]
    )
    return report


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
