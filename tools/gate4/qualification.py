"""Produce reproducible Gate 4 solve, residual, and independent price evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.core_energy import (
    CoreEnergyPricingEngine,
    CoreEnergySolvePolicy,
    core_energy_formulation,
)
from pyspd.core_energy.validation import finite_difference_price, validate_core_energy
from pyspd.data import GdxAdapter


def qualify(
    *, input_gdx: Path, system_directory: Path, identifier: CaseIdentifier
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    built = ModelAssembler().assemble(
        core_energy_formulation(preprocess=True),
        CaseData("vspd-v5.0.6", identifier, raw),
    )
    result = CoreEnergySolvePolicy().solve(built)
    prices = CoreEnergyPricingEngine().price(built, result)
    validation = validate_core_energy(built)
    epsilon = 1e-3
    finite_difference = {
        region: finite_difference_price(built.case_data, region, epsilon_mw=epsilon)
        for region in sorted(built.case_data.regions)
    }
    price_errors = {
        region: abs(prices.values[region] - finite_difference[region])
        for region in prices.values
    }
    objective = validation.objective_components
    component_error = max(
        (abs(value) for value in validation.objective_component_errors.values()),
        default=0.0,
    )
    tolerance = {
        "primal_residual_mw": 1e-7,
        "objective_component_nzd": 1e-7,
        "finite_difference_price_nzd_per_mwh": 2e-5,
    }
    passed = (
        result.raw_termination_condition == "optimal"
        and validation.maximum_residual <= tolerance["primal_residual_mw"]
        and validation.maximum_bound_violation <= tolerance["primal_residual_mw"]
        and component_error <= tolerance["objective_component_nzd"]
        and max(price_errors.values(), default=0.0)
        <= tolerance["finite_difference_price_nzd_per_mwh"]
    )
    interval_revenue_examples = {
        _semantic(region): prices.values[region]
        * built.case_data.interval_minutes[region[:2]]
        / 60.0
        for region in prices.values
    }
    return {
        "schema_version": 1,
        "profile": "macOS-arm64-highs-core-energy",
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "source": {
            "name": input_gdx.name,
            "sha256": hashlib.sha256(input_gdx.read_bytes()).hexdigest(),
            "case": {
                "case_id": identifier.case_id,
                "date_time": identifier.date_time,
                "trading_period": identifier.trading_period,
            },
        },
        "structure": {
            "formulation_id": built.formulation.formulation_id,
            "build_order": built.build_order,
            "structural_signature": built.structural_signature,
            "preprocessing_signature": built.case_data.preprocessing_signature,
            "periods": len(built.case_data.periods),
            "regions": len(built.case_data.regions),
            "offers": len(built.case_data.offers),
            "offer_blocks": len(built.case_data.offer_blocks),
            "scarcity_blocks": len(built.case_data.scarcity_blocks),
        },
        "solver": {
            "backend": result.backend,
            "interface": result.interface,
            "version": result.version,
            "status": result.status.value,
            "termination": result.raw_termination_condition,
            "solution_loaded": result.solution_loaded,
            "options": dict(result.options),
        },
        "objective_components_nzd": dict(objective),
        "validation": {
            "maximum_primal_residual_mw": validation.maximum_residual,
            "maximum_bound_violation_mw": validation.maximum_bound_violation,
            "maximum_objective_component_error_nzd": component_error,
        },
        "pricing": {
            "unit": prices.unit,
            "dual_normalization": prices.convention,
            "dual_prices": {
                _semantic(region): value for region, value in prices.values.items()
            },
            "raw_duals": {
                _semantic(region): value for region, value in prices.raw_duals.items()
            },
            "finite_difference_epsilon_mw": epsilon,
            "finite_difference_prices": {
                _semantic(region): value for region, value in finite_difference.items()
            },
            "absolute_errors": {
                _semantic(region): value for region, value in price_errors.items()
            },
            "maximum_absolute_error": max(price_errors.values(), default=0.0),
            "duration_conversion": (
                "vSPD marginal prices are not interval-scaled; interval revenue "
                "for 1 MW is price * interval_minutes / 60"
            ),
            "one_mw_interval_revenue_nzd": interval_revenue_examples,
        },
        "tolerances": tolerance,
        "passed": passed,
    }


def _semantic(index: tuple[str, ...]) -> str:
    return "[" + ",".join(json.dumps(value) for value in index) + "]"


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
