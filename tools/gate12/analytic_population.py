"""Algebraically reconstruct the pinned v5.0.2 first-loop RTD load.

The implementation mirrors the load calculation in ``vSPDsolve.gms`` without
solving the dispatch model.  It is deliberately separate from the Pyomo model:
Gate 12 uses it only to enumerate the immutable historical E2E population.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import MATERIAL_SHORTFALL_MW


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
