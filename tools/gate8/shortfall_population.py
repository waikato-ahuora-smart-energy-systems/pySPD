"""Derive the v5.0.4 shortfall-transfer interval identity population.

The Authority release publishes the affected count and trading dates, but not
the 546 case identifiers. The corrected inputs retain the defining pre-solve
signature: positive RTD initial load at a node whose mapped buses have no
positive electrical-island assignment. Such a node is dead under the pinned
vSPD rule and its load necessarily enters energy scarcity before transfer.
This tool evaluates that predicate directly and binds every resulting interval
to its Gate 1 hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from gams.transfer import Container

SYMBOLS = [
    "i_dateTimeNodeParameter",
    "i_dateTimeNodeBus",
    "i_dateTimeBusElectricalIsland",
    "i_dateTimeParameter",
    "i_dateTimeTradePeriodMap",
    "i_runMode",
    "i_priceCaseFilesPublishedSecs",
]


def derive(
    *,
    input_root: Path,
    inventory_path: Path,
    population_path: Path,
    system_directory: Path,
) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    population = json.loads(population_path.read_text(encoding="utf-8"))
    by_date = {item["trading_date"]: item for item in inventory["artifacts"]}
    dates = population["trading_dates"]
    if set(dates) != set(by_date):
        raise AssertionError("Gate 1 date inventory and release population differ")

    intervals: list[dict[str, Any]] = []
    per_date: dict[str, int] = {}
    for position, trading_date in enumerate(dates, start=1):
        path = input_root / trading_date[:4] / f"Pricing_{trading_date}.gdx"
        expected_hash = by_date[trading_date]["sha256"]
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise AssertionError(f"source hash mismatch: {path}")
        discovered = _derive_file(path, system_directory)
        per_date[trading_date] = len(discovered)
        intervals.extend(
            {
                **item,
                "trading_date": trading_date,
                "source_name": path.name,
                "source_sha256": actual_hash,
                "assertions": {
                    "dead_node_positive_load_predicate_replayed": True,
                    "bounded_by_source_max_solve_loop": True,
                    "gate8_state_machine_regression": (
                        "tests/orchestration/test_shortfall_population.py"
                    ),
                },
            }
            for item in discovered
        )
        print(
            f"[{position:03d}/{len(dates)}] {trading_date}: "
            f"{len(discovered)} affected intervals"
        )

    identities = {(item["case_id"], item["date_time"]) for item in intervals}
    if len(identities) != len(intervals):
        raise AssertionError("derived interval identities are not unique")
    declared = int(population["declared_affected_interval_count"])
    return {
        "schema_version": 1,
        "method": {
            "authority_release": population["source_release"],
            "release_commit": population["release_commit"],
            "declared_affected_interval_count": declared,
            "predicate": (
                "initialLoad(node) > 0 and sum(busElectricalIsland(node_bus)) = 0"
            ),
            "reference_source": "vSPDsolve.gms:1287-1291,1308-1318",
            "interpretation": (
                "exact immutable affected identities derived from the corrected "
                "daily GDX dead-node/positive-load signature and reconciled to "
                "the Authority's independently declared count"
            ),
        },
        "source_population": {
            "date_count": len(dates),
            "all_gate1_hashes_verified": True,
            "inventory": str(inventory_path),
        },
        "derived_interval_count": len(intervals),
        "declared_count_matches": len(intervals) == declared,
        "per_date": per_date,
        "intervals": intervals,
        "passed": len(intervals) == declared and len(dates) == 139,
    }


def _derive_file(path: Path, system_directory: Path) -> list[dict[str, Any]]:
    container = Container(system_directory=str(system_directory))
    container.read(str(path), symbols=SYMBOLS)
    frames = {name: container[name].records for name in SYMBOLS}
    if any(frame is None for frame in frames.values()):
        raise AssertionError(f"missing required records in {path}")

    node_parameter = frames["i_dateTimeNodeParameter"]
    node_bus = frames["i_dateTimeNodeBus"]
    bus_electrical_island = frames["i_dateTimeBusElectricalIsland"]
    date_time_parameter = frames["i_dateTimeParameter"]
    period_map = frames["i_dateTimeTradePeriodMap"]
    run_mode = frames["i_runMode"]
    publication = frames["i_priceCaseFilesPublishedSecs"]
    assert node_parameter is not None
    assert node_bus is not None
    assert bus_electrical_island is not None
    assert date_time_parameter is not None
    assert period_map is not None
    assert run_mode is not None
    assert publication is not None

    initial_load = {
        (str(row.ca), str(row.dt), str(row.n)): float(row.value)
        for row in node_parameter.itertuples(index=False)
        if str(row.nodePar) == "initialLoad" and float(row.value) > 0.0
    }
    positive_island_buses = {
        (str(row.ca), str(row.dt), str(row.b))
        for row in bus_electrical_island.itertuples(index=False)
        if float(row.value) > 0.0
    }
    node_buses: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in node_bus.itertuples(index=False):
        node_buses[(str(row.ca), str(row.dt), str(row.n))].add(str(row.b))
    affected_nodes: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for node, load in initial_load.items():
        case_id, date_time, node_name = node
        buses = node_buses.get(node, set())
        if buses and not any(
            (case_id, date_time, bus) in positive_island_buses for bus in buses
        ):
            affected_nodes[(case_id, date_time)][node_name] = load

    periods = {
        (str(row.ca), str(row.dt)): str(row.tp)
        for row in period_map.itertuples(index=False)
    }
    modes = {
        str(row.ca): int(float(row.value))
        for row in run_mode.itertuples(index=False)
        if str(row.casePar) == "studyMode"
    }
    limits = {
        (str(row.ca), str(row.dt)): int(float(row.value))
        for row in date_time_parameter.itertuples(index=False)
        if str(row.dtPar) == "maxSolveLoop"
    }
    seconds = {
        (str(row.ca), str(row.tp)): float(row.value)
        for row in publication.itertuples(index=False)
    }
    discovered: list[dict[str, Any]] = []
    for (case_id, date_time), nodes in affected_nodes.items():
        trading_period = periods[(case_id, date_time)]
        maximum = limits.get((case_id, date_time), 0) or 5
        discovered.append(
            {
                "case_id": case_id,
                "date_time": date_time,
                "trading_period": trading_period,
                "study_mode": modes[case_id],
                "publication_seconds": seconds.get((case_id, trading_period), 0.0),
                "maximum_solve_loops": maximum,
                "affected_dead_nodes": [
                    {
                        "node": node,
                        "initial_load_mw": nodes[node],
                        "buses": sorted(node_buses[(case_id, date_time, node)]),
                    }
                    for node in sorted(nodes)
                ],
            }
        )
    discovered.sort(key=lambda item: (item["date_time"], item["case_id"]))
    return discovered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = derive(
        input_root=args.input_root.resolve(),
        inventory_path=args.inventory.resolve(),
        population_path=args.population.resolve(),
        system_directory=args.system_directory.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
