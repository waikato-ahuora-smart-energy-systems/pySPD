"""Compare streamed PySPD solver-path results with a CPLEX vSPD day."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from pyspd.reporting import _daily_definitions
from pyspd.reserve import RESERVE_FORMULATION_ID
from tools.gate12.report_crosswalk import _TABLE_RULES
from tools.gate12.report_row_parity import ReportRowParityValidator

_RAW_TABLES = {
    "BidResults_TP": "*raw_BidResults_TP.csv",
    "BrConstraintResults_TP": "*raw_BrConstraintResults_TP.csv",
    "BranchResults_TP": "*raw_BranchResults_TP.csv",
    "BusResults_TP": "*raw_BusResults_TP.csv",
    "IslandResults_TP": "*raw_IslandResults_TP.csv",
    "MNodeConstraintResults_TP": "*raw_MNodeConstraintResults_TP.csv",
    "RiskResults_TP": "*raw_RiskResults_TP.csv",
    "SummaryResults_TP": "*raw_SummaryResults_TP.csv",
    "OfferResults_TP": "*base_offer_results.csv",
    "ReserveResults_TP": "*base_reserve_results.csv",
    "PublishedEnergyPrices_TP": "*raw_PublishedEnergyPrices_TP.csv",
    "PublishedReservePrices_TP": "*raw_PublishedReservePrices_TP.csv",
}

_PUBLISHED_TABLES = {
    "PublishedEnergyPrices_TP",
    "PublishedReservePrices_TP",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--year", required=True, type=int, choices=(2019, 2023))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    reference = _load_reference(args.results, year=args.year)
    profiles = []
    for run in benchmark["runs"]:
        records = tuple(
            json.loads(line)
            for line in Path(run["records_path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        profiles.append(
            _compare_profile(
                run,
                records,
                reference,
                year=args.year,
                benchmark_schema_version=(
                    int(benchmark["schema_version"]) if args.year == 2019 else 5
                ),
            )
        )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "profile": "pyspd-cplex-mapped-complete-day-comparison-v1",
        "scope": (
            "All CPLEX rows and fields having an implemented PySPD report "
            "crosswalk, plus independent model validation and solver-path parity."
        ),
        "benchmark_sha256": _sha256(args.benchmark),
        "year": args.year,
        "results_directory": str(args.results),
        "profiles": profiles,
    }
    payload["logical_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "profiles": [
                    {
                        "profile": item["profile"],
                        "passed": item["passed"],
                        "case_count": item["case_count"],
                        "compared_value_count": item["compared_value_count"],
                        "above_precision_count": item["above_precision_count"],
                        "maximum_absolute_error": item["maximum_absolute_error"],
                    }
                    for item in profiles
                ],
            },
            sort_keys=True,
        )
    )


def _load_reference(results: Path, *, year: int) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for table, pattern in _RAW_TABLES.items():
        matches = tuple(results.glob(pattern))
        if not matches:
            continue
        if len(matches) != 1:
            raise ValueError(f"expected one {table} file, found {len(matches)}")
        with matches[0].open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            rows = tuple(dict(row) for row in reader)
        by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        by_datetime: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if row.get("CaseID"):
                by_case[row["CaseID"]].append(row)
            if row.get("DateTime"):
                by_datetime[row["DateTime"].casefold()].append(row)
        loaded[table] = {
            "fields": fields,
            "rows": rows,
            "by_case": dict(by_case),
            "by_datetime": dict(by_datetime),
        }
    if year == 2019:
        matches = tuple(results.glob("*base_node_results.csv"))
        if len(matches) != 1:
            raise ValueError("2019 reference requires one base node result file")
        with matches[0].open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            rows = tuple(dict(row) for row in reader)
        node_by_datetime: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            node_by_datetime[row["DateTime"].casefold()].append(row)
        loaded["NodeResults_TP"] = {
            "fields": fields,
            "rows": rows,
            "by_case": {},
            "by_datetime": dict(node_by_datetime),
        }
    else:
        matches = tuple(results.glob("*base_node_results.csv"))
        if len(matches) != 1:
            raise ValueError("2023 reference requires one base node result file")
        with matches[0].open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            rows = tuple(dict(row) for row in reader)
        loaded["Base_NodeResults_TP"] = {
            "fields": fields,
            "rows": rows,
            "by_case": {},
            "by_datetime": {},
        }
    return loaded


def _compare_profile(
    run: dict[str, Any],
    records: tuple[dict[str, Any], ...],
    reference: dict[str, dict[str, Any]],
    *,
    year: int,
    benchmark_schema_version: int = 5,
) -> dict[str, Any]:
    validator = ReportRowParityValidator()
    compared = missing = extra = above = certified = 0
    maximum = Decimal(0)
    case_failures: list[dict[str, Any]] = []
    table_totals: dict[str, dict[str, Any]] = {}
    for record in records:
        reference_payload = _case_reference(reference, record, year=year)
        candidate_payload = _case_candidate(
            record,
            reference_payload,
            normalize_v4_island_load=benchmark_schema_version < 5,
        )
        result = validator.compare(
            case_id=record["case_id"],
            reference=json.dumps(reference_payload, sort_keys=True).encode(),
            candidate=json.dumps(candidate_payload, sort_keys=True).encode(),
        )
        for table in result.tables:
            compared += table.compared_value_count
            missing += table.missing_identity_count
            extra += table.extra_identity_count
            above += table.above_precision_count
            certified += table.certified_difference_count
            maximum = max(maximum, Decimal(table.maximum_absolute_error))
            _accumulate_table_total(table_totals, table)
        if not result.passed and len(case_failures) < 20:
            case_failures.append(result.to_dict())
    published_result = _compare_published(run, reference)
    daily_results = (
        _compare_base_node(records, reference),
        published_result,
    )
    for daily_result in daily_results:
        if daily_result is None:
            continue
        for table in daily_result.tables:
            compared += table.compared_value_count
            missing += table.missing_identity_count
            extra += table.extra_identity_count
            above += table.above_precision_count
            certified += table.certified_difference_count
            maximum = max(maximum, Decimal(table.maximum_absolute_error))
            _accumulate_table_total(table_totals, table)
        if not daily_result.passed and len(case_failures) < 20:
            case_failures.append(daily_result.to_dict())
    complete = bool(run.get("completed")) and len(records) == run.get("case_count")
    passed = bool(
        complete
        and run.get("all_solves_optimal")
        and run.get("independent_validation_passed")
        and records
        and not missing
        and not extra
        and not above
        and not case_failures
    )
    return {
        "profile": run["profile"],
        "passed": passed,
        "complete": complete,
        "case_count": len(records),
        "all_solves_optimal": bool(run.get("all_solves_optimal")),
        "independent_validation_passed": bool(run.get("independent_validation_passed")),
        "compared_value_count": compared,
        "missing_identity_count": missing,
        "extra_identity_count": extra,
        "certified_difference_count": certified,
        "above_precision_count": above,
        "maximum_absolute_error": format(maximum, "f"),
        "tables": [table_totals[name] for name in sorted(table_totals)],
        "failure_examples": case_failures,
    }


def _accumulate_table_total(totals: dict[str, dict[str, Any]], table: Any) -> None:
    total = totals.setdefault(
        table.reference_table,
        {
            "reference_table": table.reference_table,
            "candidate_table": table.candidate_table,
            "compared_value_count": 0,
            "missing_identity_count": 0,
            "extra_identity_count": 0,
            "certified_difference_count": 0,
            "above_precision_count": 0,
            "maximum_absolute_error": "0",
        },
    )
    for name in (
        "compared_value_count",
        "missing_identity_count",
        "extra_identity_count",
        "certified_difference_count",
        "above_precision_count",
    ):
        total[name] += int(getattr(table, name))
    total["maximum_absolute_error"] = format(
        max(
            Decimal(total["maximum_absolute_error"]),
            Decimal(table.maximum_absolute_error),
        ),
        "f",
    )


def _case_reference(
    reference: dict[str, dict[str, Any]],
    record: dict[str, Any],
    *,
    year: int,
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for table, raw in reference.items():
        if table in {*_PUBLISHED_TABLES, "Base_NodeResults_TP"}:
            continue
        if table == "NodeResults_TP":
            selected = [
                {
                    "CaseID": record["case_id"],
                    **row,
                    "DateTime": record["date_time"],
                }
                for row in raw["by_datetime"].get(
                    record["date_time"].casefold(), ()
                )
            ]
        elif year == 2023:
            selected = list(raw["by_case"].get(record["case_id"], ()))
        else:
            selected = [
                {"CaseID": record["case_id"], **row}
                for row in raw["by_datetime"].get(
                    record["date_time"].casefold(), ()
                )
            ]
        if not selected:
            continue
        candidate_name, rules = _TABLE_RULES[table]
        if year == 2019 and table in {"BidResults_TP", "OfferResults_TP"}:
            identity = "Bid" if table == "BidResults_TP" else "Offer"
            candidate_identity = identity.casefold()
            traders = {
                row[candidate_identity]: row["trader"]
                for row in record["reports"][candidate_name]
            }
            for row in selected:
                row["Trader"] = traders[row[identity]]
            raw_fields = (*raw["fields"], "Trader")
        elif table == "NodeResults_TP":
            raw_fields = ("CaseID", *raw["fields"])
        else:
            raw_fields = raw["fields"]
        candidate_fields = set(_candidate_fields(candidate_name))
        admitted = {
            rule.reference
            for rule in rules
            if set(rule.candidate).issubset(candidate_fields)
        }
        fields = tuple(
            field
            for field in (("CaseID", *raw_fields) if year == 2019 else raw_fields)
            if field in admitted
        )
        payload[table] = {
            "fields": list(dict.fromkeys(fields)),
            "rows": [
                {field: row[field] for field in dict.fromkeys(fields)}
                for row in selected
            ],
        }
    return payload


def _compare_published(
    run: dict[str, Any], reference: dict[str, dict[str, Any]]
) -> Any | None:
    tables = {
        name: {"fields": payload["fields"], "rows": payload["rows"]}
        for name, payload in reference.items()
        if name in _PUBLISHED_TABLES
    }
    if not tables:
        return None
    candidate_rows = run.get("published_price_rows", [])
    candidate = {
        "published_price": {
            "field_order": list(_candidate_fields("published_price")),
            "rows": candidate_rows,
        }
    }
    return ReportRowParityValidator().compare(
        case_id="published-day",
        reference=json.dumps(tables, sort_keys=True).encode(),
        candidate=json.dumps(candidate, sort_keys=True).encode(),
    )


def _compare_base_node(
    records: tuple[dict[str, Any], ...], reference: dict[str, dict[str, Any]]
) -> Any | None:
    raw = reference.get("Base_NodeResults_TP")
    if raw is None:
        return None
    fields = (
        "CaseID",
        "DateTime",
        "Period",
        "Node",
        "Generation (MW)",
        "Load (MW)",
        "Price ($/MWh)",
    )
    reference_rows = [
        {
            "CaseID": "base",
            "DateTime": row["DateTime"],
            "Period": row["TP"],
            "Node": row["Node"],
            "Generation (MW)": row["Generation (MW)"],
            "Load (MW)": row["Load (MW)"],
            "Price ($/MWh)": row["Price ($/MWh)"],
        }
        for row in raw["rows"]
    ]
    reference_payload = {
        "Base_NodeResults_TP": {"fields": list(fields), "rows": reference_rows}
    }
    candidate_payload = {
        "node": {
            "field_order": list(_candidate_fields("node")),
            "rows": _base_node_candidate_rows(records, raw["rows"]),
        }
    }
    return ReportRowParityValidator().compare(
        case_id="base-node-day",
        reference=json.dumps(reference_payload, sort_keys=True).encode(),
        candidate=json.dumps(candidate_payload, sort_keys=True).encode(),
    )


def _base_node_candidate_rows(
    records: tuple[dict[str, Any], ...],
    reference_rows: tuple[dict[str, str], ...],
) -> list[dict[str, str]]:
    case_count: dict[str, int] = defaultdict(int)
    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {
            "generation_mw": 0.0,
            "load_mw": 0.0,
            "price_nzd_per_mwh": 0.0,
        }
    )
    for record in records:
        trading_period = record["trading_period"]
        case_count[trading_period] += 1
        for row in record["reports"]["node"]:
            values = totals[(trading_period, row["node"])]
            for field in values:
                values[field] += float(row[field])
    output = []
    for reference in reference_rows:
        trading_period = reference["TP"]
        node = reference["Node"]
        divisor = case_count.get(trading_period, 0)
        aggregate_values = totals.get((trading_period, node))
        if not divisor or aggregate_values is None:
            continue
        output.append(
            {
                "case_id": "base",
                "date_time": reference["DateTime"],
                "node": node,
                **{
                    field: format(value / divisor, ".17g")
                    for field, value in aggregate_values.items()
                },
            }
        )
    return output


def _case_candidate(
    record: dict[str, Any],
    reference: dict[str, dict[str, Any]],
    *,
    normalize_v4_island_load: bool,
) -> dict[str, dict[str, Any]]:
    candidate_names = {_TABLE_RULES[name][0] for name in reference}
    reports = record["reports"]
    if normalize_v4_island_load and "island" in candidate_names:
        reports = dict(reports)
        reports["island"] = [
            {
                **row,
                "load_mw": format(
                    float(row["load_mw"]) - float(row["bid_load_mw"]), ".17g"
                ),
            }
            for row in reports["island"]
        ]
    return {
        name: {
            "field_order": list(_candidate_fields(name)),
            "rows": reports[name],
        }
        for name in sorted(candidate_names)
    }


def _candidate_fields(name: str) -> tuple[str, ...]:
    definitions = _daily_definitions(RESERVE_FORMULATION_ID)
    return tuple(field.name for field in definitions[name].fields)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
