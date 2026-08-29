"""Produce reproducible pinned-case Gate 5 solve, price, and residual evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import GdxAdapter
from pyspd.network import (
    IndependentNetworkValidator,
    NetworkPreprocessor,
    NetworkPricingEngine,
    NetworkSolvePolicy,
    ac_network_formulation,
    validate_nodal_price_finite_difference,
)


def qualify(
    *,
    input_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
    residual_tolerance: float = 1e-7,
    price_tolerance: float = 1e-2,
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    source_case = CaseData("vspd-v5.0.6", identifier, raw)
    case = NetworkPreprocessor().transform(source_case)
    built = ModelAssembler().assemble(ac_network_formulation(), case)
    started = time.perf_counter()
    solve_result = NetworkSolvePolicy().solve(built)
    elapsed = time.perf_counter() - started
    prices = NetworkPricingEngine().price(built, solve_result)
    validation = IndependentNetworkValidator().validate(
        built, prices, tolerance=residual_tolerance
    )
    assert case.network is not None
    network = case.network
    price_node = max(
        network.node_load, key=lambda key: network.node_load[key]
    )
    price_check = validate_nodal_price_finite_difference(
        case,
        price_node,
        perturbation_mw=1e-4,
        tolerance=price_tolerance,
    )
    branch_flow = built.artifacts["branch_flow"]
    directed_loss = built.artifacts["directed_branch_loss"]
    finite_prices = all(math.isfinite(value) for value in prices.node.values())
    report = {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-ac-network-stage5",
        "case": asdict(identifier),
        "source": {
            "name": input_gdx.name,
            "sha256": hashlib.sha256(input_gdx.read_bytes()).hexdigest(),
        },
        "solver": {
            "backend": solve_result.backend,
            "interface": solve_result.interface,
            "version": list(solve_result.version),
            "status": solve_result.status.value,
            "solution_loaded": solve_result.solution_loaded,
            "elapsed_seconds": elapsed,
        },
        "model": {
            "structural_signature": built.structural_signature,
            "bus_count": len(network.buses),
            "ac_branch_count": len(network.ac_branches),
            "loss_segment_count": len(network.valid_ac_loss_segments),
            "branch_constraint_count": len(network.branch_constraints),
            "market_node_constraint_count": len(
                network.market_node_constraints
            ),
        },
        "solution": {
            "net_benefit": float(pyo.value(built.artifacts["net_benefit"])),
            "maximum_absolute_branch_flow_mw": max(
                (abs(float(pyo.value(branch_flow[key]))) for key in branch_flow),
                default=0.0,
            ),
            "total_dynamic_ac_loss_mw": sum(
                float(pyo.value(directed_loss[key])) for key in directed_loss
            ),
            "node_price_count": len(prices.node),
            "dead_node_count": len(prices.dead_nodes),
            "all_node_prices_finite": finite_prices,
        },
        "independent_validation": {
            "tolerance": validation.tolerance,
            "residual_count": len(validation.residuals),
            "maximum_residual": max(validation.residuals.values(), default=0.0),
            "passed": validation.passed,
        },
        "finite_difference_price": asdict(price_check),
    }
    report["passed"] = bool(
        solve_result.solution_loaded
        and validation.passed
        and price_check.passed
        and finite_prices
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
