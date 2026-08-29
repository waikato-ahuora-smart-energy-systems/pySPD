"""Audited vSPD override-family application in reference scope order."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pyspd.contracts import CaseData
from pyspd.data import RawRecord, RawSymbol, RawSymbols, ScalarValue
from pyspd.preprocess.input import CaseInput

from .types import OrchestrationError


class OverrideFamily(StrEnum):
    DEMAND = "demand"
    OFFER_PARAMETER = "offer_parameter"
    ENERGY_OFFER = "energy_offer"
    RESERVE_OFFER = "reserve_offer"
    BID_PARAMETER = "bid_parameter"
    ENERGY_BID = "energy_bid"
    BRANCH_PARAMETER = "branch_parameter"
    BRANCH_CONSTRAINT_RHS = "branch_constraint_rhs"
    BRANCH_CONSTRAINT_FACTOR = "branch_constraint_factor"
    MARKET_NODE_CONSTRAINT_RHS = "market_node_constraint_rhs"
    MARKET_NODE_CONSTRAINT_FACTOR = "market_node_constraint_factor"


class OverrideScope(StrEnum):
    ALL_TIME = "all_time"
    TRADING_PERIOD = "trading_period"
    DATE_TIME = "date_time"
    CASE_ID = "case_id"


_SCOPE_ORDER = {scope: index for index, scope in enumerate(OverrideScope)}
_FAMILY_ORDER = {family: index for index, family in enumerate(OverrideFamily)}


@dataclass(frozen=True, slots=True)
class OverrideInstruction:
    family: OverrideFamily
    scope: OverrideScope
    selector: str
    target: tuple[str, ...]
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", OverrideFamily(self.family))
        object.__setattr__(self, "scope", OverrideScope(self.scope))
        object.__setattr__(self, "target", tuple(self.target))
        if not self.target:
            raise OrchestrationError("override target must not be empty")
        if not math.isfinite(self.value):
            raise OrchestrationError("override value must be finite")


@dataclass(frozen=True, slots=True)
class OverrideAuditEntry:
    ordinal: int
    family: OverrideFamily
    scope: OverrideScope
    selector: str
    symbol: str
    key: tuple[str, ...]
    before: float
    after: float


@dataclass(frozen=True, slots=True)
class OverrideAudit:
    input_logical_sha256: str
    output_logical_sha256: str
    entries: tuple[OverrideAuditEntry, ...]


_GENERIC: dict[OverrideFamily, tuple[str, tuple[int, ...]]] = {
    OverrideFamily.OFFER_PARAMETER: ("i_dateTimeOfferParameter", (0, 1)),
    OverrideFamily.ENERGY_OFFER: ("i_dateTimeEnergyOffer", (0, 2, 1)),
    OverrideFamily.RESERVE_OFFER: (
        "i_dateTimeReserveOffer",
        (0, 1, 2, 4, 3),
    ),
    OverrideFamily.BID_PARAMETER: ("i_dateTimeBidParameter", (0, 1)),
    OverrideFamily.ENERGY_BID: ("i_dateTimeEnergyBid", (0, 2, 1)),
    OverrideFamily.BRANCH_PARAMETER: ("i_dateTimeBranchParameter", (0, 1)),
    OverrideFamily.BRANCH_CONSTRAINT_RHS: (
        "i_dateTimeBranchConstraintRHS",
        (0, 1),
    ),
    OverrideFamily.BRANCH_CONSTRAINT_FACTOR: (
        "i_dateTimeBranchConstraintFactors",
        (0, 1),
    ),
    OverrideFamily.MARKET_NODE_CONSTRAINT_RHS: (
        "i_dateTimeMNCnstrRHS",
        (0, 1),
    ),
}


class OverrideApplier:
    """Apply all eleven vSPD families with All→TP→datetime→case precedence."""

    def apply(
        self,
        case_data: CaseData,
        instructions: Iterable[OverrideInstruction],
    ) -> tuple[CaseData, OverrideAudit]:
        applicable = [
            (ordinal, instruction)
            for ordinal, instruction in enumerate(instructions)
            if self._applies(case_data, instruction)
        ]
        applicable.sort(
            key=lambda item: (
                _FAMILY_ORDER[item[1].family],
                _SCOPE_ORDER[item[1].scope],
                item[0],
            )
        )
        symbols = case_data.symbols
        entries: list[OverrideAuditEntry] = []
        for ordinal, instruction in applicable:
            if instruction.family is OverrideFamily.DEMAND:
                symbols, changed = self._demand(symbols, case_data, instruction)
            else:
                symbols, changed = self._generic(symbols, case_data, instruction)
            entries.extend(
                OverrideAuditEntry(
                    ordinal,
                    instruction.family,
                    instruction.scope,
                    instruction.selector,
                    symbol,
                    key,
                    before,
                    after,
                )
                for symbol, key, before, after in changed
            )
        output = CaseData(case_data.formulation_id, case_data.identifier, symbols)
        return output, OverrideAudit(
            case_data.symbols.logical_sha256,
            output.symbols.logical_sha256,
            tuple(entries),
        )

    @staticmethod
    def _applies(case_data: CaseData, instruction: OverrideInstruction) -> bool:
        identity = case_data.identifier
        return (
            instruction.scope is OverrideScope.ALL_TIME
            or (
                instruction.scope is OverrideScope.TRADING_PERIOD
                and instruction.selector == identity.trading_period
            )
            or (
                instruction.scope is OverrideScope.DATE_TIME
                and instruction.selector == identity.date_time
            )
            or (
                instruction.scope is OverrideScope.CASE_ID
                and instruction.selector == identity.case_id
            )
        )

    def _generic(
        self,
        symbols: RawSymbols,
        case_data: CaseData,
        instruction: OverrideInstruction,
    ) -> tuple[RawSymbols, list[tuple[str, tuple[str, ...], float, float]]]:
        if instruction.family is OverrideFamily.MARKET_NODE_CONSTRAINT_FACTOR:
            return self._market_node_factor(symbols, case_data, instruction)
        try:
            symbol_name, order = _GENERIC[instruction.family]
        except KeyError as error:
            raise OrchestrationError(
                f"unsupported override family: {instruction.family.value}"
            ) from error
        if len(order) != len(instruction.target):
            raise OrchestrationError(
                f"{instruction.family.value} target requires {len(order)} fields"
            )
        reordered = tuple(instruction.target[index] for index in order)
        key = (
            case_data.identifier.case_id,
            case_data.identifier.date_time,
            *reordered,
        )
        before = _value(symbols[symbol_name], key)
        output = _set_value(symbols, symbol_name, key, instruction.value)
        return output, [(symbol_name, key, before, instruction.value)]

    def _market_node_factor(
        self,
        symbols: RawSymbols,
        case_data: CaseData,
        instruction: OverrideInstruction,
    ) -> tuple[RawSymbols, list[tuple[str, tuple[str, ...], float, float]]]:
        if len(instruction.target) != 4:
            raise OrchestrationError(
                "market_node_constraint_factor target requires constraint, "
                "offer, reserve class, reserve type"
            )
        constraint, offer, reserve_class, reserve_type = instruction.target
        prefix = (case_data.identifier.case_id, case_data.identifier.date_time)
        key: tuple[str, ...]
        if reserve_class.upper() == "NA" and reserve_type.upper() == "NA":
            name = "i_dateTimeMNCnstrEnrgFactors"
            key = (*prefix, constraint, offer)
        else:
            name = "i_dateTimeMNCnstrResrvFactors"
            key = (*prefix, constraint, offer, reserve_class, reserve_type)
        before = _value(symbols[name], key)
        return (
            _set_value(symbols, name, key, instruction.value),
            [(name, key, before, instruction.value)],
        )

    def _demand(
        self,
        symbols: RawSymbols,
        case_data: CaseData,
        instruction: OverrideInstruction,
    ) -> tuple[RawSymbols, list[tuple[str, tuple[str, ...], float, float]]]:
        if len(instruction.target) != 4:
            raise OrchestrationError(
                "demand target requires level, identifier, load type, method"
            )
        level, identifier, load_type, method = (
            value.upper() for value in instruction.target
        )
        source = CaseInput(
            CaseData(case_data.formulation_id, case_data.identifier, symbols)
        )
        node_values = source.numeric("i_dateTimeNodeParameter")
        nodes = {key[:3] for key in node_values if key[-1] == "demand"}
        if level == "NODE":
            nodes = {node for node in nodes if node[2] == identifier}
        elif level == "ISLAND":
            node_bus = source.members("i_dateTimeNodeBus")
            bus_island = source.members("i_dateTimeBusIsland")
            buses = {key[:3] for key in bus_island if key[3].upper() == identifier}
            nodes = {key[:3] for key in node_bus if key[:2] + (key[3],) in buses}
        elif level != "ALL":
            raise OrchestrationError(f"unsupported demand override level: {level}")
        if load_type not in {"ALL", "CONFORMING", "NONCONFORM"}:
            raise OrchestrationError(f"unsupported demand load type: {load_type}")
        if load_type != "ALL":
            want_ncl = load_type == "NONCONFORM"
            nodes = {
                node
                for node in nodes
                if bool(node_values.get((*node, "loadIsNCL"), 0.0)) is want_ncl
            }
        current = {node: node_values.get((*node, "demand"), 0.0) for node in nodes}
        updated = dict(current)
        if method == "SCALE":
            updated = {
                node: value * instruction.value for node, value in current.items()
            }
        elif level == "NODE" and method == "INCREMENT":
            updated = {
                node: value + instruction.value for node, value in current.items()
            }
        elif level == "NODE" and method == "VALUE":
            updated = dict.fromkeys(current, instruction.value)
        elif method in {"INCREMENT", "VALUE"}:
            positive = {node: value for node, value in current.items() if value > 0.0}
            total = sum(positive.values())
            if total <= 0.0:
                raise OrchestrationError(
                    "group demand increment/value requires positive load"
                )
            delta = (
                instruction.value
                if method == "INCREMENT"
                else instruction.value - total
            )
            for node, value in positive.items():
                updated[node] = value + delta * value / total
        else:
            raise OrchestrationError(f"unsupported demand override method: {method}")
        changed: list[tuple[str, tuple[str, ...], float, float]] = []
        output = symbols
        for node in sorted(updated):
            key = (*node, "demand")
            output = _set_value(output, "i_dateTimeNodeParameter", key, updated[node])
            changed.append(
                ("i_dateTimeNodeParameter", key, current[node], updated[node])
            )
        return output, changed


def _value(symbol: RawSymbol, key: tuple[str, ...]) -> float:
    record = next((item for item in symbol.records if item.keys == key), None)
    if record is None:
        return 0.0
    value = record.values.get("value")
    return 0.0 if value is None or value.number is None else float(value.number)


def _set_value(
    symbols: RawSymbols,
    symbol_name: str,
    key: tuple[str, ...],
    value: float,
) -> RawSymbols:
    source = symbols[symbol_name]
    records = list(source.records)
    replacement = RawRecord(key, MappingProxyType({"value": ScalarValue.finite(value)}))
    for index, record in enumerate(records):
        if record.keys == key:
            records[index] = replacement
            break
    else:
        records.append(replacement)
    uels = tuple(
        tuple(dict.fromkeys((*source.uel_orders[index], key[index])))
        for index in range(source.dimension)
    )
    changed = RawSymbol(
        source.name,
        source.symbol_type,
        source.dimension,
        source.domains,
        source.description,
        uels,
        tuple(records),
    )
    return RawSymbols(
        symbols.source_name,
        symbols.source_sha256,
        tuple(
            changed if item.name == symbol_name else item for item in symbols.symbols
        ),
    )
