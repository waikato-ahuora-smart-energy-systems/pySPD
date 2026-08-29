"""Algebraically reconstruct the pinned v5.0.2 first-loop RTD load.

The implementation mirrors the load calculation in ``vSPDsolve.gms`` without
solving the dispatch model.  It is deliberately separate from the Pyomo model:
Gate 12 uses it only to enumerate the immutable historical E2E population.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tools.gate12.evidence import AffectedIntervalIdentity, EvidenceContractError
from tools.gate12.historical_population import (
    MATERIAL_SHORTFALL_MW,
    HistoricalInputArtifact,
)

ANALYTIC_GDX_SYMBOLS = (
    "i_runMode",
    "i_dateTimeTradePeriodMap",
    "i_dateTimeNodeParameter",
    "i_dateTimeParameter",
    "i_dateTimeIslandParameter",
    "i_dateTimeNodeBus",
    "i_dateTimeBusIsland",
    "i_dateTimeBusElectricalIsland",
)


@dataclass(frozen=True)
class HistoricalFirstLoopCase:
    """Canonical inputs needed by the first-loop RTD load calculation."""

    case_id: str
    date_time: str
    trading_period: str
    shortfall_transfer_enabled: bool
    use_actual_load: bool
    island_parameters: dict[tuple[str, str], float]
    node_parameters: dict[tuple[str, str], float]
    node_market_islands: dict[str, tuple[str, ...]]
    node_electrical_island_sum: dict[str, float]


@dataclass(frozen=True)
class HistoricalFirstLoopResult:
    """Reconstructed load and provably affected dead-node shortfall."""

    required_load: dict[str, float]
    affected_shortfall_mw: dict[str, float]


@dataclass(frozen=True)
class HistoricalAnalyticAffectedInterval:
    """One analytically selected interval and its reconstructed node evidence."""

    identity: AffectedIntervalIdentity
    affected_shortfall_mw: dict[str, float]


@dataclass(frozen=True)
class HistoricalAnalyticDayResult:
    """Hash-bound analytic results for one canonical daily GDX."""

    trading_date: str
    source_sha256: str
    selected_rtd_case_count: int
    affected: tuple[HistoricalAnalyticAffectedInterval, ...]


class HistoricalFirstLoopCaseLoader(Protocol):
    """Load canonical first-loop cases from a daily artifact."""

    def load(
        self, path: Path, system_directory: Path
    ) -> tuple[HistoricalFirstLoopCase, ...]: ...


class HistoricalFirstLoopLoadReconstructor:
    """Mirror v5.0.2 section 4.10 for the first RTD solve loop."""

    def reconstruct(self, case: HistoricalFirstLoopCase) -> HistoricalFirstLoopResult:
        nodes = sorted(case.node_market_islands)
        islands = sorted(
            {island for mapped in case.node_market_islands.values() for island in mapped}
        )
        if not nodes or not islands:
            raise EvidenceContractError(
                "REQ-G12-POPULATION: first-loop case lacks nodes or market islands"
            )

        def node_value(node: str, parameter: str) -> float:
            value = float(case.node_parameters.get((node, parameter), 0.0))
            if not math.isfinite(value):
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: non-finite node parameter"
                )
            return value

        def island_value(island: str, parameter: str) -> float:
            value = float(case.island_parameters.get((island, parameter), 0.0))
            if not math.isfinite(value):
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: non-finite island parameter"
                )
            return value

        def is_in(node: str, island: str) -> bool:
            return island in case.node_market_islands[node]

        est_scalable = {
            node: node_value(node, "loadIsNCL") == 0.0
            and node_value(node, "conformingFactor") > 0.0
            for node in nodes
        }
        est_non_scalable = {
            node: (
                node_value(node, "nonConformingLoad")
                if node_value(node, "loadIsNCL") != 0.0
                else (
                    0.0
                    if est_scalable[node]
                    else node_value(node, "conformingFactor")
                )
            )
            for node in nodes
        }
        est_scaling: dict[str, float] = {}
        for island in islands:
            denominator = sum(
                node_value(node, "conformingFactor")
                for node in nodes
                if is_in(node, island) and est_scalable[node]
            )
            if denominator == 0.0:
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: zero estimated-load scaling denominator"
                )
            est_scaling[island] = (
                island_value(island, "MWIPS")
                - island_value(island, "Losses")
                - sum(
                    est_non_scalable[node]
                    for node in nodes
                    if is_in(node, island)
                )
            ) / denominator

        estimated_initial = {
            node: (
                node_value(node, "conformingFactor")
                * sum(est_scaling[island] for island in case.node_market_islands[node])
                if est_scalable[node]
                else est_non_scalable[node]
            )
            for node in nodes
        }
        initial_load: dict[str, float] = {}
        for node in nodes:
            value = node_value(node, "initialLoad")
            override = node_value(node, "loadIsOverride") != 0.0
            bad = node_value(node, "loadIsBad") != 0.0
            if not override and (not case.use_actual_load or bad):
                value = estimated_initial[node]
            if override and case.use_actual_load and value > node_value(node, "maxLoad"):
                value = node_value(node, "maxLoad")
            initial_load[node] = value

        scalable = {
            node: node_value(node, "loadIsNCL") == 0.0
            and node_value(node, "loadIsOverride") == 0.0
            and initial_load[node] >= 0.0
            for node in nodes
        }
        target_total = {
            island: island_value(island, "MWIPS")
            + island_value(island, "PSD")
            - island_value(island, "Losses")
            + sum(
                node_value(node, "dispatchedGeneration")
                - node_value(node, "dispatchedLoad")
                for node in nodes
                if is_in(node, island)
            )
            for island in islands
        }
        load_scaling: dict[str, float] = {}
        for island in islands:
            denominator = sum(
                initial_load[node]
                for node in nodes
                if is_in(node, island) and scalable[node]
            )
            if denominator == 0.0:
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: zero required-load scaling denominator"
                )
            load_scaling[island] = (
                target_total[island]
                - sum(
                    initial_load[node]
                    for node in nodes
                    if is_in(node, island) and not scalable[node]
                )
            ) / denominator

        required_load = {
            node: (
                initial_load[node]
                * sum(load_scaling[island] for island in case.node_market_islands[node])
                if scalable[node]
                else initial_load[node]
            )
            + (
                node_value(node, "instructedLoadShed")
                if node_value(node, "instructedShedActive") != 0.0
                else 0.0
            )
            for node in nodes
        }
        affected = {
            node: required_load[node]
            for node in nodes
            if case.shortfall_transfer_enabled
            and case.node_electrical_island_sum.get(node, 0.0) == 0.0
            and required_load[node] > MATERIAL_SHORTFALL_MW
            and node_value(node, "loadIsOverride") == 0.0
            and node_value(node, "instructedShedActive") == 0.0
        }
        return HistoricalFirstLoopResult(
            required_load=required_load,
            affected_shortfall_mw=affected,
        )


class HistoricalAnalyticPopulationSelector:
    """Select affected identities from canonical first-loop cases."""

    def __init__(
        self, reconstructor: HistoricalFirstLoopLoadReconstructor | None = None
    ) -> None:
        self._reconstructor = reconstructor or HistoricalFirstLoopLoadReconstructor()

    def select(
        self,
        cases: tuple[HistoricalFirstLoopCase, ...],
        *,
        trading_date: str,
        source_sha256: str,
    ) -> tuple[HistoricalAnalyticAffectedInterval, ...]:
        if len(trading_date) != 8 or not trading_date.isdigit():
            raise EvidenceContractError(
                "REQ-G12-POPULATION: invalid analytic trading date"
            )
        if len(source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in source_sha256
        ):
            raise EvidenceContractError(
                "REQ-G12-POPULATION: invalid analytic source SHA-256"
            )
        records: list[HistoricalAnalyticAffectedInterval] = []
        for case in cases:
            result = self._reconstructor.reconstruct(case)
            if not result.affected_shortfall_mw:
                continue
            records.append(
                HistoricalAnalyticAffectedInterval(
                    identity=AffectedIntervalIdentity(
                        case_id=case.case_id,
                        date_time=case.date_time,
                        trading_period=case.trading_period,
                        trading_date=trading_date,
                        source_sha256=source_sha256,
                        discovery_rationale=(
                            "pinned-v5.0.2 first-loop RTD load reconstruction; "
                            "positive required load at electrical-island-0 node"
                        ),
                    ),
                    affected_shortfall_mw=result.affected_shortfall_mw,
                )
            )
        records.sort(key=lambda item: item.identity.key)
        return tuple(records)


class HistoricalAnalyticDayEnumerator:
    """Verify provenance and enumerate a single daily GDX fail-closed."""

    def __init__(
        self,
        *,
        loader: HistoricalFirstLoopCaseLoader | None = None,
        selector: HistoricalAnalyticPopulationSelector | None = None,
    ) -> None:
        self._loader = loader or GamsTransferFirstLoopCaseLoader()
        self._selector = selector or HistoricalAnalyticPopulationSelector()

    def enumerate(
        self,
        *,
        artifact: HistoricalInputArtifact,
        path: Path,
        system_directory: Path,
    ) -> HistoricalAnalyticDayResult:
        try:
            size = path.stat().st_size
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise EvidenceContractError(
                "REQ-G12-POPULATION: canonical source is unreadable"
            ) from error
        source_sha256 = digest.hexdigest()
        if size != artifact.size_bytes or source_sha256 != artifact.sha256:
            raise EvidenceContractError(
                "REQ-G12-POPULATION: source size or hash mismatch"
            )
        cases = self._loader.load(path, system_directory)
        affected = self._selector.select(
            cases,
            trading_date=artifact.trading_date,
            source_sha256=source_sha256,
        )
        return HistoricalAnalyticDayResult(
            trading_date=artifact.trading_date,
            source_sha256=source_sha256,
            selected_rtd_case_count=len(cases),
            affected=affected,
        )


class GamsTransferFirstLoopCaseLoader:
    """Adapt the eight canonical GDX symbols to first-loop domain objects."""

    def load(
        self, path: Path, system_directory: Path
    ) -> tuple[HistoricalFirstLoopCase, ...]:
        from collections import defaultdict

        from gams.transfer import Container

        container = Container(system_directory=str(system_directory))
        container.read(str(path), symbols=list(ANALYTIC_GDX_SYMBOLS))
        frames = {
            name: container[name].records for name in ANALYTIC_GDX_SYMBOLS
        }
        if any(frame is None for frame in frames.values()):
            raise EvidenceContractError(
                "REQ-G12-POPULATION: canonical GDX symbol lacks records"
            )

        run_mode = frames["i_runMode"]
        period_map = frames["i_dateTimeTradePeriodMap"]
        node_parameter = frames["i_dateTimeNodeParameter"]
        date_time_parameter = frames["i_dateTimeParameter"]
        island_parameter = frames["i_dateTimeIslandParameter"]
        node_bus = frames["i_dateTimeNodeBus"]
        bus_island = frames["i_dateTimeBusIsland"]
        bus_electrical = frames["i_dateTimeBusElectricalIsland"]
        assert run_mode is not None
        assert period_map is not None
        assert node_parameter is not None
        assert date_time_parameter is not None
        assert island_parameter is not None
        assert node_bus is not None
        assert bus_island is not None
        assert bus_electrical is not None

        study_mode = {
            str(row.ca): int(float(row.value))
            for row in run_mode.itertuples(index=False)
            if str(row.casePar) == "studyMode"
        }
        periods = {
            (str(row.ca), str(row.dt)): str(row.tp)
            for row in period_map.itertuples(index=False)
        }
        date_parameters = {
            (str(row.ca), str(row.dt), str(row.dtPar)): float(row.value)
            for row in date_time_parameter.itertuples(index=False)
        }
        island_parameters: dict[
            tuple[str, str], dict[tuple[str, str], float]
        ] = defaultdict(dict)
        for row in island_parameter.itertuples(index=False):
            island_parameters[(str(row.ca), str(row.dt))][
                (str(row.isl), str(row.islPar))
            ] = float(row.value)

        renamed_node_parameters = {
            "nonConformingFactor": "nonConformingLoad",
        }
        node_parameters: dict[
            tuple[str, str], dict[tuple[str, str], float]
        ] = defaultdict(dict)
        for row in node_parameter.itertuples(index=False):
            name = renamed_node_parameters.get(str(row.nodePar), str(row.nodePar))
            node_parameters[(str(row.ca), str(row.dt))][
                (str(row.n), name)
            ] = float(row.value)

        node_buses: dict[
            tuple[str, str], dict[str, set[str]]
        ] = defaultdict(lambda: defaultdict(set))
        for row in node_bus.itertuples(index=False):
            node_buses[(str(row.ca), str(row.dt))][str(row.n)].add(str(row.b))
        bus_islands: dict[
            tuple[str, str], dict[str, set[str]]
        ] = defaultdict(lambda: defaultdict(set))
        for row in bus_island.itertuples(index=False):
            bus_islands[(str(row.ca), str(row.dt))][str(row.b)].add(str(row.isl))
        electrical: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for row in bus_electrical.itertuples(index=False):
            electrical[(str(row.ca), str(row.dt))][str(row.b)] = float(row.value)

        cases: list[HistoricalFirstLoopCase] = []
        for key, trading_period in periods.items():
            case_id, date_time = key
            if study_mode.get(case_id) not in {101, 201}:
                continue
            mappings = node_buses[key]
            market_islands = {
                node: tuple(
                    sorted(
                        {
                            island
                            for bus in buses
                            for island in bus_islands[key].get(bus, set())
                        }
                    )
                )
                for node, buses in mappings.items()
            }
            if any(not mapped for mapped in market_islands.values()):
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: node lacks a market-island mapping"
                )
            electrical_sum = {
                node: sum(electrical[key].get(bus, 0.0) for bus in buses)
                for node, buses in mappings.items()
            }
            cases.append(
                HistoricalFirstLoopCase(
                    case_id=case_id,
                    date_time=date_time,
                    trading_period=trading_period,
                    shortfall_transfer_enabled=(
                        date_parameters.get((*key, "enrgShortfallTransfer"), 0.0)
                        == 1.0
                    ),
                    use_actual_load=(
                        date_parameters.get((*key, "useActualLoad"), 0.0) == 1.0
                    ),
                    island_parameters=island_parameters[key],
                    node_parameters=node_parameters[key],
                    node_market_islands=market_islands,
                    node_electrical_island_sum=electrical_sum,
                )
            )
        cases.sort(key=lambda item: (item.date_time, item.case_id))
        if not cases:
            raise EvidenceContractError(
                "REQ-G12-POPULATION: GDX has no RTD first-loop cases"
            )
        return tuple(cases)
