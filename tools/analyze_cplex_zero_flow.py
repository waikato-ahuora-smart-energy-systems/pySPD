"""Analyze basis-selected CPLEX prices at passive zero-flow AC-loss leaves."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from enum import StrEnum
from pathlib import Path
from typing import Any

_PERIOD_CACHE: dict[tuple[Path, str], str] = {}


class EndpointSide(StrEnum):
    EXPORT = "export"
    LOAD = "load"
    AMBIGUOUS = "ambiguous"


def classify_endpoint(
    parent_price: float, leaf_price: float, *, tolerance: float = 5e-5
) -> EndpointSide:
    """Classify a zero-flow leaf price without assuming the price sign.

    For symmetric positive marginal losses, the export endpoint has a
    leaf/parent ratio below one and the load endpoint has a ratio above one.
    Values indistinguishable at the five-decimal branch-report precision are
    deliberately left unclassified.
    """

    if (
        not math.isfinite(parent_price)
        or not math.isfinite(leaf_price)
        or abs(parent_price) <= tolerance
        or parent_price * leaf_price <= 0.0
        or abs(parent_price - leaf_price) <= tolerance
    ):
        return EndpointSide.AMBIGUOUS
    ratio = leaf_price / parent_price
    if ratio < 1.0:
        return EndpointSide.EXPORT
    if ratio > 1.0:
        return EndpointSide.LOAD
    return EndpointSide.AMBIGUOUS


def export_delta_from_load_endpoint(parent_price: float, leaf_price: float) -> float:
    """Return export minus load price when ``leaf_price`` is the load endpoint."""

    if leaf_price == 0.0 or parent_price * leaf_price <= 0.0:
        raise ValueError("a same-sign nonzero parent and leaf price is required")
    return parent_price * parent_price / leaf_price - leaf_price


def _number(row: dict[str, str], name: str) -> float:
    value = row.get(name, "")
    return 0.0 if value == "" else float(value)


def _identity(row: dict[str, str]) -> tuple[str, str]:
    return row.get("CaseID", ""), row["DateTime"].casefold()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _only(directory: Path, pattern: str) -> Path:
    matches = tuple(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"expected one {pattern} in {directory}, found {len(matches)}")
    return matches[0]


def _source_projection(
    *,
    input_path: Path,
    results: Path,
    year: int,
    system_directory: Path,
) -> tuple[
    dict[tuple[str, str, str], list[tuple[str, float]]],
    dict[tuple[str, str], float],
]:
    try:
        from gams import transfer as gt
    except ImportError as error:  # pragma: no cover - dependency boundary
        raise RuntimeError("run with uv --group gdx") from error

    container = gt.Container(system_directory=str(system_directory))
    if year == 2023:
        allocation_name = "i_dateTimeNodeBusAllocationFactor"
        seconds_name = "i_priceCaseFilesPublishedSecs"
        container.read(str(input_path), symbols=[allocation_name, seconds_name])
        allocation_frame = container[allocation_name].records
        seconds_frame = container[seconds_name].records
        if allocation_frame is None or seconds_frame is None:
            raise ValueError("2023 GDX projection symbols have no records")
        allocations: dict[tuple[str, str, str], list[tuple[str, float]]] = (
            defaultdict(list)
        )
        for row in allocation_frame.itertuples(index=False):
            allocations[(str(row.ca), str(row.dt).casefold(), str(row.b))].append(
                (str(row.n), float(row.value))
            )
        seconds = {
            (str(row.ca), str(row.tp)): float(row.value)
            for row in seconds_frame.itertuples(index=False)
        }
        return dict(allocations), seconds

    allocation_name = "i_tradePeriodNodeBusAllocationFactor"
    container.read(str(input_path), symbols=[allocation_name])
    allocation_frame = container[allocation_name].records
    if allocation_frame is None:
        raise ValueError("2019 GDX allocation symbol has no records")
    node_rows = _read_csv(_only(results, "*base_node_results.csv"))
    period_datetime = {
        row["TP"]: row["DateTime"].casefold() for row in node_rows
    }
    allocations = defaultdict(list)
    for row in allocation_frame.itertuples(index=False):
        date_time = period_datetime[str(row.tp)]
        allocations[("", date_time, str(row.b))].append(
            (str(row.n), float(row.value))
        )
    return dict(allocations), {}


def analyze_day(
    day: Path, *, year: int, system_directory: Path
) -> dict[str, Any]:
    results = day / "results"
    input_path = _only(day / "input", "*.gdx")
    branch_rows = _read_csv(_only(results, "*raw_BranchResults_TP.csv"))
    bus_rows = _read_csv(_only(results, "*raw_BusResults_TP.csv"))
    allocations, seconds = _source_projection(
        input_path=input_path,
        results=results,
        year=year,
        system_directory=system_directory,
    )

    buses = {
        (*_identity(row), row["Bus"]): row
        for row in bus_rows
    }
    degree: Counter[tuple[str, str, str]] = Counter()
    period_cases: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in branch_rows:
        identity = _identity(row)
        degree[(*identity, row["FromBus"])] += 1
        degree[(*identity, row["ToBus"])] += 1
        period = row.get("Period", "")
        if not period:
            period = _period_from_datetime(results, row["DateTime"])
        period_cases[period].add(identity)

    side_counts: Counter[str] = Counter()
    load_bus_deltas: list[tuple[float, tuple[str, ...]]] = []
    node_case_delta: dict[tuple[str, str, str, str], float] = defaultdict(float)
    projected_endpoint_counts: Counter[str] = Counter()
    load_endpoint_node_counts: Counter[str] = Counter()
    projected_load_observations = 0
    unprojected_load_observations = 0

    for row in branch_rows:
        if any(
            abs(_number(row, field)) > 5e-8
            for field in (
                "Flow (MW) (From->To)",
                "DynamicLoss (MW)",
                "FixedLoss (MW)",
            )
        ):
            continue
        identity = _identity(row)
        period = row.get("Period", "") or _period_from_datetime(
            results, row["DateTime"]
        )
        endpoints = (
            (
                row["FromBus"],
                row["ToBus"],
                _number(row, "FromBusPrice ($/MWh)"),
                _number(row, "ToBusPrice ($/MWh)"),
            ),
            (
                row["ToBus"],
                row["FromBus"],
                _number(row, "ToBusPrice ($/MWh)"),
                _number(row, "FromBusPrice ($/MWh)"),
            ),
        )
        for leaf, parent, leaf_price, parent_price in endpoints:
            if degree[(*identity, leaf)] != 1:
                continue
            bus = buses.get((*identity, leaf))
            if bus is None or any(
                abs(_number(bus, field)) > 5e-8
                for field in ("Generation (MW)", "Load (MW)")
            ):
                continue
            side = classify_endpoint(parent_price, leaf_price)
            side_counts[side.value] += 1
            mappings = allocations.get((*identity, leaf), ())
            if mappings:
                projected_endpoint_counts[side.value] += 1
            if side is not EndpointSide.LOAD:
                continue
            delta = export_delta_from_load_endpoint(parent_price, leaf_price)
            detail = (
                day.name,
                identity[0],
                row["DateTime"],
                period,
                row["Branch"],
                leaf,
                parent,
            )
            load_bus_deltas.append((delta, detail))
            if mappings:
                projected_load_observations += 1
            else:
                unprojected_load_observations += 1
            for node, weight in mappings:
                load_endpoint_node_counts[node] += 1
                node_case_delta[(*identity, period, node)] += weight * delta

    maximum_bus = max(load_bus_deltas, key=lambda item: abs(item[0]), default=None)
    maximum_node = max(
        node_case_delta.items(), key=lambda item: abs(item[1]), default=None
    )
    base_delta: dict[tuple[str, str], float] = {}
    for period, cases in period_cases.items():
        nodes = {
            node
            for _case, _date_time, item_period, node in node_case_delta
            if item_period == period
        }
        for node in nodes:
            base_delta[(period, node)] = sum(
                node_case_delta.get((*case, period, node), 0.0) for case in cases
            ) / len(cases)
    maximum_base = max(base_delta.items(), key=lambda item: abs(item[1]), default=None)

    published_delta: dict[tuple[str, str], float] = {}
    if seconds:
        for period, node in base_delta:
            cases = period_cases[period]
            denominator = sum(seconds.get((case[0], period), 0.0) for case in cases)
            if denominator:
                published_delta[(period, node)] = sum(
                    seconds.get((case[0], period), 0.0)
                    * node_case_delta.get((*case, period, node), 0.0)
                    for case in cases
                ) / denominator
    maximum_published = max(
        published_delta.items(), key=lambda item: abs(item[1]), default=None
    )
    return {
        "date": day.name,
        "year": year,
        "case_count": len({identity for cases in period_cases.values() for identity in cases}),
        "passive_zero_flow_endpoint_count": sum(side_counts.values()),
        "endpoint_counts": dict(sorted(side_counts.items())),
        "load_endpoint_fraction": (
            side_counts[EndpointSide.LOAD.value]
            / max(1, side_counts[EndpointSide.LOAD.value] + side_counts[EndpointSide.EXPORT.value])
        ),
        "projected_endpoint_counts": dict(sorted(projected_endpoint_counts.items())),
        "load_endpoint_node_projected_count": projected_load_observations,
        "load_endpoint_bus_only_count": unprojected_load_observations,
        "load_endpoint_node_counts": dict(sorted(load_endpoint_node_counts.items())),
        "affected_node_case_count": len(node_case_delta),
        "affected_nodes": sorted({key[3] for key in node_case_delta}),
        "maximum_new_bus_difference": _maximum_payload(maximum_bus),
        "maximum_new_node_case_difference": _maximum_mapping_payload(maximum_node),
        "maximum_new_base_node_difference": _maximum_mapping_payload(maximum_base),
        "maximum_new_published_difference": _maximum_mapping_payload(maximum_published),
    }


def _period_from_datetime(results: Path, date_time: str) -> str:
    key = (results, date_time.casefold())
    if key not in _PERIOD_CACHE:
        rows = _read_csv(_only(results, "*base_node_results.csv"))
        _PERIOD_CACHE.update(
            ((results, row["DateTime"].casefold()), row["TP"]) for row in rows
        )
    return _PERIOD_CACHE[key]


def _maximum_payload(
    item: tuple[float, tuple[str, ...]] | None,
) -> dict[str, Any] | None:
    if item is None:
        return None
    value, identity = item
    return {"absolute_difference": abs(value), "signed_difference": value, "identity": identity}


def _maximum_mapping_payload(
    item: tuple[tuple[str, ...], float] | None,
) -> dict[str, Any] | None:
    if item is None:
        return None
    identity, value = item
    return {"absolute_difference": abs(value), "signed_difference": value, "identity": identity}


def corpus_scope(day_count: int) -> str:
    return f"All {day_count} deterministic CPLEX reference-corpus days"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    days = []
    for year_dir in sorted(path for path in args.corpus.iterdir() if path.name.isdigit()):
        for day in sorted(path for path in year_dir.iterdir() if path.is_dir()):
            days.append(
                analyze_day(
                    day,
                    year=int(year_dir.name),
                    system_directory=args.system_directory,
                )
            )
    payload = {
        "schema_version": 1,
        "profile": "cplex-passive-zero-flow-endpoint-analysis-v1",
        "scope": corpus_scope(len(days)),
        "days": days,
        "totals": {
            "case_count": sum(day["case_count"] for day in days),
            "passive_zero_flow_endpoint_count": sum(
                day["passive_zero_flow_endpoint_count"] for day in days
            ),
            "export_endpoint_count": sum(
                day["endpoint_counts"].get("export", 0) for day in days
            ),
            "load_endpoint_count": sum(
                day["endpoint_counts"].get("load", 0) for day in days
            ),
            "ambiguous_endpoint_count": sum(
                day["endpoint_counts"].get("ambiguous", 0) for day in days
            ),
            "affected_node_case_count": sum(
                day["affected_node_case_count"] for day in days
            ),
            "load_endpoint_node_projected_count": sum(
                day["load_endpoint_node_projected_count"] for day in days
            ),
            "load_endpoint_bus_only_count": sum(
                day["load_endpoint_bus_only_count"] for day in days
            ),
            "affected_nodes": sorted(
                {node for day in days for node in day["affected_nodes"]}
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
