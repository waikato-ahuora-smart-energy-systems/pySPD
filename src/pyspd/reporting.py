"""Formulation-selected, deterministic Gate 9 result and report contracts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar

import pyomo.environ as pyo

from pyspd.orchestration import DailyRunResult, PriceTrace, SolveObservation
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from pyspd.v16.compatibility import SPD16_FORMULATION_ID


class ReportError(ValueError):
    """A report contract, artifact, or formulation selection is invalid."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


@dataclass(frozen=True, slots=True)
class ArtifactProvenance:
    formulation_id: str
    source_sha256: str
    configuration_sha256: str
    code_version: str
    dependency_lock_sha256: str
    solver_profile: str
    environment_fingerprint: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.formulation_id,
                self.code_version,
                self.solver_profile,
                self.environment_fingerprint,
            )
        ):
            raise ReportError("provenance text fields must not be empty")
        for name in (
            "source_sha256",
            "configuration_sha256",
            "dependency_lock_sha256",
        ):
            if not _valid_sha256(getattr(self, name)):
                raise ReportError(f"{name} must be a lowercase SHA-256")

    @property
    def logical_sha256(self) -> str:
        return _sha256(_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, str]:
        return {
            "code_version": self.code_version,
            "configuration_sha256": self.configuration_sha256,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "environment_fingerprint": self.environment_fingerprint,
            "formulation_id": self.formulation_id,
            "solver_profile": self.solver_profile,
            "source_sha256": self.source_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ArtifactProvenance:
        return cls(**{name: str(value[name]) for name in cls.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class ReportField:
    name: str
    unit: str = "dimensionless"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.unit.strip():
            raise ReportError("report field name and unit must not be empty")


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    name: str
    formulation_id: str
    fields: tuple[ReportField, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))
        if not self.name.strip() or not self.formulation_id.strip():
            raise ReportError("report name and formulation must not be empty")
        names = [field.name for field in self.fields]
        if not names or len(names) != len(set(names)):
            raise ReportError(f"report {self.name!r} has empty or duplicate fields")


@dataclass(frozen=True, slots=True)
class ReportTable:
    definition: ReportDefinition
    rows: tuple[Mapping[str, str], ...]

    def __post_init__(self) -> None:
        expected = tuple(field.name for field in self.definition.fields)
        normalized: list[Mapping[str, str]] = []
        for row in self.rows:
            if tuple(row) != expected:
                raise ReportError(
                    f"{self.definition.name} row fields {tuple(row)!r} != {expected!r}"
                )
            normalized.append(
                MappingProxyType({key: str(value) for key, value in row.items()})
            )
        object.__setattr__(self, "rows", tuple(normalized))

    def csv_bytes(self) -> bytes:
        stream = io.StringIO(newline="")
        names = [field.name for field in self.definition.fields]
        writer = csv.DictWriter(stream, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows)
        return stream.getvalue().encode()


@dataclass(frozen=True, slots=True)
class ReportManifest:
    formulation_id: str
    provenance_sha256: str
    files: Mapping[str, str]
    logical_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))


@dataclass(frozen=True, slots=True)
class ReportBundle:
    provenance: ArtifactProvenance
    tables: Mapping[str, ReportTable]

    def __post_init__(self) -> None:
        tables = dict(self.tables)
        if set(tables) != {table.definition.name for table in tables.values()}:
            raise ReportError("table keys must match report definition names")
        if any(
            table.definition.formulation_id != self.provenance.formulation_id
            for table in tables.values()
        ):
            raise ReportError("report formulation differs from provenance")
        object.__setattr__(self, "tables", MappingProxyType(tables))

    def write(self, directory: Path) -> ReportManifest:
        directory.mkdir(parents=True, exist_ok=True)
        file_hashes: dict[str, str] = {}
        definitions: dict[str, object] = {}
        for name, table in sorted(self.tables.items()):
            filename = f"{name}.csv"
            csv_payload = table.csv_bytes()
            (directory / filename).write_bytes(csv_payload)
            file_hashes[filename] = _sha256(csv_payload)
            definitions[name] = {
                "fields": [
                    {"name": field.name, "unit": field.unit}
                    for field in table.definition.fields
                ],
                "row_count": len(table.rows),
            }
        logical_payload = {
            "definitions": definitions,
            "files": file_hashes,
            "formulation_id": self.provenance.formulation_id,
            "provenance": self.provenance.to_dict(),
            "schema_version": 1,
        }
        logical_sha256 = _sha256(_json_bytes(logical_payload))
        manifest_payload = {**logical_payload, "logical_sha256": logical_sha256}
        (directory / "manifest.json").write_bytes(_json_bytes(manifest_payload))
        return ReportManifest(
            self.provenance.formulation_id,
            self.provenance.logical_sha256,
            file_hashes,
            logical_sha256,
        )

    @classmethod
    def read(cls, directory: Path) -> ReportBundle:
        manifest_path = directory / "manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReportError(f"cannot read report manifest: {error}") from error
        expected_logical = payload.pop("logical_sha256", None)
        actual_logical = _sha256(_json_bytes(payload))
        if expected_logical != actual_logical:
            raise ReportError("report manifest logical hash mismatch")
        provenance = ArtifactProvenance.from_dict(payload["provenance"])
        tables: dict[str, ReportTable] = {}
        for name, item in sorted(payload["definitions"].items()):
            filename = f"{name}.csv"
            raw = (directory / filename).read_bytes()
            if _sha256(raw) != payload["files"][filename]:
                raise ReportError(f"report file hash mismatch: {filename}")
            fields = tuple(
                ReportField(str(field["name"]), str(field["unit"]))
                for field in item["fields"]
            )
            rows = tuple(dict(row) for row in csv.DictReader(io.StringIO(raw.decode())))
            if len(rows) != item["row_count"]:
                raise ReportError(f"report row count mismatch: {filename}")
            definition = ReportDefinition(name, provenance.formulation_id, fields)
            tables[name] = ReportTable(definition, rows)
        return cls(provenance, tables)


@dataclass(frozen=True, slots=True)
class DailyCollectedResults:
    result: DailyRunResult
    provenance: ArtifactProvenance


class DailyResultSchema:
    supported_formulations: ClassVar[frozenset[str]] = frozenset()

    def collect(
        self, result: DailyRunResult, provenance: ArtifactProvenance
    ) -> DailyCollectedResults:
        if provenance.formulation_id not in self.supported_formulations:
            raise ReportError("result schema does not support formulation")
        if result.configuration_sha256 != provenance.configuration_sha256:
            raise ReportError("result and provenance configuration hashes differ")
        return DailyCollectedResults(result, provenance)


class DailyReportRenderer:
    supported_formulations: ClassVar[frozenset[str]] = frozenset()

    def render(self, results: DailyCollectedResults) -> ReportBundle:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DailyReportProfile:
    formulation_id: str
    result_schema: type[DailyResultSchema]
    report_renderer: type[DailyReportRenderer]


class DailyReportRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, DailyReportProfile] = {}

    def register(self, profile: DailyReportProfile) -> None:
        if profile.formulation_id in self._profiles:
            raise ValueError(f"duplicate report profile: {profile.formulation_id}")
        for extension in (profile.result_schema, profile.report_renderer):
            if profile.formulation_id not in extension.supported_formulations:
                raise ValueError("report extension does not support formulation")
        self._profiles[profile.formulation_id] = profile

    def resolve(self, formulation_id: str) -> DailyReportProfile:
        try:
            return self._profiles[formulation_id]
        except KeyError as error:
            raise ValueError(f"unknown report profile: {formulation_id}") from error


_V5 = frozenset({RESERVE_FORMULATION_ID})


def _reported_bus_price(
    bus_key: tuple[str, ...],
    accepted: SolveObservation,
    prices: PriceTrace,
) -> float:
    """Apply pinned-vSPD's dead-node bus report projection."""

    allocations = accepted.node_bus_allocation
    has_dead_node = any(
        allocation_key[:-1] in prices.dead_nodes
        and allocation_key[:2] + (allocation_key[-1],) == bus_key
        and float(weight) != 0.0
        for allocation_key, weight in allocations.items()
    )
    if not has_dead_node:
        return float(prices.repaired_bus[bus_key])
    return sum(
        float(weight) * float(prices.node[allocation_key[:-1]])
        for allocation_key, weight in allocations.items()
        if allocation_key[:2] + (allocation_key[-1],) == bus_key
    )


class V5DailyResultSchema(DailyResultSchema):
    supported_formulations = _V5


class V5DailyReportRenderer(DailyReportRenderer):
    supported_formulations = _V5

    def render(self, results: DailyCollectedResults) -> ReportBundle:
        if results.provenance.formulation_id not in self.supported_formulations:
            raise ReportError("v5 renderer received another formulation")
        definitions = _daily_definitions(results.provenance.formulation_id)
        rows: dict[str, list[dict[str, str]]] = {name: [] for name in definitions}
        run = results.result
        for case in run.cases:
            accepted = case.accepted
            prices = case.prices
            assert accepted is not None and prices is not None
            base = {
                "case_id": case.specification.case_id,
                "date_time": case.specification.date_time,
            }
            rows["summary"].append(
                {
                    **base,
                    "status": case.status.value,
                    "solve_count": str(case.solve_count),
                    "objective_nzd": _number(accepted.objective),
                    "formulation_id": results.provenance.formulation_id,
                }
            )
            for offer_name, value in sorted(accepted.generation.items()):
                rows["offer"].append(
                    {
                        **base,
                        "offer": offer_name,
                        "generation_mw": _number(value),
                    }
                )
            for bus_key, raw in sorted(prices.raw_bus.items()):
                rows["bus"].append(
                    {
                        **base,
                        "bus": bus_key[-1],
                        "raw_price_nzd_per_mwh": _number(raw),
                        "repaired_price_nzd_per_mwh": _number(
                            _reported_bus_price(bus_key, accepted, prices)
                        ),
                        "disconnected": _boolean(bus_key in prices.disconnected_buses),
                        "invalid": _boolean(bus_key in prices.invalid_buses),
                    }
                )
            for node_key, value in sorted(prices.node.items()):
                rows["node"].append(
                    {
                        **base,
                        "node": node_key[-1],
                        "price_nzd_per_mwh": _number(value),
                        "dead": _boolean(node_key in prices.dead_nodes),
                        "price_source": prices.dead_node_price_source.get(
                            node_key, node_key
                        )[-1],
                    }
                )
            for reserve_key, value in sorted(prices.reserve.items()):
                island = reserve_key[-2] if len(reserve_key) >= 2 else ""
                reserve_class = reserve_key[-1]
                reserve_row = {
                    **base,
                    "island": island,
                    "reserve_class": reserve_class,
                    "price_nzd_per_mwh": _number(value),
                }
                rows["reserve"].append(reserve_row)
                rows["island"].append(reserve_row.copy())
            _model_rows(rows, accepted.solve_payload, base)
            for event in case.events:
                rows["audit"].append(
                    {
                        **base,
                        "sequence": str(event.sequence),
                        "event": event.kind.value,
                        "solve_loop": ""
                        if event.solve_loop is None
                        else str(event.solve_loop),
                        "details_json": json.dumps(
                            dict(event.details), sort_keys=True, separators=(",", ":")
                        ),
                    }
                )
        if run.published is not None:
            for (period, node), value in sorted(run.published.energy.items()):
                rows["published_price"].append(
                    {
                        "trading_period": period,
                        "location": node,
                        "product": "energy",
                        "price_nzd_per_mwh": _number(value),
                        "publication_seconds": _number(
                            run.published.total_seconds[period]
                        ),
                    }
                )
            for (period, island, reserve_class), value in sorted(
                run.published.reserve.items()
            ):
                rows["published_price"].append(
                    {
                        "trading_period": period,
                        "location": island,
                        "product": reserve_class,
                        "price_nzd_per_mwh": _number(value),
                        "publication_seconds": _number(
                            run.published.total_seconds[period]
                        ),
                    }
                )
        tables = {
            name: ReportTable(definition, tuple(rows[name]))
            for name, definition in definitions.items()
        }
        return ReportBundle(results.provenance, tables)


_V16 = frozenset({SPD16_FORMULATION_ID})


class Spd16DailyResultSchema(DailyResultSchema):
    supported_formulations = _V16


class Spd16DailyReportRenderer(V5DailyReportRenderer):
    """Separate v16 renderer class using the common deterministic table shape."""

    supported_formulations = _V16


def daily_report_registry() -> DailyReportRegistry:
    registry = DailyReportRegistry()
    registry.register(
        DailyReportProfile(
            RESERVE_FORMULATION_ID,
            V5DailyResultSchema,
            V5DailyReportRenderer,
        )
    )
    registry.register(
        DailyReportProfile(
            SPD16_FORMULATION_ID,
            Spd16DailyResultSchema,
            Spd16DailyReportRenderer,
        )
    )
    return registry


def _fields(*values: tuple[str, str]) -> tuple[ReportField, ...]:
    return tuple(ReportField(name, unit) for name, unit in values)


def _daily_definitions(formulation_id: str) -> dict[str, ReportDefinition]:
    common = (("case_id", "id"), ("date_time", "datetime"))
    specifications: dict[str, tuple[tuple[str, str], ...]] = {
        "summary": (
            *common,
            ("status", "state"),
            ("solve_count", "count"),
            ("objective_nzd", "NZD"),
            ("formulation_id", "id"),
        ),
        "island": (
            *common,
            ("island", "id"),
            ("reserve_class", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
        ),
        "bus": (
            *common,
            ("bus", "id"),
            ("raw_price_nzd_per_mwh", "NZD/MWh"),
            ("repaired_price_nzd_per_mwh", "NZD/MWh"),
            ("disconnected", "boolean"),
            ("invalid", "boolean"),
        ),
        "node": (
            *common,
            ("node", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
            ("dead", "boolean"),
            ("price_source", "id"),
        ),
        "offer": (*common, ("offer", "id"), ("generation_mw", "MW")),
        "bid": (*common, ("bid", "id"), ("purchase_mw", "MW")),
        "reserve": (
            *common,
            ("island", "id"),
            ("reserve_class", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
        ),
        "risk": (*common, ("risk", "id"), ("quantity_mw", "MW")),
        "branch": (*common, ("branch", "id"), ("flow_mw", "MW")),
        "constraint": (
            *common,
            ("constraint", "id"),
            ("index", "id"),
            ("body", "value"),
            ("lower", "value"),
            ("upper", "value"),
        ),
        "published_price": (
            ("trading_period", "id"),
            ("location", "id"),
            ("product", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
            ("publication_seconds", "s"),
        ),
        "audit": (
            *common,
            ("sequence", "count"),
            ("event", "state"),
            ("solve_loop", "count"),
            ("details_json", "json"),
        ),
    }
    return {
        name: ReportDefinition(name, formulation_id, _fields(*fields))
        for name, fields in specifications.items()
    }


def _number(value: Any | None) -> str:
    if value is None:
        return ""
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ReportError("reports cannot contain non-finite numbers")
    return format(numeric, ".17g")


def _boolean(value: bool) -> str:
    return "true" if value else "false"


def _component_values(component: Any) -> list[tuple[str, float]]:
    output: list[tuple[str, float]] = []
    for index in component:
        value = pyo.value(component[index], exception=False)
        if value is not None:
            key = index if isinstance(index, tuple) else (index,)
            output.append(("|".join(str(part) for part in key), float(value)))
    return output


def _model_rows(
    rows: dict[str, list[dict[str, str]]], solve_payload: Any, base: Mapping[str, str]
) -> None:
    solved = getattr(solve_payload, "pricing_model", None)
    if solved is None:
        solved = getattr(solve_payload, "primary_model", None)
    if solved is None:
        return
    artifacts = solved.artifacts.values
    for artifact, report, identity, quantity in (
        ("purchase", "bid", "bid", "purchase_mw"),
        ("island_risk", "risk", "risk", "quantity_mw"),
        ("branch_flow", "branch", "branch", "flow_mw"),
        ("hvdc_flow", "branch", "branch", "flow_mw"),
    ):
        component = artifacts.get(artifact)
        if component is None:
            continue
        for key, value in _component_values(component):
            rows[report].append({**base, identity: key, quantity: _number(value)})
    network_data = artifacts.get("network_data")
    reported_branch_identities = {row["branch"] for row in rows["branch"]}
    for branch in sorted(getattr(network_data, "report_branches", ())):
        identity = "|".join(str(part) for part in branch)
        if identity not in reported_branch_identities:
            rows["branch"].append({**base, "branch": identity, "flow_mw": "0"})
    for component in solved.model.component_objects(
        pyo.Constraint, active=True, descend_into=True
    ):
        for index in component:
            item = component[index]
            if not item.active:
                continue
            index_text = "|".join(
                str(part) for part in (index if isinstance(index, tuple) else (index,))
            )
            rows["constraint"].append(
                {
                    **base,
                    "constraint": component.name,
                    "index": index_text,
                    "body": _number(pyo.value(item.body, exception=False)),
                    "lower": _number(pyo.value(item.lower, exception=False)),
                    "upper": _number(pyo.value(item.upper, exception=False)),
                }
            )
