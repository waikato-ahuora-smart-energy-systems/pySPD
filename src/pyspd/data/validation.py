"""Actionable pre-model validation for vSPD input semantics."""

from __future__ import annotations

from dataclasses import dataclass

from pyspd.data.catalog import SymbolCatalog, SymbolCatalogError
from pyspd.data.raw import RawSymbols
from pyspd.data.values import ValueKind


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    symbol: str
    identity: tuple[str, ...]
    message: str


class InputValidationError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{item.code}: {item.message}" for item in issues))


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def raise_for_errors(self) -> None:
        if self.issues:
            raise InputValidationError(self.issues)


class V5InputValidator:
    def __init__(self, *, allocation_tolerance: float = 1e-9) -> None:
        self.allocation_tolerance = allocation_tolerance

    def validate(self, raw: RawSymbols) -> ValidationReport:
        issues: list[ValidationIssue] = []
        try:
            SymbolCatalog.vspd_v5().validate(raw)
        except SymbolCatalogError as error:
            issues.append(ValidationIssue("schema", "<catalog>", (), str(error)))
            return ValidationReport(tuple(issues))

        symbols = {symbol.name: symbol for symbol in raw.symbols}
        cases = {record.keys[0] for record in symbols["i_caseDefn"].records}
        date_pairs = {
            record.keys[:2]
            for record in symbols["i_dateTimeTradePeriodMap"].records
        }
        auxiliary_datetime_families = {
            "i_dateTimeBidNode",
            "i_dateTimeBidTrader",
            "i_dateTimeBidParameter",
            "i_dateTimeEnergyBid",
        }
        for symbol in raw.symbols:
            if symbol.name == "i_dateTimeTradePeriodMap":
                continue
            if symbol.name.startswith("i_dateTime") and symbol.dimension >= 2:
                for record in symbol.records:
                    unknown_case = record.keys[0] not in cases
                    unknown_datetime = (
                        symbol.name not in auxiliary_datetime_families
                        and record.keys[:2] not in date_pairs
                    )
                    if unknown_case or unknown_datetime:
                        issues.append(
                            ValidationIssue(
                                "unknown_case_datetime",
                                symbol.name,
                                record.keys[:2],
                                f"{symbol.name}{record.keys[:2]} has no case/date mapping",
                            )
                        )

        nodes = {record.keys[0] for record in symbols["i_node"].records}
        buses = {record.keys[0] for record in symbols["i_bus"].records}
        for mapping_name, node_index, bus_index in (
            ("i_dateTimeNodeBus", 2, 3),
            ("i_dateTimeNodeOutageBranch", 2, None),
            ("i_dateTimeOfferNode", 3, None),
            ("i_dateTimeBidNode", 3, None),
        ):
            for record in symbols[mapping_name].records:
                node = record.keys[node_index]
                if node not in nodes:
                    issues.append(
                        ValidationIssue(
                            "unknown_node",
                            mapping_name,
                            record.keys,
                            f"{mapping_name}{record.keys} references unknown node {node}",
                        )
                    )
                if bus_index is not None:
                    bus = record.keys[bus_index]
                    if bus not in buses:
                        issues.append(
                            ValidationIssue(
                                "unknown_bus",
                                mapping_name,
                                record.keys,
                                f"{mapping_name}{record.keys} references unknown bus {bus}",
                            )
                        )

        allocations: dict[tuple[str, ...], float] = {}
        allocation_symbol = symbols["i_dateTimeNodeBusAllocationFactor"]
        for record in allocation_symbol.records:
            scalar = record.values.get("value")
            if scalar is None or scalar.kind is not ValueKind.FINITE:
                issues.append(
                    ValidationIssue(
                        "allocation_value",
                        allocation_symbol.name,
                        record.keys,
                        f"allocation {record.keys} is not finite",
                    )
                )
                continue
            assert scalar.number is not None
            key = record.keys[:3]
            allocations[key] = allocations.get(key, 0.0) + float(scalar.number)
        for identity, total in allocations.items():
            if abs(total - 1.0) > self.allocation_tolerance:
                issues.append(
                    ValidationIssue(
                        "allocation_sum",
                        allocation_symbol.name,
                        identity,
                        f"allocation_sum {identity} is {total:.17g}, expected 1",
                    )
                )

        for name, group_dimension, block_dimension in (
            ("i_dateTimeEnergyOffer", 3, 3),
            ("i_dateTimeReserveOffer", 5, 5),
            ("i_dateTimeEnergyBid", 3, 3),
        ):
            symbol = symbols[name]
            if not symbol.records:
                continue
            block_order = {
                label: index for index, label in enumerate(symbol.uel_orders[block_dimension])
            }
            previous_by_group: dict[tuple[str, ...], int] = {}
            for record in symbol.records:
                group = record.keys[:group_dimension]
                block = record.keys[block_dimension]
                index = block_order[block]
                previous = previous_by_group.get(group, index)
                if index < previous:
                    issues.append(
                        ValidationIssue(
                            "curve_order",
                            name,
                            record.keys,
                            f"curve_order decreases at {record.keys}",
                        )
                    )
                previous_by_group[group] = index

        unique = {
            (issue.code, issue.symbol, issue.identity, issue.message): issue
            for issue in issues
        }
        return ValidationReport(tuple(unique.values()))
