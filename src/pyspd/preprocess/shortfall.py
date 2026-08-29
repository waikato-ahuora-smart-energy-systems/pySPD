"""Pure mapped-node shortfall-transfer rules from the vSPD re-solve loop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from pyspd.preprocess.base import Key


@dataclass(frozen=True, slots=True)
class ShortfallTransferState:
    required_load: Mapping[Key, float]
    adjustment_mw: Mapping[Key, float]
    energy_shortfall_mw: Mapping[Key, float]
    dead_nodes: frozenset[Key]
    load_override_nodes: frozenset[Key]
    instructed_shed_nodes: frozenset[Key]
    electrical_island: Mapping[Key, float]


@dataclass(frozen=True, slots=True)
class ShortfallTransferResult:
    required_load: Mapping[Key, float]
    transfers: Mapping[tuple[Key, Key], float]
    did_transfer: frozenset[Key]
    untransferred: frozenset[Key]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "required_load", MappingProxyType(dict(self.required_load))
        )
        object.__setattr__(self, "transfers", MappingProxyType(dict(self.transfers)))


class ShortfallTransferResolver:
    """Resolve vSPD's ordered candidate-chain rule without solver side effects."""

    def resolve(
        self,
        mapped_nodes: Sequence[tuple[Key, Key]],
        state: ShortfallTransferState,
    ) -> ShortfallTransferResult:
        successors: dict[Key, list[Key]] = {}
        for source, target in mapped_nodes:
            successors.setdefault(source, []).append(target)
        load = dict(state.required_load)
        transfers: dict[tuple[Key, Key], float] = {}
        did_transfer: set[Key] = set()
        untransferred: set[Key] = set()
        for source, adjustment in sorted(state.adjustment_mw.items()):
            if adjustment <= 0.0:
                continue
            load[source] = max(0.0, load.get(source, 0.0) - adjustment)
            candidate = self._candidate(source, successors, state)
            if candidate is None or not self._eligible(source, candidate, state):
                untransferred.add(source)
                did_transfer.add(source)
                continue
            transfers[(source, candidate)] = adjustment
            load[candidate] = load.get(candidate, 0.0) + adjustment
            did_transfer.update((source, candidate))
        return ShortfallTransferResult(
            load,
            MappingProxyType(transfers),
            frozenset(did_transfer),
            frozenset(untransferred),
        )

    @staticmethod
    def _candidate(
        source: Key,
        successors: Mapping[Key, list[Key]],
        state: ShortfallTransferState,
    ) -> Key | None:
        visited = {source}
        candidates = successors.get(source, [])
        candidate = candidates[0] if candidates else None
        while candidate is not None and (
            state.energy_shortfall_mw.get(candidate, 0.0) != 0.0
            or candidate in state.dead_nodes
        ):
            if candidate in visited:
                return None
            visited.add(candidate)
            next_candidates = successors.get(candidate, [])
            candidate = next_candidates[0] if next_candidates else None
        return candidate

    @staticmethod
    def _eligible(
        source: Key,
        candidate: Key,
        state: ShortfallTransferState,
    ) -> bool:
        source_island = state.electrical_island.get(source, 0.0)
        candidate_island = state.electrical_island.get(candidate, 0.0)
        return (
            candidate not in state.load_override_nodes
            and candidate not in state.instructed_shed_nodes
            and (source_island == 0.0 or source_island == candidate_island)
        )
