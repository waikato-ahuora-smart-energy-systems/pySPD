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
    """Apply pinned-vSPD's unresolved-dead-node bus report projection."""

    allocations = accepted.node_bus_allocation
    has_dead_node = any(
        allocation_key[:-1] in prices.dead_nodes
        and allocation_key[:-1] not in prices.dead_node_price_source
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


def _branch_report_direction(flow: float) -> str:
    """Choose the vSPD report direction without amplifying LP zero noise."""

    return "forward" if flow >= -1.0e-9 else "backward"


def _island_report_load(
    network: Any,
    period: tuple[str, str],
    buses: set[str],
    bid_load: float,
) -> float:
    """Project vSPD island load independently of duplicated bus bid rows."""

    return (
        sum(
            float(network.node_bus_allocation.get((*period, node, bus), 0.0))
            * float(network.node_load[*period, node])
            for ca, dt, node, bus in network.node_bus
            if (ca, dt) == period and bus in buses
        )
        + bid_load
    )


class V5DailyResultSchema(DailyResultSchema):
    supported_formulations = _V5


def _pricing_model(solve_payload: Any) -> Any | None:
    pricing = getattr(solve_payload, "pricing_model", None)
    if pricing is not None:
        return pricing
    return getattr(solve_payload, "primary_model", None)


def _index_tuple(index: Any) -> tuple[str, ...]:
    values = index if isinstance(index, tuple) else (index,)
    return tuple(str(value) for value in values)


def _component_value(component: Any, key: tuple[str, ...]) -> float:
    try:
        value = pyo.value(component[key], exception=False)
    except KeyError as error:
        raise ReportError(f"report component is missing {key!r}") from error
    if value is None or not math.isfinite(float(value)):
        raise ReportError(f"report component is not finite at {key!r}")
    return float(value)


def _optional_component_value(component: Any, key: tuple[str, ...]) -> float:
    try:
        value = pyo.value(component[key], exception=False)
    except KeyError:
        return 0.0
    if value is None or not math.isfinite(float(value)):
        raise ReportError(f"report component is not finite at {key!r}")
    return float(value)


def _component_sum(component: Any, prefix: tuple[str, ...]) -> float:
    return sum(
        _component_value(component, _index_tuple(index))
        for index in component
        if _index_tuple(index)[: len(prefix)] == prefix
    )


class V5SummaryReportProjector:
    """Project the pinned-vSPD trading-period summary from registered handles."""

    _VIOLATION_COMPONENTS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("surplus_generation_mw", "balance_surplus"),
        ("surplus_branch_flow_mw", "branch_flow_surplus"),
        ("deficit_ramp_rate_mw", "ramp_deficit"),
        ("surplus_ramp_rate_mw", "ramp_surplus"),
        ("deficit_branch_constraint_mw", "branch_constraint_deficit"),
        ("surplus_branch_constraint_mw", "branch_constraint_surplus"),
        ("deficit_market_node_constraint_mw", "market_node_constraint_deficit"),
        ("surplus_market_node_constraint_mw", "market_node_constraint_surplus"),
    )

    def project(
        self,
        accepted: SolveObservation,
        base: Mapping[str, str],
        *,
        complete: bool,
    ) -> dict[str, str]:
        solved = _pricing_model(accepted.solve_payload)
        if solved is None:
            return {
                **base,
                "status_code": "1" if complete else "0",
                "system_ofv_nzd": _number(accepted.objective),
                "system_cost_nzd": "0",
                "system_benefit_nzd": "0",
                "violation_cost_nzd": "0",
                "deficit_generation_mw": "0",
                "surplus_generation_mw": "0",
                "deficit_reserve_mw": "0",
                "surplus_branch_flow_mw": "0",
                "deficit_ramp_rate_mw": "0",
                "surplus_ramp_rate_mw": "0",
                "deficit_branch_constraint_mw": "0",
                "surplus_branch_constraint_mw": "0",
                "deficit_market_node_constraint_mw": "0",
                "surplus_market_node_constraint_mw": "0",
            }
        artifacts = solved.artifacts.values
        period = (base["case_id"], base["date_time"])
        case = solved.case_data
        economics = getattr(solved.model, "Economics", None)
        period_components = {
            "system_cost_nzd": artifacts.get("system_cost_by_period"),
            "system_benefit_nzd": artifacts.get("system_benefit_by_period"),
            "violation_cost_nzd": artifacts.get("system_penalty_by_period"),
        }
        if economics is not None:
            if period_components["system_cost_nzd"] is None:
                period_components["system_cost_nzd"] = getattr(
                    economics, "SystemCostByPeriod", None
                )
            if period_components["system_benefit_nzd"] is None:
                period_components["system_benefit_nzd"] = getattr(
                    economics, "SystemBenefitByPeriod", None
                )
            if period_components["violation_cost_nzd"] is None:
                period_components["violation_cost_nzd"] = getattr(
                    economics, "SystemPenaltyByPeriod", None
                )
        if any(component is None for component in period_components.values()):
            raise ReportError("period economics handles are unavailable")
        scarcity_constant = sum(
            float(case.scarcity_limit[key]) * float(case.scarcity_price[key])
            for key in case.scarcity_blocks
            if tuple(key)[:2] == period
        )
        values = {
            name: _component_sum(artifacts[component], period)
            for name, component in self._VIOLATION_COMPONENTS
        }
        # vSPD's o_defGenViolation_TP is the sum of bus balance deficit and
        # ENERGYSCARCITYNODE. The latter is the nodal shortfall variable used
        # when energy-scarcity blocks are enabled.
        values["deficit_generation_mw"] = _component_sum(
            artifacts["balance_deficit"], period
        ) + _component_sum(artifacts["energy_scarcity_node"], period)
        values["deficit_reserve_mw"] = _component_sum(
            artifacts["reserve_deficit_ce"], period
        ) + _component_sum(artifacts["reserve_deficit_ece"], period)
        legacy_spd = (
            float(getattr(case, "study_mode", {}).get(period, 0.0)) == 111.0
        )
        system_ofv = (
            _component_value(period_components["system_benefit_nzd"], period)
            - _component_value(period_components["system_cost_nzd"], period)
            - _component_value(period_components["violation_cost_nzd"], period)
            if legacy_spd
            else accepted.objective + scarcity_constant
        )
        return {
            **base,
            "status_code": "1" if complete else "0",
            "system_ofv_nzd": _number(system_ofv),
            "system_cost_nzd": _number(
                _component_value(period_components["system_cost_nzd"], period)
            ),
            "system_benefit_nzd": _number(
                _component_value(period_components["system_benefit_nzd"], period)
            ),
            "violation_cost_nzd": _number(
                _component_value(period_components["violation_cost_nzd"], period)
            ),
            "deficit_generation_mw": _number(values["deficit_generation_mw"]),
            "surplus_generation_mw": _number(values["surplus_generation_mw"]),
            "deficit_reserve_mw": _number(values["deficit_reserve_mw"]),
            "surplus_branch_flow_mw": _number(values["surplus_branch_flow_mw"]),
            "deficit_ramp_rate_mw": _number(values["deficit_ramp_rate_mw"]),
            "surplus_ramp_rate_mw": _number(values["surplus_ramp_rate_mw"]),
            "deficit_branch_constraint_mw": _number(
                values["deficit_branch_constraint_mw"]
            ),
            "surplus_branch_constraint_mw": _number(
                values["surplus_branch_constraint_mw"]
            ),
            "deficit_market_node_constraint_mw": _number(
                values["deficit_market_node_constraint_mw"]
            ),
            "surplus_market_node_constraint_mw": _number(
                values["surplus_market_node_constraint_mw"]
            ),
        }


class V5RiskReportProjector:
    """Project active vSPD risk setters and their complete pricing context."""

    def project(
        self, accepted: SolveObservation, base: Mapping[str, str]
    ) -> tuple[dict[str, str], ...]:
        solved = _pricing_model(accepted.solve_payload)
        if solved is None:
            return ()
        artifacts = solved.artifacts.values
        definitions = artifacts.get("risk_definition_constraints")
        if definitions is None:
            risk_block = getattr(solved.model, "ReserveRisk", None)
            definitions = getattr(risk_block, "_report_definition_constraints", None)
        reserve_data = getattr(solved.case_data, "reserve", None)
        if definitions is None or reserve_data is None:
            return ()
        rows = []
        for identity, constraint in sorted(definitions.items()):
            raw_dual = solved.model.dual.get(constraint, 0.0)
            risk_price = -float(raw_dual)
            if risk_price == 0.0:
                continue
            kind, *raw_key = identity
            key = tuple(raw_key)
            row = self._row(
                kind,
                key,
                risk_price,
                accepted,
                base,
                artifacts,
                reserve_data,
            )
            rows.append(row)
        return tuple(rows)

    def _row(
        self,
        kind: str,
        key: tuple[str, ...],
        risk_price: float,
        accepted: SolveObservation,
        base: Mapping[str, str],
        artifacts: Mapping[str, Any],
        data: Any,
    ) -> dict[str, str]:
        ca, dt, island = key[:3]
        if kind in {"GEN", "RISKGROUP"}:
            setter, reserve_class, risk = key[3:]
        else:
            reserve_class, risk = key[3:]
            setter = kind
        island_risk = (ca, dt, island, reserve_class, risk)
        offers = self._offers(kind, ca, dt, island, setter, risk, data)
        covered_energy = sum(
            _optional_component_value(artifacts["generation"], (ca, dt, offer))
            for offer in offers
        )
        covered_reserve = sum(
            _component_value(artifacts["reserve"], _index_tuple(index))
            for index in artifacts["reserve"]
            if _index_tuple(index)[:2] == (ca, dt)
            and _index_tuple(index)[2] in offers
            and _index_tuple(index)[3] == reserve_class
        )
        covered_fk_band = sum(
            float(data.fk_band.get((ca, dt, offer), 0.0)) for offer in offers
        )
        if kind == "HVDC":
            covered_energy = _component_value(
                artifacts["hvdc_received"], (ca, dt, island)
            )
            covered_reserve = 0.0
            covered_fk_band = float(data.modulation_risk_class.get((ca, dt, risk), 0.0))
            subtractor = _component_value(artifacts["risk_offset"], island_risk)
            shortfall = _optional_component_value(
                artifacts["reserve_shortfall"], island_risk
            )
        elif kind == "MANUAL":
            covered_energy = float(data.risk_minimum.get(island_risk, 0.0))
            covered_reserve = 0.0
            covered_fk_band = 0.0
            subtractor = float(data.free_reserve.get(island_risk, 0.0))
            shortfall = _optional_component_value(
                artifacts["reserve_shortfall"], island_risk
            )
        elif kind == "RISKGROUP":
            subtractor = float(data.free_reserve.get(island_risk, 0.0))
            shortfall = _optional_component_value(
                artifacts["reserve_shortfall_group"], key
            )
        else:
            subtractor = float(data.free_reserve.get(island_risk, 0.0))
            shortfall = _optional_component_value(
                artifacts["reserve_shortfall_unit"], key
            )
        reserve = self._island_reserve(
            artifacts, data, ca, dt, island, reserve_class
        ) + _optional_component_value(artifacts["reserve_share_effective"], island_risk)
        deficit_key = (ca, dt, island, reserve_class)
        deficit = _component_value(
            artifacts["reserve_deficit_ce"], deficit_key
        ) + _component_value(artifacts["reserve_deficit_ece"], deficit_key)
        reserve_price = float(accepted.reserve_prices[deficit_key])
        return {
            **base,
            "island": island,
            "reserve_class": reserve_class,
            "risk_class": "CE" if risk in data.ce_risks else "ECE",
            "risk_type": kind,
            "risk_setter": setter,
            "covered_energy_mw": _number(covered_energy),
            "covered_reserve_mw": _number(covered_reserve),
            "covered_fk_band_mw": _number(covered_fk_band),
            "risk_subtractor_mw": _number(subtractor),
            "reserve_mw": _number(reserve),
            "shortfall_mw": _number(shortfall),
            "deficit_mw": _number(deficit),
            "reserve_price_nzd_per_mwh": _number(reserve_price),
            "risk_price_nzd_per_mwh": _number(risk_price),
        }

    @staticmethod
    def _offers(
        kind: str,
        ca: str,
        dt: str,
        island: str,
        setter: str,
        risk: str,
        data: Any,
    ) -> tuple[str, ...]:
        if kind == "GEN":
            return (setter,)
        if kind == "RISKGROUP":
            return tuple(
                sorted(
                    offer
                    for r_ca, r_dt, group, offer, r_risk in data.risk_group_offer
                    if (r_ca, r_dt, group, r_risk) == (ca, dt, setter, risk)
                )
            )
        return ()

    @staticmethod
    def _island_reserve(
        artifacts: Mapping[str, Any],
        data: Any,
        ca: str,
        dt: str,
        island: str,
        reserve_class: str,
    ) -> float:
        offers = {
            offer
            for r_ca, r_dt, offer, offer_island in data.offer_island
            if (r_ca, r_dt, offer_island) == (ca, dt, island)
        }
        return sum(
            _component_value(artifacts["reserve"], _index_tuple(index))
            for index in artifacts["reserve"]
            if _index_tuple(index)[:2] == (ca, dt)
            and _index_tuple(index)[2] in offers
            and _index_tuple(index)[3] == reserve_class
        )


class V5DetailedReportProjector:
    """Enrich the common rows with the complete pinned-vSPD report surface."""

    _DETAIL_DEFAULTS: ClassVar[dict[str, tuple[str, ...]]] = {
        "offer": ("trader", "fir_mw", "sir_mw"),
        "bid": ("trader", "total_bid_mw"),
        "bus": (
            "generation_mw",
            "load_mw",
            "deficit_mw",
            "surplus_mw",
        ),
        "node": (
            "generation_mw",
            "load_mw",
            "deficit_mw",
            "surplus_mw",
        ),
        "branch": (
            "from_bus",
            "to_bus",
            "capacity_mw",
            "dynamic_loss_mw",
            "fixed_loss_mw",
            "from_bus_price_nzd_per_mwh",
            "to_bus_price_nzd_per_mwh",
            "branch_price_nzd_per_mwh",
            "branch_rentals_nzd",
        ),
        "constraint": ("price_nzd_per_mwh",),
        "reserve": ("required_mw", "violation_mw"),
        "island": (
            "generation_mw",
            "load_mw",
            "bid_load_mw",
            "ac_loss_mw",
            "hvdc_flow_mw",
            "hvdc_loss_mw",
            "reference_price_nzd_per_mwh",
            "required_mw",
            "cleared_mw",
            "share_mw",
            "received_mw",
            "effective_ce_mw",
            "effective_ece_mw",
        ),
    }

    def enrich(
        self,
        rows: dict[str, list[dict[str, str]]],
        accepted: SolveObservation,
        prices: PriceTrace,
        base: Mapping[str, str],
    ) -> None:
        current = {
            table: [
                row
                for row in rows[table]
                if all(row.get(field) == value for field, value in base.items())
            ]
            for table in self._DETAIL_DEFAULTS
        }
        for table, fields in self._DETAIL_DEFAULTS.items():
            for row in current[table]:
                for field in fields:
                    row[field] = ""
        solved = _pricing_model(accepted.solve_payload)
        if solved is None:
            return
        artifacts = solved.artifacts.values
        case = solved.case_data
        network = getattr(case, "network", None)
        reserve_data = getattr(case, "reserve", None)
        hvdc_data = getattr(case, "hvdc", None)
        if network is None:
            return
        period = (base["case_id"], base["date_time"])
        generation = artifacts["generation"]
        purchase = artifacts["purchase"]
        reserve = artifacts.get("reserve")
        scarcity = artifacts["energy_scarcity_node"]
        deficit = artifacts["balance_deficit"]
        surplus = artifacts["balance_surplus"]

        for row in current["offer"]:
            key = (*period, row["offer"])
            row["trader"] = (
                "" if reserve_data is None else reserve_data.offer_trader.get(key, "")
            )
            for reserve_class, field in (("FIR", "fir_mw"), ("SIR", "sir_mw")):
                value = (
                    0.0
                    if reserve is None
                    else sum(
                        _component_value(reserve, _index_tuple(index))
                        for index in reserve
                        if _index_tuple(index)[:3] == key
                        and _index_tuple(index)[3] == reserve_class
                    )
                )
                row[field] = _number(value)
        for row in current["bid"]:
            key = (*period, row["bid"])
            row["trader"] = (
                "" if reserve_data is None else reserve_data.bid_trader.get(key, "")
            )
            row["total_bid_mw"] = _number(
                sum(
                    value for block, value in case.bid_limit.items() if block[:3] == key
                )
            )

        bus_values: dict[str, dict[str, float]] = {}
        for row in current["bus"]:
            bus = row["bus"]
            bus_key = (*period, bus)
            generation_mw = sum(
                network.node_bus_allocation.get((*period, node, bus), 0.0)
                * _component_value(generation, (*period, offer))
                for o_ca, o_dt, offer, node in network.offer_node
                if (o_ca, o_dt) == period and (*period, node, bus) in network.node_bus
            )
            load_mw = sum(
                network.node_bus_allocation.get((*period, node, bus), 0.0)
                * network.node_load[*period, node]
                for n_ca, n_dt, node, n_bus in network.node_bus
                if (n_ca, n_dt, n_bus) == bus_key
            ) + sum(
                _component_value(purchase, (*period, bid))
                for b_ca, b_dt, bid, node in network.bid_node
                if (b_ca, b_dt) == period and (*period, node, bus) in network.node_bus
            )
            deficit_mw = _component_value(deficit, bus_key) + sum(
                network.node_bus_allocation.get((*period, node, bus), 0.0)
                * _component_value(scarcity, (*period, node))
                for n_ca, n_dt, node, n_bus in network.node_bus
                if (n_ca, n_dt, n_bus) == bus_key
            )
            values = {
                "generation_mw": generation_mw,
                "load_mw": load_mw,
                "deficit_mw": deficit_mw,
                "surplus_mw": _component_value(surplus, bus_key),
            }
            bus_values[bus] = values
            row.update({name: _number(value) for name, value in values.items()})

        allocation_totals = {
            bus: sum(
                float(weight)
                for (
                    ca,
                    dt,
                    _node,
                    n_bus,
                ), weight in network.node_bus_allocation.items()
                if (ca, dt, n_bus) == (*period, bus)
            )
            for _ca, _dt, bus in network.buses
            if (_ca, _dt) == period
        }
        for row in current["node"]:
            node = row["node"]
            node_key = (*period, node)
            node_generation = sum(
                _component_value(generation, (*period, offer))
                for o_ca, o_dt, offer, o_node in network.offer_node
                if (o_ca, o_dt, o_node) == node_key
            )
            node_load = network.node_load[node_key] + sum(
                _component_value(purchase, (*period, bid))
                for b_ca, b_dt, bid, b_node in network.bid_node
                if (b_ca, b_dt, b_node) == node_key
            )
            node_deficit = _component_value(scarcity, node_key)
            node_surplus = 0.0
            for n_ca, n_dt, n_node, bus in network.node_bus:
                if (n_ca, n_dt, n_node) != node_key:
                    continue
                total = allocation_totals.get(bus, 0.0)
                weight = (
                    0.0
                    if total <= 0.0
                    else network.node_bus_allocation.get((*period, node, bus), 0.0)
                    / total
                )
                node_deficit += weight * _component_value(deficit, (*period, bus))
                node_surplus += weight * _component_value(surplus, (*period, bus))
            row.update(
                {
                    "generation_mw": _number(node_generation),
                    "load_mw": _number(node_load),
                    "deficit_mw": _number(node_deficit),
                    "surplus_mw": _number(node_surplus),
                }
            )

        self._branches(
            current["branch"], solved, accepted, prices, period, network, hvdc_data
        )
        self._constraints(current["constraint"], solved)
        if reserve_data is not None and reserve is not None:
            self._reserve_and_island(
                current,
                solved,
                accepted,
                prices,
                period,
                network,
                reserve_data,
                hvdc_data,
                bus_values,
            )

    @staticmethod
    def _branches(
        rows: list[dict[str, str]],
        solved: Any,
        accepted: SolveObservation,
        prices: PriceTrace,
        period: tuple[str, str],
        network: Any,
        hvdc_data: Any,
    ) -> None:
        artifacts = solved.artifacts.values
        for row in rows:
            branch = row["branch"].rsplit("|", 1)[-1]
            key = (*period, branch)
            definition = next(
                (item for item in network.report_branch_definitions if item[:3] == key),
                None,
            )
            from_bus = "" if definition is None else definition[3]
            to_bus = "" if definition is None else definition[4]
            flow = float(row["flow_mw"])
            direction = _branch_report_direction(flow)
            capacity = network.branch_capacity.get((*key, direction), 0.0)
            if key in network.ac_branches:
                loss = sum(
                    _optional_component_value(
                        artifacts["directed_branch_loss"], (*key, item)
                    )
                    for item in ("forward", "backward")
                )
                marginal = sum(
                    float(
                        solved.model.dual.get(
                            artifacts["branch_maximum_flow"][*key, item], 0.0
                        )
                    )
                    for item in ("forward", "backward")
                    if (*key, item) in artifacts["branch_maximum_flow"]
                )
            elif hvdc_data is not None and key in hvdc_data.links:
                loss = _component_value(artifacts["hvdc_loss"], key)
                constraint = artifacts["hvdc_maximum_flow"]
                marginal = (
                    float(solved.model.dual.get(constraint[key], 0.0))
                    if key in constraint
                    else 0.0
                )
            else:
                loss = 0.0
                marginal = 0.0
            fixed = float(network.branch_fixed_loss.get(key, 0.0))
            active = key in network.branches
            from_price = (
                _reported_bus_price((*period, from_bus), accepted, prices)
                if active and from_bus
                else 0.0
            )
            to_price = (
                _reported_bus_price((*period, to_bus), accepted, prices)
                if active and to_bus
                else 0.0
            )
            duration = float(solved.case_data.interval_minutes[period]) / 60.0
            rentals = duration * (
                to_price * (flow - loss - fixed) - from_price * flow
                if direction == "forward"
                else to_price * flow - from_price * (loss + fixed + flow)
            )
            row.update(
                {
                    "from_bus": from_bus,
                    "to_bus": to_bus,
                    "capacity_mw": _number(capacity),
                    "dynamic_loss_mw": _number(loss),
                    "fixed_loss_mw": _number(fixed),
                    "from_bus_price_nzd_per_mwh": _number(from_price),
                    "to_bus_price_nzd_per_mwh": _number(to_price),
                    "branch_price_nzd_per_mwh": _number(marginal),
                    "branch_rentals_nzd": _number(rentals),
                }
            )

    @staticmethod
    def _constraints(rows: list[dict[str, str]], solved: Any) -> None:
        components = {
            component.name: component
            for component in solved.model.component_objects(
                pyo.Constraint, active=True, descend_into=True
            )
        }
        indexes = {
            name: {
                "|".join(
                    str(part)
                    for part in (
                        index if isinstance(index, tuple) else (index,)
                    )
                ): index
                for index in component
            }
            for name, component in components.items()
        }
        for row in rows:
            component = components[row["constraint"]]
            index = indexes[row["constraint"]][row["index"]]
            row["price_nzd_per_mwh"] = _number(
                solved.model.dual.get(component[index], 0.0)
            )

    def _reserve_and_island(
        self,
        current: dict[str, list[dict[str, str]]],
        solved: Any,
        accepted: SolveObservation,
        prices: PriceTrace,
        period: tuple[str, str],
        network: Any,
        reserve_data: Any,
        hvdc_data: Any,
        bus_values: Mapping[str, Mapping[str, float]],
    ) -> None:
        artifacts = solved.artifacts.values
        requirement: dict[tuple[str, str], float] = {}
        for island_key in reserve_data.islands:
            if island_key[:2] != period:
                continue
            island = island_key[2]
            for reserve_class in ("FIR", "SIR"):
                candidates = [0.0]
                prefix = (*period, island)
                for name in (
                    "generator_island_risk",
                    "group_island_risk",
                ):
                    for index in artifacts[name]:
                        key = _index_tuple(index)
                        if key[:3] != prefix or key[-2] != reserve_class:
                            continue
                        effective_key = (*prefix, reserve_class, key[-1])
                        candidates.append(
                            _component_value(artifacts[name], key)
                            + _optional_component_value(
                                artifacts["reserve_share_effective"], effective_key
                            )
                        )
                for index in artifacts["island_risk"]:
                    key = _index_tuple(index)
                    if key[:4] != (*prefix, reserve_class):
                        continue
                    if key[4] in reserve_data.manual_risks:
                        candidates.append(
                            _component_value(artifacts["island_risk"], key)
                            + _optional_component_value(
                                artifacts["reserve_share_effective"], key
                            )
                        )
                    elif key[4] in reserve_data.hvdc_risks:
                        candidates.append(
                            _component_value(artifacts["island_risk"], key)
                        )
                for name in (
                    "hvdc_generator_island_risk",
                    "hvdc_manual_island_risk",
                ):
                    for index in artifacts[name]:
                        key = _index_tuple(index)
                        if key[:3] == prefix and key[-2] == reserve_class:
                            candidates.append(_component_value(artifacts[name], key))
                requirement[(island, reserve_class)] = max(candidates)
        for table in ("reserve", "island"):
            for row in current[table]:
                island = row["island"]
                reserve_class = row["reserve_class"]
                key = (*period, island, reserve_class)
                row["required_mw"] = _number(
                    requirement.get((island, reserve_class), 0.0)
                )
                if table == "reserve":
                    row["violation_mw"] = _number(
                        _component_value(artifacts["reserve_deficit_ce"], key)
                        + _component_value(artifacts["reserve_deficit_ece"], key)
                    )
                    continue
                buses = {
                    bus
                    for ca, dt, bus, row_island in network.bus_island
                    if (ca, dt, row_island) == (*period, island)
                }
                offers = {
                    offer
                    for ca, dt, offer, row_island in reserve_data.offer_island
                    if (ca, dt, row_island) == (*period, island)
                }
                bids = {
                    bid
                    for ca, dt, bid, node in network.bid_node
                    if (ca, dt) == period
                    and any(
                        (n_ca, n_dt, n_node, bus) in network.node_bus
                        for n_ca, n_dt, n_node, bus in network.node_bus
                        if (n_ca, n_dt, n_node) == (*period, node) and bus in buses
                    )
                }
                generation_mw = sum(
                    _component_value(artifacts["generation"], (*period, offer))
                    for offer in offers
                )
                bid_load = sum(
                    _component_value(artifacts["purchase"], (*period, bid))
                    for bid in bids
                )
                # Island load follows vSPD's ``sum(busLoad) + clearedBid``.
                # Bus report load cannot be reused here because a bid attached
                # to a node mapped to multiple buses is intentionally shown at
                # every bus, whereas the island total counts that bid once.
                base_load = _island_report_load(network, period, buses, bid_load)
                ac_loss = 0.0
                for branch in network.ac_branches:
                    to_bus = next(
                        (
                            item[3]
                            for item in network.branch_to_bus
                            if item[:3] == branch
                        ),
                        "",
                    )
                    if branch[:2] == period and to_bus in buses:
                        ac_loss += float(network.branch_fixed_loss[branch]) + sum(
                            _optional_component_value(
                                artifacts["directed_branch_loss"], (*branch, direction)
                            )
                            for direction in ("forward", "backward")
                        )
                hvdc_flow = 0.0
                hvdc_loss = 0.0
                if hvdc_data is not None:
                    for link in hvdc_data.links:
                        if link[:2] != period:
                            continue
                        from_bus = next(
                            item[3]
                            for item in hvdc_data.sending_bus
                            if item[:3] == link
                        )
                        to_bus = next(
                            item[3]
                            for item in hvdc_data.receiving_bus
                            if item[:3] == link
                        )
                        fixed = 0.5 * float(network.branch_fixed_loss.get(link, 0.0))
                        if from_bus in buses:
                            hvdc_flow += _component_value(artifacts["hvdc_flow"], link)
                            hvdc_loss += fixed
                        if to_bus in buses:
                            hvdc_loss += fixed + _component_value(
                                artifacts["hvdc_loss"], link
                            )
                reference_price = sum(
                    float(prices.node.get((*period, node), 0.0))
                    for ca, dt, node in network.reference_nodes
                    if (ca, dt) == period
                    and any(
                        n_bus in buses
                        for n_ca, n_dt, n_node, n_bus in network.node_bus
                        if (n_ca, n_dt, n_node) == (*period, node)
                    )
                )
                cleared = _component_value(artifacts["island_reserve"], key)
                shared = _component_sum(artifacts["reserve_share_sent"], key)
                received = _component_sum(artifacts["reserve_share_received"], key)
                effective_ce = _component_value(
                    artifacts["reserve_share_effective_ce"], key
                )
                effective_ece = _component_value(
                    artifacts["reserve_share_effective_ece"], key
                )
                row.update(
                    {
                        "generation_mw": _number(generation_mw),
                        "load_mw": _number(base_load),
                        "bid_load_mw": _number(bid_load),
                        "ac_loss_mw": _number(ac_loss),
                        "hvdc_flow_mw": _number(hvdc_flow),
                        "hvdc_loss_mw": _number(hvdc_loss),
                        "reference_price_nzd_per_mwh": _number(reference_price),
                        "cleared_mw": _number(cleared),
                        "share_mw": _number(shared),
                        "received_mw": _number(received),
                        "effective_ce_mw": _number(effective_ce),
                        "effective_ece_mw": _number(effective_ece),
                    }
                )


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
                V5SummaryReportProjector().project(
                    accepted,
                    base,
                    complete=case.status.value == "complete",
                )
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
                        "price_interval": _price_interval(
                            prices.repaired_bus_intervals.get(bus_key)
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
                        "price_interval": _price_interval(
                            prices.node_intervals.get(node_key)
                        ),
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
            rows["risk"].extend(V5RiskReportProjector().project(accepted, base))
            V5DetailedReportProjector().enrich(rows, accepted, prices, base)
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
                        "price_interval": _price_interval(
                            run.published.energy_intervals.get((period, node))
                        ),
                        "publication_seconds": _number(
                            run.published.total_seconds[period]
                        ),
                        "date_time": run.published.date_time.get(period, ""),
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
                        "price_interval": "",
                        "publication_seconds": _number(
                            run.published.total_seconds[period]
                        ),
                        "date_time": run.published.date_time.get(period, ""),
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
            ("status_code", "code"),
            ("system_ofv_nzd", "NZD"),
            ("system_cost_nzd", "NZD"),
            ("system_benefit_nzd", "NZD"),
            ("violation_cost_nzd", "NZD"),
            ("deficit_generation_mw", "MW"),
            ("surplus_generation_mw", "MW"),
            ("deficit_reserve_mw", "MW"),
            ("surplus_branch_flow_mw", "MW"),
            ("deficit_ramp_rate_mw", "MW"),
            ("surplus_ramp_rate_mw", "MW"),
            ("deficit_branch_constraint_mw", "MW"),
            ("surplus_branch_constraint_mw", "MW"),
            ("deficit_market_node_constraint_mw", "MW"),
            ("surplus_market_node_constraint_mw", "MW"),
        ),
        "island": (
            *common,
            ("island", "id"),
            ("reserve_class", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
            ("generation_mw", "MW"),
            ("load_mw", "MW"),
            ("bid_load_mw", "MW"),
            ("ac_loss_mw", "MW"),
            ("hvdc_flow_mw", "MW"),
            ("hvdc_loss_mw", "MW"),
            ("reference_price_nzd_per_mwh", "NZD/MWh"),
            ("required_mw", "MW"),
            ("cleared_mw", "MW"),
            ("share_mw", "MW"),
            ("received_mw", "MW"),
            ("effective_ce_mw", "MW"),
            ("effective_ece_mw", "MW"),
        ),
        "bus": (
            *common,
            ("bus", "id"),
            ("raw_price_nzd_per_mwh", "NZD/MWh"),
            ("repaired_price_nzd_per_mwh", "NZD/MWh"),
            ("price_interval", "NZD/MWh"),
            ("disconnected", "boolean"),
            ("invalid", "boolean"),
            ("generation_mw", "MW"),
            ("load_mw", "MW"),
            ("deficit_mw", "MW"),
            ("surplus_mw", "MW"),
        ),
        "node": (
            *common,
            ("node", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
            ("price_interval", "NZD/MWh"),
            ("dead", "boolean"),
            ("price_source", "id"),
            ("generation_mw", "MW"),
            ("load_mw", "MW"),
            ("deficit_mw", "MW"),
            ("surplus_mw", "MW"),
        ),
        "offer": (
            *common,
            ("offer", "id"),
            ("generation_mw", "MW"),
            ("trader", "id"),
            ("fir_mw", "MW"),
            ("sir_mw", "MW"),
        ),
        "bid": (
            *common,
            ("bid", "id"),
            ("purchase_mw", "MW"),
            ("trader", "id"),
            ("total_bid_mw", "MW"),
        ),
        "reserve": (
            *common,
            ("island", "id"),
            ("reserve_class", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
            ("required_mw", "MW"),
            ("violation_mw", "MW"),
        ),
        "risk": (
            *common,
            ("island", "id"),
            ("reserve_class", "id"),
            ("risk_class", "id"),
            ("risk_type", "id"),
            ("risk_setter", "id"),
            ("covered_energy_mw", "MW"),
            ("covered_reserve_mw", "MW"),
            ("covered_fk_band_mw", "MW"),
            ("risk_subtractor_mw", "MW"),
            ("reserve_mw", "MW"),
            ("shortfall_mw", "MW"),
            ("deficit_mw", "MW"),
            ("reserve_price_nzd_per_mwh", "NZD/MWh"),
            ("risk_price_nzd_per_mwh", "NZD/MWh"),
        ),
        "branch": (
            *common,
            ("branch", "id"),
            ("flow_mw", "MW"),
            ("from_bus", "id"),
            ("to_bus", "id"),
            ("capacity_mw", "MW"),
            ("dynamic_loss_mw", "MW"),
            ("fixed_loss_mw", "MW"),
            ("from_bus_price_nzd_per_mwh", "NZD/MWh"),
            ("to_bus_price_nzd_per_mwh", "NZD/MWh"),
            ("branch_price_nzd_per_mwh", "NZD/MWh"),
            ("branch_rentals_nzd", "NZD"),
        ),
        "constraint": (
            *common,
            ("constraint", "id"),
            ("index", "id"),
            ("body", "value"),
            ("lower", "value"),
            ("upper", "value"),
            ("price_nzd_per_mwh", "NZD/MWh"),
        ),
        "published_price": (
            ("trading_period", "id"),
            ("location", "id"),
            ("product", "id"),
            ("price_nzd_per_mwh", "NZD/MWh"),
            ("price_interval", "NZD/MWh"),
            ("publication_seconds", "s"),
            ("date_time", "datetime"),
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


def _price_interval(value: tuple[float, float] | None) -> str:
    if value is None:
        return ""
    return json.dumps([float(_number(bound)) for bound in value], separators=(",", ":"))


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
        ("branch_flow", "branch", "branch", "flow_mw"),
        ("hvdc_flow", "branch", "branch", "flow_mw"),
    ):
        component = artifacts.get(artifact)
        if component is None:
            continue
        for key, value in _component_values(component):
            rows[report].append(
                {**base, identity: key.rsplit("|", 1)[-1], quantity: _number(value)}
            )
    network_data = artifacts.get("network_data")
    study_mode = getattr(getattr(solved, "case_data", None), "study_mode", {})
    period = (base["case_id"], base["date_time"])
    if float(study_mode.get(period, 0.0)) != 111.0:
        reported_branch_identities = {row["branch"] for row in rows["branch"]}
        for branch in sorted(getattr(network_data, "report_branches", ())):
            identity = str(branch[-1])
            if identity not in reported_branch_identities:
                rows["branch"].append(
                    {**base, "branch": identity, "flow_mw": "0"}
                )
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
