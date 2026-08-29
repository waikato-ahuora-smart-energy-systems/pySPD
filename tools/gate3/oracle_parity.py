"""Compare Python preprocessing artifacts with the Gate 1 GAMS checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import GdxAdapter, RawSymbol, ValueKind
from pyspd.preprocess import SparseParameter, SparseSet, Vspd506Preprocessor

ARTIFACT_MAP = {
    "node": "node",
    "bus": "bus",
    "node_island": "nodeIsland",
    "branch": "branch",
    "ac_branch": "ACBranch",
    "hvdc_link": "HVDClink",
    "total_bus_allocation": "totalBusAllocation",
    "bus_node_allocation_factor": "busNodeAllocationFactor",
    "branch_capacity": "branchCapacity",
    "branch_resistance": "branchResistance",
    "branch_susceptance": "branchSusceptance",
    "branch_fixed_loss": "branchFixedLoss",
    "branch_loss_blocks": "branchLossBlocks",
    "loss_segment_mw": "lossSegmentMW",
    "loss_segment_factor": "lossSegmentFactor",
    "valid_loss_segment": "validLossSegment",
    "loss_branch": "LossBranch",
    "ac_branch_loss_mw": "ACBranchLossMW",
    "ac_branch_loss_factor": "ACBranchLossFactor",
    "hvdc_breakpoint_flow": "HVDCBreakPointMWFlow",
    "hvdc_breakpoint_loss": "HVDCBreakPointMWLoss",
    "study_mode": "studyMode",
    "interval_duration": "IntervalDuration",
    "generation_start": "generationStart",
    "ramp_rate_up": "rampRateUp",
    "ramp_rate_down": "rampRateDn",
    "reserve_generation_maximum": "reserveGenMax",
    "reserve_maximum_factor": "reserveMaxFactor",
    "offer": "offer",
    "offer_island": "offerIsland",
    "primary_offer": "primaryOffer",
    "secondary_offer": "secondaryOffer",
    "primary_secondary_offer": "primarySecondaryOffer",
    "intermittent_offer": "intermittentOffer",
    "price_responsive_offer": "priceResponsive",
    "potential_mw": "potentialMW",
    "energy_offer_mw": "enrgOfrMW",
    "energy_offer_price": "enrgOfrPrice",
    "generation_offer_block": "genOfrBlk",
    "positive_energy_offer": "posEnrgOfr",
    "reserve_offer_mw": "resrvOfrMW",
    "reserve_offer_price": "resrvOfrPrice",
    "reserve_offer_percent": "resrvOfrPct",
    "reserve_offer_block": "resOfrBlk",
    "bid": "Bid",
    "bid_island": "bidIsland",
    "demand_bid_mw": "demBidMW",
    "demand_bid_price": "demBidPrice",
    "demand_bid_block": "DemBidBlk",
    "required_load": "requiredLoad",
    "branch_constraint": "BranchConstraint",
    "branch_constraint_sense": "BranchConstraintSense",
    "branch_constraint_limit": "BranchConstraintLimit",
    "branch_constraint_ramping": "rampingConstraint",
    "market_node_constraint": "MNodeConstraint",
    "market_node_constraint_sense": "MNodeConstraintSense",
    "market_node_constraint_limit": "MNodeConstraintLimit",
    "island_risk_group": "islandRiskGroup",
    "risk_adjustment_factor": "riskAdjFactor",
    "reserve_share_enabled": "reserveShareEnabled",
    "reserve_round_power": "reserveRoundPower",
    "round_power_zone_exit": "roPwrZoneExit",
    "energy_scarcity_enabled": "energyScarcityEnabled",
    "reserve_scarcity_enabled": "reserveScarcityEnabled",
    "bad_price_factor": "badPriceFactor",
    "scarcity_energy_price_max": "scarcityEnergyPriceMax",
    "scarcity_reserve_limit": "scarcityResrvIslandLimit",
    "scarcity_reserve_price": "scarcityResrvIslandPrice",
}


@dataclass(frozen=True, slots=True)
class Comparison:
    python_artifact: str
    gams_symbol: str
    kind: str
    python_nonzero_records: int
    gams_nonzero_records: int
    missing_in_python: int
    extra_in_python: int
    value_mismatches: int
    maximum_absolute_error: float
    samples: tuple[str, ...]
    passed: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _oracle_values(symbol: RawSymbol) -> dict[tuple[str, ...], float]:
    values: dict[tuple[str, ...], float] = {}
    for record in symbol.records:
        value = record.values.get("value")
        if value is None or value.kind is ValueKind.EPS:
            number = 0.0
        elif value.kind is ValueKind.FINITE:
            assert value.number is not None
            number = value.number
        else:
            raise ValueError(f"unsupported checkpoint value {symbol.name}{record.keys}")
        if number != 0.0:
            values[record.keys] = number
    return values


def compare(
    *,
    input_gdx: Path,
    checkpoint_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
    tolerance: float,
) -> dict[str, object]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    result = Vspd506Preprocessor().transform(CaseData("vspd-v5.0.6", identifier, raw))
    checkpoint = GdxAdapter.read(checkpoint_gdx, system_directory=system_directory)
    oracle_by_name = {symbol.name.casefold(): symbol for symbol in checkpoint.symbols}
    comparisons: list[Comparison] = []
    for python_name, gams_name in ARTIFACT_MAP.items():
        artifact = result.artifacts[python_name]
        oracle = oracle_by_name[gams_name.casefold()]
        if isinstance(artifact, SparseSet):
            python_records = artifact.members
            oracle_records = frozenset(record.keys for record in oracle.records)
            missing = oracle_records - python_records
            extra = python_records - oracle_records
            samples = tuple(
                [f"missing:{key!r}" for key in sorted(missing)[:3]]
                + [f"extra:{key!r}" for key in sorted(extra)[:3]]
            )
            comparisons.append(
                Comparison(
                    python_name,
                    oracle.name,
                    "set",
                    len(python_records),
                    len(oracle_records),
                    len(missing),
                    len(extra),
                    0,
                    0.0,
                    samples,
                    not missing and not extra,
                )
            )
            continue
        if not isinstance(artifact, SparseParameter):
            raise TypeError(python_name)
        python_values = {
            key: value for key, value in artifact.values.items() if value != 0.0
        }
        oracle_values = _oracle_values(oracle)
        missing_keys = set(oracle_values) - set(python_values)
        extra_keys = set(python_values) - set(oracle_values)
        differences = {
            key: abs(python_values.get(key, 0.0) - oracle_values.get(key, 0.0))
            for key in set(python_values) | set(oracle_values)
        }
        mismatches = {
            key: error for key, error in differences.items() if error > tolerance
        }
        samples = tuple(
            f"{key!r}:python={python_values.get(key, 0.0)!r},"
            f"gams={oracle_values.get(key, 0.0)!r},error={error!r}"
            for key, error in sorted(mismatches.items())[:6]
        )
        comparisons.append(
            Comparison(
                python_name,
                oracle.name,
                "parameter",
                len(python_values),
                len(oracle_values),
                len(missing_keys),
                len(extra_keys),
                len(mismatches),
                max(differences.values(), default=0.0),
                samples,
                not mismatches,
            )
        )
    return {
        "schema_version": 1,
        "profile": "vspd-v5.0.6",
        "case": asdict(identifier),
        "precision_rule": {
            "comparison": "absolute error after normalizing sparse absent and explicit zero",
            "absolute_tolerance": tolerance,
        },
        "input_gdx": {
            "name": input_gdx.name,
            "sha256": _sha256(input_gdx),
        },
        "checkpoint_gdx": {
            "name": checkpoint_gdx.name,
            "sha256": _sha256(checkpoint_gdx),
        },
        "python_checkpoint_hashes": {
            checkpoint.step: checkpoint.logical_sha256
            for checkpoint in result.checkpoints
        },
        "comparison_count": len(comparisons),
        "comparisons": [asdict(item) for item in comparisons],
        "passed": all(item.passed for item in comparisons),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-gdx", type=Path, required=True)
    parser.add_argument("--checkpoint-gdx", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--trading-period", required=True)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    system_directory = args.system_directory
    if system_directory is None:
        import gamspy_base

        system_directory = Path(gamspy_base.__file__).parent
    report = compare(
        input_gdx=args.input_gdx.resolve(),
        checkpoint_gdx=args.checkpoint_gdx.resolve(),
        system_directory=system_directory.resolve(),
        identifier=CaseIdentifier(args.case_id, args.datetime, args.trading_period),
        tolerance=args.tolerance,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "comparison_count": report["comparison_count"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
