"""Immutable Gate 8 run, state, event, and price contracts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

type Key = tuple[str, ...]


class OrchestrationError(ValueError):
    """A daily-run contract or transition is unsafe or inconsistent."""


class ScheduleType(StrEnum):
    RTD = "RTD"
    PRSS = "PRSS"
    SPD = "SPD"


class CaseRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    DEGRADED = "degraded"
    FAILED = "failed"


class DailyRunState(StrEnum):
    READY = "ready"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETE = "complete"
    FAILED = "failed"


class RunEventKind(StrEnum):
    CASE_SELECTED = "case_selected"
    INITIALIZED = "initialized"
    OVERRIDES_APPLIED = "overrides_applied"
    SOLVE_STARTED = "solve_started"
    SOLVE_ACCEPTED = "solve_accepted"
    SHORTFALL_TRANSFERRED = "shortfall_transferred"
    SHORTFALL_SCALING_DISABLED = "shortfall_scaling_disabled"
    LOOP_LIMIT_REACHED = "loop_limit_reached"
    PRICES_REPAIRED = "prices_repaired"
    CASE_COMPLETE = "case_complete"
    CHECKPOINT_WRITTEN = "checkpoint_written"
    RESUMED = "resumed"
    PRICES_PUBLISHED = "prices_published"


@dataclass(frozen=True, slots=True)
class DailyRunConfiguration:
    formulation_id: str
    source_sha256: str
    maximum_solve_loops: int = 5
    daily_mode: bool = True
    price_rounding_decimals: int = 5
    residual_tolerance: float = 1e-6
    environment_fingerprint: str = ""
    application_configuration_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.formulation_id.strip():
            raise OrchestrationError("formulation_id must not be empty")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise OrchestrationError("source_sha256 must be a lowercase SHA-256")
        if self.maximum_solve_loops <= 0:
            raise OrchestrationError("maximum_solve_loops must be positive")
        if not 0 <= self.price_rounding_decimals <= 12:
            raise OrchestrationError("price_rounding_decimals must lie in [0, 12]")
        if self.residual_tolerance <= 0.0 or not math.isfinite(self.residual_tolerance):
            raise OrchestrationError("residual_tolerance must be finite and positive")
        if self.application_configuration_sha256 and (
            len(self.application_configuration_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.application_configuration_sha256
            )
        ):
            raise OrchestrationError(
                "application_configuration_sha256 must be a lowercase SHA-256"
            )

    @property
    def logical_sha256(self) -> str:
        return _sha256(
            {
                "formulation_id": self.formulation_id,
                "source_sha256": self.source_sha256,
                "maximum_solve_loops": self.maximum_solve_loops,
                "daily_mode": self.daily_mode,
                "price_rounding_decimals": self.price_rounding_decimals,
                "residual_tolerance": self.residual_tolerance.hex(),
                "environment_fingerprint": self.environment_fingerprint,
                "application_configuration_sha256": (
                    self.application_configuration_sha256
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class DailyCase:
    case_id: str
    date_time: str
    trading_period: str
    study_mode: int
    schedule_type: ScheduleType
    interval_minutes: float
    publication_seconds: float
    ordinal: int
    source_sha256: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.case_id, self.date_time, self.trading_period)
        ):
            raise OrchestrationError("case identity fields must not be empty")
        if self.interval_minutes <= 0.0 or not math.isfinite(self.interval_minutes):
            raise OrchestrationError("interval_minutes must be finite and positive")
        if self.publication_seconds < 0.0 or not math.isfinite(
            self.publication_seconds
        ):
            raise OrchestrationError(
                "publication_seconds must be finite and nonnegative"
            )
        if self.ordinal < 0:
            raise OrchestrationError("case ordinal must be nonnegative")
        compatible_modes = {
            ScheduleType.RTD: frozenset({101, 201}),
            ScheduleType.PRSS: frozenset({130, 131}),
            ScheduleType.SPD: frozenset({111}),
        }
        if self.study_mode not in compatible_modes[self.schedule_type]:
            raise OrchestrationError(
                "REQ-G8-ORCHESTRATION: incompatible study mode and schedule type"
            )


@dataclass(frozen=True, slots=True)
class PreparedCase:
    specification: DailyCase
    payload: Any
    required_load: Mapping[Key, float]
    generation_start: Mapping[str, float] = field(default_factory=dict)
    load_override_nodes: frozenset[Key] = frozenset()
    load_bad_nodes: frozenset[Key] = frozenset()
    instructed_shed_nodes: frozenset[Key] = frozenset()
    potential_inconsistency_nodes: frozenset[Key] = frozenset()
    node_transfer: tuple[tuple[Key, Key], ...] = ()
    use_actual_load: bool = True
    rtd_load_reconstruction_enabled: bool = True
    scaling_disabled_nodes: frozenset[Key] = frozenset()
    transfer_enabled: bool = True
    price_transfer_enabled: bool = True
    shortfall_removal_margin: float = 0.0
    maximum_solve_loops: int | None = None
    override_entry_count: int = 0
    override_input_sha256: str = ""
    override_output_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_load", _proxy(self.required_load))
        object.__setattr__(self, "generation_start", _proxy(self.generation_start))
        for name in (
            "load_override_nodes",
            "load_bad_nodes",
            "instructed_shed_nodes",
            "potential_inconsistency_nodes",
            "scaling_disabled_nodes",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        object.__setattr__(self, "node_transfer", tuple(self.node_transfer))
        if self.shortfall_removal_margin < 0.0:
            raise OrchestrationError("shortfall_removal_margin cannot be negative")
        if self.maximum_solve_loops is not None and self.maximum_solve_loops <= 0:
            raise OrchestrationError("case maximum_solve_loops must be positive")
        if self.override_entry_count < 0:
            raise OrchestrationError("override_entry_count cannot be negative")


@dataclass(frozen=True, slots=True)
class SolveObservation:
    generation: Mapping[str, float]
    energy_shortfall: Mapping[Key, float]
    bus_generation: Mapping[Key, float]
    bus_load: Mapping[Key, float]
    raw_bus_prices: Mapping[Key, float]
    reserve_prices: Mapping[Key, float]
    node_bus_allocation: Mapping[Key, float]
    bus_electrical_island: Mapping[Key, float]
    node_electrical_island: Mapping[Key, float]
    raw_bus_price_intervals: Mapping[Key, tuple[float, float]] = field(
        default_factory=dict
    )
    node_market_island: Mapping[Key, str] = field(default_factory=dict)
    node_transfer: tuple[tuple[Key, Key], ...] = ()
    persistent_disconnected_buses: frozenset[Key] = frozenset()
    bus_adjacency: frozenset[tuple[Key, Key]] = frozenset()
    connected_bus_flow: Mapping[Key, float] = field(default_factory=dict)
    cleared_offer_price: Mapping[Key, float] = field(default_factory=dict)
    sos_price_repair_required: bool = False
    objective: float = 0.0
    degraded_reasons: tuple[str, ...] = ()
    solve_payload: Any = None

    def __post_init__(self) -> None:
        for name in (
            "generation",
            "energy_shortfall",
            "bus_generation",
            "bus_load",
            "raw_bus_prices",
            "reserve_prices",
            "node_bus_allocation",
            "bus_electrical_island",
            "node_electrical_island",
            "connected_bus_flow",
            "cleared_offer_price",
        ):
            values = dict(getattr(self, name))
            if any(not math.isfinite(float(value)) for value in values.values()):
                raise OrchestrationError(f"{name} contains a non-finite value")
            object.__setattr__(self, name, MappingProxyType(values))
        object.__setattr__(self, "node_transfer", tuple(self.node_transfer))
        object.__setattr__(
            self,
            "raw_bus_price_intervals",
            _price_interval_proxy(
                self.raw_bus_price_intervals,
                valid_keys=self.raw_bus_prices,
                name="raw_bus_price_intervals",
            ),
        )
        object.__setattr__(self, "node_market_island", _proxy(self.node_market_island))
        object.__setattr__(
            self,
            "persistent_disconnected_buses",
            frozenset(self.persistent_disconnected_buses),
        )
        object.__setattr__(self, "bus_adjacency", frozenset(self.bus_adjacency))
        object.__setattr__(self, "degraded_reasons", tuple(self.degraded_reasons))


@dataclass(frozen=True, slots=True)
class PriceTrace:
    raw_bus: Mapping[Key, float]
    repaired_bus: Mapping[Key, float]
    node: Mapping[Key, float]
    reserve: Mapping[Key, float]
    disconnected_buses: frozenset[Key]
    dead_nodes: frozenset[Key]
    dead_node_price_source: Mapping[Key, Key]
    invalid_buses: frozenset[Key]
    raw_bus_intervals: Mapping[Key, tuple[float, float]] = field(
        default_factory=dict
    )
    repaired_bus_intervals: Mapping[Key, tuple[float, float]] = field(
        default_factory=dict
    )
    node_intervals: Mapping[Key, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "raw_bus",
            "repaired_bus",
            "node",
            "reserve",
            "dead_node_price_source",
        ):
            object.__setattr__(self, name, _proxy(getattr(self, name)))
        object.__setattr__(
            self, "disconnected_buses", frozenset(self.disconnected_buses)
        )
        object.__setattr__(self, "dead_nodes", frozenset(self.dead_nodes))
        object.__setattr__(self, "invalid_buses", frozenset(self.invalid_buses))
        for name, valid_keys in (
            ("raw_bus_intervals", self.raw_bus),
            ("repaired_bus_intervals", self.repaired_bus),
            ("node_intervals", self.node),
        ):
            object.__setattr__(
                self,
                name,
                _price_interval_proxy(
                    getattr(self, name), valid_keys=valid_keys, name=name
                ),
            )


@dataclass(frozen=True, slots=True)
class RunEvent:
    sequence: int
    kind: RunEventKind
    case_id: str | None
    solve_loop: int | None = None
    details: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise OrchestrationError("event sequence must be nonnegative")
        object.__setattr__(self, "details", _proxy(self.details))


@dataclass(frozen=True, slots=True)
class CaseRunResult:
    specification: DailyCase
    status: CaseRunStatus
    solve_count: int
    accepted: SolveObservation | None
    prices: PriceTrace | None
    events: tuple[RunEvent, ...]
    final_required_load: Mapping[Key, float]
    transfers: Mapping[tuple[Key, Key], float]
    untransferred_nodes: frozenset[Key]

    def __post_init__(self) -> None:
        if self.solve_count < 0:
            raise OrchestrationError("solve_count cannot be negative")
        if self.status in {CaseRunStatus.COMPLETE, CaseRunStatus.DEGRADED} and (
            self.accepted is None or self.prices is None
        ):
            raise OrchestrationError("accepted case result requires solve and prices")
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(
            self, "final_required_load", _proxy(self.final_required_load)
        )
        object.__setattr__(self, "transfers", _proxy(self.transfers))
        object.__setattr__(
            self, "untransferred_nodes", frozenset(self.untransferred_nodes)
        )


@dataclass(frozen=True, slots=True)
class PublishedPrices:
    energy: Mapping[tuple[str, str], float]
    reserve: Mapping[tuple[str, str, str], float]
    total_seconds: Mapping[str, float]
    date_time: Mapping[str, str] = field(default_factory=dict)
    energy_intervals: Mapping[tuple[str, str], tuple[float, float]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "energy", _proxy(self.energy))
        object.__setattr__(self, "reserve", _proxy(self.reserve))
        object.__setattr__(self, "total_seconds", _proxy(self.total_seconds))
        object.__setattr__(self, "date_time", _proxy(self.date_time))
        object.__setattr__(
            self,
            "energy_intervals",
            _price_interval_proxy(
                self.energy_intervals,
                valid_keys=self.energy,
                name="energy_intervals",
            ),
        )


@dataclass(frozen=True, slots=True)
class DailyRunCheckpoint:
    configuration_sha256: str
    next_case_ordinal: int
    completed: tuple[CaseRunResult, ...]
    previous_generation: Mapping[str, float]
    event_sequence: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "completed", tuple(self.completed))
        object.__setattr__(
            self, "previous_generation", _proxy(self.previous_generation)
        )


@dataclass(frozen=True, slots=True)
class DailyRunResult:
    state: DailyRunState
    configuration_sha256: str
    cases: tuple[CaseRunResult, ...]
    published: PublishedPrices | None
    events: tuple[RunEvent, ...]
    checkpoint: DailyRunCheckpoint | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", tuple(self.cases))
        object.__setattr__(self, "events", tuple(self.events))


def _proxy[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(values))


def _price_interval_proxy[K](
    values: Mapping[K, tuple[float, float]],
    *,
    valid_keys: Mapping[K, float],
    name: str,
) -> Mapping[K, tuple[float, float]]:
    output: dict[K, tuple[float, float]] = {}
    for key, raw_bounds in values.items():
        if key not in valid_keys:
            raise OrchestrationError(f"{name} contains an unknown price key")
        if len(raw_bounds) != 2:
            raise OrchestrationError(f"{name} bounds must have length two")
        bounds = (float(raw_bounds[0]), float(raw_bounds[1]))
        if not all(math.isfinite(value) for value in bounds):
            raise OrchestrationError(f"{name} contains a non-finite bound")
        if bounds[0] > bounds[1]:
            raise OrchestrationError(f"{name} lower bound exceeds upper bound")
        scalar = float(valid_keys[key])
        if scalar < bounds[0] - 1e-9 or scalar > bounds[1] + 1e-9:
            raise OrchestrationError(f"{name} does not contain its scalar price")
        output[key] = bounds
    return MappingProxyType(output)


def _sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
