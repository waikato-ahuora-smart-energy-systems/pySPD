"""Identity-strict row parity for proven Authority/PySPD report mappings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from tools.gate12.bus_price_degeneracy import (
    BusPriceCaseCertificate,
    BusPriceDegeneracyResult,
)
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore
from tools.gate12.report_crosswalk import (
    REPORT_SCHEMA_CROSSWALK_PROFILE,
    ReportSchemaCrosswalkValidator,
)
from tools.gate12.zero_flow_price_convention import (
    ZeroFlowPriceConventionResult,
)

REPORT_ROW_PARITY_PROFILE = "authority-pyspd-mapped-report-row-parity-v2"
REPORT_ROW_BUS_CERTIFIED_PROFILE = (
    "authority-pyspd-mapped-report-row-parity-bus-certified-v2"
)
REPORT_ROW_ZERO_FLOW_CERTIFIED_PROFILE = (
    "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v2"
)
_MAX_EXAMPLES = 20


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _identity(value: str) -> str:
    return value


def _pipe_tail(value: str) -> str:
    return value.rsplit("|", 1)[-1]


@dataclass(frozen=True, slots=True)
class _Projection:
    reference_table: str
    candidate_table: str
    observable: str
    reference_identity: tuple[str, ...]
    candidate_identity: tuple[str, ...]
    reference_value: str
    candidate_value: str
    candidate_filter: tuple[str, str] | None = None
    candidate_filter_prefix: tuple[str, str] | None = None
    candidate_support_fields: tuple[str, ...] = ()
    candidate_value_resolver: Callable[[dict[str, str]], str] | None = None
    candidate_identity_normalizer: Callable[[str], str] = _identity


def _projection(
    reference_table: str,
    candidate_table: str,
    observable: str,
    reference_identity: tuple[str, ...],
    candidate_identity: tuple[str, ...],
    reference_value: str,
    candidate_value: str,
    *,
    candidate_filter: tuple[str, str] | None = None,
    candidate_filter_prefix: tuple[str, str] | None = None,
    candidate_support_fields: tuple[str, ...] = (),
    candidate_value_resolver: Callable[[dict[str, str]], str] | None = None,
    candidate_identity_normalizer: Callable[[str], str] = _identity,
) -> _Projection:
    return _Projection(
        reference_table,
        candidate_table,
        observable,
        reference_identity,
        candidate_identity,
        reference_value,
        candidate_value,
        candidate_filter,
        candidate_filter_prefix,
        candidate_support_fields,
        candidate_value_resolver,
        candidate_identity_normalizer,
    )


def _active_bound(row: dict[str, str]) -> str:
    lower = row.get("lower", "")
    upper = row.get("upper", "")
    if lower and upper:
        if Decimal(lower) != Decimal(upper):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: ranged constraint has no single RHS"
            )
        return lower
    if lower:
        return lower
    if upper:
        return upper
    raise EvidenceContractError("REQ-G12-REPORT-ROW: constraint has no finite RHS")


def _constraint_sense(row: dict[str, str]) -> str:
    lower = bool(row.get("lower", ""))
    upper = bool(row.get("upper", ""))
    if lower and upper:
        return "0"
    if lower:
        return "1"
    if upper:
        return "-1"
    raise EvidenceContractError("REQ-G12-REPORT-ROW: constraint has no finite sense")


_CASE_TIME = ("CaseID", "DateTime")
_CASE_TIME_CANDIDATE = ("case_id", "date_time")
_PROJECTIONS = (
    _projection(
        "BidResults_TP",
        "bid",
        "cleared-bid-mw",
        (*_CASE_TIME, "Bid"),
        (*_CASE_TIME_CANDIDATE, "bid"),
        "Cleared Bid (MW)",
        "purchase_mw",
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-lhs",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "LHS (MW)",
        "body",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-rhs",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "RHS (MW)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_active_bound,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-sense",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "Sense (-1:<=, 0:=, 1:>=)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_constraint_sense,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BranchResults_TP",
        "branch",
        "branch-flow-mw",
        (*_CASE_TIME, "Branch"),
        (*_CASE_TIME_CANDIDATE, "branch"),
        "Flow (MW) (From->To)",
        "flow_mw",
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BusResults_TP",
        "bus",
        "repaired-bus-price",
        (*_CASE_TIME, "Bus"),
        (*_CASE_TIME_CANDIDATE, "bus"),
        "Price ($/MWh)",
        "repaired_price_nzd_per_mwh",
    ),
    _projection(
        "IslandResults_TP",
        "island",
        "FIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "FIR Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "FIR"),
    ),
    _projection(
        "IslandResults_TP",
        "island",
        "SIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "SIR Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "SIR"),
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-lhs",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "LHS (MW)",
        "body",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-rhs",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "RHS (MW)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_active_bound,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-sense",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "Sense (-1:<=, 0:=, 1:>=)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_constraint_sense,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "NodeResults_TP",
        "node",
        "node-price",
        (*_CASE_TIME, "Node"),
        (*_CASE_TIME_CANDIDATE, "node"),
        "Price ($/MWh)",
        "price_nzd_per_mwh",
    ),
    _projection(
        "OfferResults_TP",
        "offer",
        "generation-mw",
        (*_CASE_TIME, "Offer"),
        (*_CASE_TIME_CANDIDATE, "offer"),
        "Generation (MW)",
        "generation_mw",
    ),
    _projection(
        "PublishedEnergyPrices_TP",
        "published_price",
        "published-energy-price",
        ("TradingPeriod", "Pnodename"),
        ("trading_period", "location"),
        "vSPDDollarsPerMegawattHour",
        "price_nzd_per_mwh",
        candidate_filter=("product", "energy"),
    ),
    _projection(
        "PublishedReservePrices_TP",
        "published_price",
        "published-FIR-price",
        ("TradingPeriod", "Island"),
        ("trading_period", "location"),
        "vSPDFIRDollarsPerMegawattHour",
        "price_nzd_per_mwh",
        candidate_filter=("product", "FIR"),
    ),
    _projection(
        "PublishedReservePrices_TP",
        "published_price",
        "published-SIR-price",
        ("TradingPeriod", "Island"),
        ("trading_period", "location"),
        "vSPDSIRDollarsPerMegawattHour",
        "price_nzd_per_mwh",
        candidate_filter=("product", "SIR"),
    ),
    _projection(
        "ReserveResults_TP",
        "reserve",
        "FIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "FIR Price ($/MW)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "FIR"),
    ),
    _projection(
        "ReserveResults_TP",
        "reserve",
        "SIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "SIR Price ($/MW)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "SIR"),
    ),
    _projection(
        "SummaryResults_TP",
        "summary",
        "system-objective",
        _CASE_TIME,
        _CASE_TIME_CANDIDATE,
        "SystemOFV",
        "objective_nzd",
    ),
)


@dataclass(frozen=True, slots=True)
class ReportValueDifference:
    observable: str
    identity: tuple[str, ...]
    reference_value: str
    candidate_value: str
    absolute_error: str
    authority_half_unit: str

    def to_dict(self) -> dict[str, object]:
        return {
            "observable": self.observable,
            "identity": list(self.identity),
            "reference_value": self.reference_value,
            "candidate_value": self.candidate_value,
            "absolute_error": self.absolute_error,
            "authority_half_unit": self.authority_half_unit,
        }


@dataclass(frozen=True, slots=True)
class ReportRowTableResult:
    reference_table: str
    candidate_table: str
    observables: tuple[str, ...]
    compared_value_count: int
    missing_identity_count: int
    extra_identity_count: int
    certified_difference_count: int
    above_precision_count: int
    maximum_absolute_error: str
    missing_identity_examples: tuple[tuple[str, ...], ...]
    extra_identity_examples: tuple[tuple[str, ...], ...]
    differences: tuple[ReportValueDifference, ...]

    @property
    def passed(self) -> bool:
        return (
            self.missing_identity_count == 0
            and self.extra_identity_count == 0
            and self.above_precision_count == 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_table": self.reference_table,
            "candidate_table": self.candidate_table,
            "observables": list(self.observables),
            "passed": self.passed,
            "compared_value_count": self.compared_value_count,
            "missing_identity_count": self.missing_identity_count,
            "extra_identity_count": self.extra_identity_count,
            "certified_difference_count": self.certified_difference_count,
            "above_precision_count": self.above_precision_count,
            "maximum_absolute_error": self.maximum_absolute_error,
            "missing_identity_examples": [
                list(identity) for identity in self.missing_identity_examples
            ],
            "extra_identity_examples": [
                list(identity) for identity in self.extra_identity_examples
            ],
            "differences": [item.to_dict() for item in self.differences],
        }


@dataclass(frozen=True, slots=True)
class ReportCaseRowParity:
    case_id: str
    reference_report_sha256: str
    candidate_report_sha256: str
    tables: tuple[ReportRowTableResult, ...]
    unimplemented_reference_tables: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return bool(
            self.tables
            and all(table.passed for table in self.tables)
            and not self.unimplemented_reference_tables
        )

    @property
    def missing_identity_count(self) -> int:
        return sum(table.missing_identity_count for table in self.tables)

    @property
    def extra_identity_count(self) -> int:
        return sum(table.extra_identity_count for table in self.tables)

    @property
    def above_precision_count(self) -> int:
        return sum(table.above_precision_count for table in self.tables)

    @property
    def certified_difference_count(self) -> int:
        return sum(table.certified_difference_count for table in self.tables)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "reference_report_sha256": self.reference_report_sha256,
            "candidate_report_sha256": self.candidate_report_sha256,
            "missing_identity_count": self.missing_identity_count,
            "extra_identity_count": self.extra_identity_count,
            "certified_difference_count": self.certified_difference_count,
            "above_precision_count": self.above_precision_count,
            "unimplemented_reference_tables": list(self.unimplemented_reference_tables),
            "tables": [table.to_dict() for table in self.tables],
        }


class ReportRowParityValidator:
    """Project only fields admitted by the schema crosswalk and compare rows."""

    def compare(
        self,
        *,
        case_id: str,
        reference: bytes,
        candidate: bytes,
        bus_price_certificate: BusPriceCaseCertificate | None = None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None = None,
    ) -> ReportCaseRowParity:
        if bus_price_certificate is not None and (
            not bus_price_certificate.passed or bus_price_certificate.case_id != case_id
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: invalid case bus-price certificate"
            )
        if (
            zero_flow_price_certificate is not None
            and not zero_flow_price_certificate.passed
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: invalid zero-flow price certificate"
            )
        schema = ReportSchemaCrosswalkValidator().compare(
            case_id=case_id, reference=reference, candidate=candidate
        )
        reference_payload = self._payload(reference, "reference")
        candidate_payload = self._payload(candidate, "candidate")
        reference_tables = self._reference_tables(reference_payload)
        mapping_by_table = {
            table.reference_table: {
                mapping.reference_field: mapping for mapping in table.field_mappings
            }
            for table in schema.tables
        }
        results = []
        implemented: set[str] = set()
        for reference_table in sorted(reference_tables):
            projections = tuple(
                item
                for item in _PROJECTIONS
                if item.reference_table == reference_table
                and self._admitted(item, mapping_by_table.get(reference_table, {}))
            )
            if not projections:
                continue
            implemented.add(reference_table)
            results.append(
                self._compare_table(
                    projections,
                    reference_tables[reference_table],
                    candidate_payload.get(projections[0].candidate_table),
                    bus_price_certificate,
                    zero_flow_price_certificate,
                )
            )
        return ReportCaseRowParity(
            case_id=case_id,
            reference_report_sha256=hashlib.sha256(reference).hexdigest(),
            candidate_report_sha256=hashlib.sha256(candidate).hexdigest(),
            tables=tuple(results),
            unimplemented_reference_tables=tuple(
                sorted(set(reference_tables) - implemented)
            ),
        )

    @staticmethod
    def _admitted(projection: _Projection, mappings: dict[str, Any]) -> bool:
        value_mapping = mappings.get(projection.reference_value)
        required_value_fields = {
            projection.candidate_value,
            *projection.candidate_support_fields,
        }
        if value_mapping is None or not required_value_fields.issubset(
            value_mapping.candidate_fields
        ):
            return False
        for reference_field, candidate_field in zip(
            projection.reference_identity, projection.candidate_identity, strict=True
        ):
            identity_mapping = mappings.get(reference_field)
            if (
                identity_mapping is None
                or candidate_field not in identity_mapping.candidate_fields
            ):
                return False
        return True

    def _compare_table(
        self,
        projections: tuple[_Projection, ...],
        reference_table: dict[str, Any],
        candidate_table: object,
        bus_price_certificate: BusPriceCaseCertificate | None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None,
    ) -> ReportRowTableResult:
        candidate_name = projections[0].candidate_table
        reference_rows = self._rows(reference_table, "reference")
        candidate_rows = self._rows(candidate_table, "candidate")
        compared = missing = extra = certified = above = 0
        maximum = Decimal(0)
        missing_examples: list[tuple[str, ...]] = []
        extra_examples: list[tuple[str, ...]] = []
        differences: list[ReportValueDifference] = []
        for projection in projections:
            expected = self._indexed_values(reference_rows, projection, reference=True)
            actual = self._indexed_values(candidate_rows, projection, reference=False)
            missing_keys = sorted(set(expected) - set(actual))
            extra_keys = sorted(set(actual) - set(expected))
            missing += len(missing_keys)
            extra += len(extra_keys)
            missing_examples.extend(
                missing_keys[: max(0, _MAX_EXAMPLES - len(missing_examples))]
            )
            extra_examples.extend(
                extra_keys[: max(0, _MAX_EXAMPLES - len(extra_examples))]
            )
            for key in sorted(set(expected) & set(actual)):
                reference_text = expected[key]
                candidate_text = actual[key]
                reference_value = self._decimal(reference_text)
                candidate_value = self._decimal(candidate_text)
                absolute_error = abs(reference_value - candidate_value)
                maximum = max(maximum, absolute_error)
                exponent = cast(int, reference_value.as_tuple().exponent)
                half_unit = Decimal(5).scaleb(exponent - 1)
                compared += 1
                if absolute_error <= half_unit:
                    continue
                if (
                    projection.reference_table == "BusResults_TP"
                    and projection.observable == "repaired-bus-price"
                    and bus_price_certificate is not None
                ):
                    certified += 1
                    continue
                if (
                    zero_flow_price_certificate is not None
                    and self._zero_flow_certifies_report_value(
                        zero_flow_price_certificate,
                        projection.observable,
                        key,
                    )
                ):
                    certified += 1
                    continue
                above += 1
                if len(differences) < _MAX_EXAMPLES:
                    differences.append(
                        ReportValueDifference(
                            projection.observable,
                            key,
                            reference_text,
                            candidate_text,
                            format(absolute_error, "f"),
                            format(half_unit, "f"),
                        )
                    )
        return ReportRowTableResult(
            reference_table=projections[0].reference_table,
            candidate_table=candidate_name,
            observables=tuple(item.observable for item in projections),
            compared_value_count=compared,
            missing_identity_count=missing,
            extra_identity_count=extra,
            certified_difference_count=certified,
            above_precision_count=above,
            maximum_absolute_error=format(maximum, "f"),
            missing_identity_examples=tuple(missing_examples),
            extra_identity_examples=tuple(extra_examples),
            differences=tuple(differences),
        )

    @staticmethod
    def _zero_flow_certifies_report_value(
        certificate: ZeroFlowPriceConventionResult,
        observable: str,
        identity: tuple[str, ...],
    ) -> bool:
        if observable == "repaired-bus-price" and len(identity) >= 3:
            return certificate.certifies_bus(identity[0], identity[2])
        if observable == "node-price" and len(identity) >= 3:
            return certificate.certifies_node(identity[0], identity[2])
        if observable == "published-energy-price" and len(identity) >= 2:
            return certificate.certifies_publication(identity[0], identity[1])
        return False

    def _indexed_values(
        self,
        rows: tuple[dict[str, str], ...],
        projection: _Projection,
        *,
        reference: bool,
    ) -> dict[tuple[str, ...], str]:
        fields = (
            projection.reference_identity
            if reference
            else projection.candidate_identity
        )
        value_field = (
            projection.reference_value if reference else projection.candidate_value
        )
        indexed: dict[tuple[str, ...], str] = {}
        for row in rows:
            if not reference and projection.candidate_filter is not None:
                filter_field, filter_value = projection.candidate_filter
                if row.get(filter_field) != filter_value:
                    continue
            if not reference and projection.candidate_filter_prefix is not None:
                filter_field, filter_prefix = projection.candidate_filter_prefix
                if not row.get(filter_field, "").startswith(filter_prefix):
                    continue
            try:
                identity = tuple(row[field] for field in fields)
                value = (
                    projection.candidate_value_resolver(row)
                    if not reference and projection.candidate_value_resolver is not None
                    else row[value_field]
                )
            except KeyError as error:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: projected row field is unavailable"
                ) from error
            if not reference:
                identity = (
                    *identity[:-1],
                    projection.candidate_identity_normalizer(identity[-1]),
                )
            key = (*identity, projection.observable)
            if key in indexed:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: duplicate projected row identity"
                )
            indexed[key] = value
        return indexed

    @staticmethod
    def _decimal(value: str) -> Decimal:
        try:
            parsed = Decimal(value)
        except InvalidOperation as error:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: projected value is not numeric"
            ) from error
        if not parsed.is_finite():
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: projected value is not finite"
            )
        return parsed

    @staticmethod
    def _payload(raw: bytes, role: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                f"REQ-G12-REPORT-ROW: invalid {role} report JSON"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError(
                f"REQ-G12-REPORT-ROW: {role} report must be an object"
            )
        return payload

    @staticmethod
    def _reference_tables(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        supported_names = {item.reference_table for item in _PROJECTIONS}
        supported_names.update(
            {
                "BrConstraintResults_TP",
                "MNodeConstraintResults_TP",
                "RiskResults_TP",
            }
        )
        output: dict[str, dict[str, Any]] = {}
        for raw_name, table in payload.items():
            matches = [
                name
                for name in supported_names
                if raw_name == name or raw_name.endswith(f"_{name}")
            ]
            if len(matches) != 1 or not isinstance(table, dict):
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: invalid reference table"
                )
            output[matches[0]] = table
        return output

    @staticmethod
    def _rows(table: object, role: str) -> tuple[dict[str, str], ...]:
        if table is None:
            return ()
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            raise EvidenceContractError(
                f"REQ-G12-REPORT-ROW: malformed {role} table rows"
            )
        rows = table["rows"]
        if any(
            not isinstance(row, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in row.items()
            )
            for row in rows
        ):
            raise EvidenceContractError(f"REQ-G12-REPORT-ROW: invalid {role} row")
        return tuple(rows)


@dataclass(frozen=True, slots=True)
class ReportRowParityResult:
    profile: str
    trading_date: str
    source_sha256: str
    work_item_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    schema_crosswalk_sha256: str
    bus_price_certificate_sha256: str | None
    zero_flow_price_certificate_sha256: str | None
    cases: tuple[ReportCaseRowParity, ...]
    logical_sha256: str

    @property
    def passed(self) -> bool:
        return bool(self.cases and all(case.passed for case in self.cases))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": self.profile,
            "scope": "mapped-fields-at-authority-display-precision",
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "work_item_sha256": self.work_item_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "schema_crosswalk_sha256": self.schema_crosswalk_sha256,
            "bus_price_certificate_sha256": self.bus_price_certificate_sha256,
            "zero_flow_price_certificate_sha256": (
                self.zero_flow_price_certificate_sha256
            ),
            "passed": self.passed,
            "missing_identity_count": sum(
                case.missing_identity_count for case in self.cases
            ),
            "extra_identity_count": sum(
                case.extra_identity_count for case in self.cases
            ),
            "certified_difference_count": sum(
                case.certified_difference_count for case in self.cases
            ),
            "above_precision_count": sum(
                case.above_precision_count for case in self.cases
            ),
            "unimplemented_table_count": sum(
                len(case.unimplemented_reference_tables) for case in self.cases
            ),
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class ReportRowParityRunner:
    """Compare mapped rows after verifying the exact schema-crosswalk artifact."""

    def __init__(
        self,
        *,
        reference_root: Path,
        candidate_root: Path,
        schema_crosswalk: Path,
        bus_price_certificate: BusPriceDegeneracyResult | None = None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None = None,
    ) -> None:
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.schema_payload, self.schema_sha256 = self._load_crosswalk(schema_crosswalk)
        self.bus_price_certificate = bus_price_certificate
        self.zero_flow_price_certificate = zero_flow_price_certificate
        self.validator = ReportRowParityValidator()

    def compare(self, trading_date: str) -> ReportRowParityResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
            or self.schema_payload.get("trading_date") != trading_date
            or self.schema_payload.get("source_sha256") != reference.source_sha256
            or self.schema_payload.get("work_item_sha256") != reference.work_item_sha256
            or self.schema_payload.get("reference_bundle_sha256")
            != reference.logical_sha256
            or self.schema_payload.get("candidate_bundle_sha256")
            != candidate.logical_sha256
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: bundle/crosswalk provenance does not match"
            )
        crosswalk_cases = {
            item["case_id"]: item
            for item in self.schema_payload.get("cases", [])
            if isinstance(item, dict) and isinstance(item.get("case_id"), str)
        }
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        certificate_by_id: dict[str, BusPriceCaseCertificate] = {}
        profile = REPORT_ROW_PARITY_PROFILE
        certificate_sha256 = None
        if self.bus_price_certificate is not None:
            certificate = self.bus_price_certificate
            certificate.validate()
            if (
                not certificate.passed
                or certificate.trading_date != trading_date
                or certificate.source_sha256 != reference.source_sha256
                or certificate.reference_bundle_sha256 != reference.logical_sha256
                or certificate.candidate_bundle_sha256 != candidate.logical_sha256
                or tuple(case.case_id for case in certificate.cases)
                != reference.affected_case_ids
            ):
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: bus-price certificate provenance does not match"
                )
            certificate_by_id = {case.case_id: case for case in certificate.cases}
            profile = REPORT_ROW_BUS_CERTIFIED_PROFILE
            certificate_sha256 = certificate.logical_sha256
        zero_flow_certificate_sha256 = None
        if self.zero_flow_price_certificate is not None:
            zero_flow = self.zero_flow_price_certificate
            zero_flow.validate()
            if (
                not zero_flow.passed
                or zero_flow.trading_date != trading_date
                or zero_flow.source_sha256 != reference.source_sha256
                or zero_flow.reference_bundle_sha256 != reference.logical_sha256
                or zero_flow.candidate_bundle_sha256 != candidate.logical_sha256
                or tuple(case.case_id for case in zero_flow.cases)
                != reference.affected_case_ids
            ):
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: zero-flow certificate provenance does not match"
                )
            profile = REPORT_ROW_ZERO_FLOW_CERTIFIED_PROFILE
            zero_flow_certificate_sha256 = zero_flow.logical_sha256
        cases = []
        for expected in reference_cases:
            actual = candidate_by_id[expected.case_id]
            recomputed = ReportSchemaCrosswalkValidator().compare(
                case_id=expected.case_id,
                reference=expected.surfaces["report-field"],
                candidate=actual.surfaces["report-field"],
            )
            if crosswalk_cases.get(expected.case_id) != recomputed.to_dict():
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: schema crosswalk case does not match"
                )
            cases.append(
                self.validator.compare(
                    case_id=expected.case_id,
                    reference=expected.surfaces["report-field"],
                    candidate=actual.surfaces["report-field"],
                    bus_price_certificate=certificate_by_id.get(expected.case_id),
                    zero_flow_price_certificate=self.zero_flow_price_certificate,
                )
            )
        unsigned = self._unsigned(
            profile,
            trading_date,
            reference.source_sha256,
            reference.work_item_sha256,
            reference.logical_sha256,
            candidate.logical_sha256,
            certificate_sha256,
            zero_flow_certificate_sha256,
            tuple(cases),
        )
        return ReportRowParityResult(
            profile=profile,
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            work_item_sha256=reference.work_item_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            schema_crosswalk_sha256=self.schema_sha256,
            bus_price_certificate_sha256=certificate_sha256,
            zero_flow_price_certificate_sha256=zero_flow_certificate_sha256,
            cases=tuple(cases),
            logical_sha256=_logical_sha256(unsigned),
        )

    def _unsigned(
        self,
        profile: str,
        trading_date: str,
        source_sha256: str,
        work_item_sha256: str,
        reference_bundle_sha256: str,
        candidate_bundle_sha256: str,
        bus_price_certificate_sha256: str | None,
        zero_flow_price_certificate_sha256: str | None,
        cases: tuple[ReportCaseRowParity, ...],
    ) -> dict[str, object]:
        result = ReportRowParityResult(
            profile,
            trading_date,
            source_sha256,
            work_item_sha256,
            reference_bundle_sha256,
            candidate_bundle_sha256,
            self.schema_sha256,
            bus_price_certificate_sha256,
            zero_flow_price_certificate_sha256,
            cases,
            "",
        )
        return result.to_dict(include_hash=False)

    @staticmethod
    def _load_crosswalk(path: Path) -> tuple[dict[str, Any], str]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: unreadable schema crosswalk"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError("REQ-G12-REPORT-ROW: invalid schema crosswalk")
        logical_sha256 = payload.pop("logical_sha256", None)
        if (
            payload.get("profile") != REPORT_SCHEMA_CROSSWALK_PROFILE
            or payload.get("scope") != "schema-only-no-row-value-parity-claim"
            or logical_sha256 != _logical_sha256(payload)
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: schema crosswalk hash/profile mismatch"
            )
        return payload, logical_sha256


class ReportRowParityResultStore:
    """Atomically persist one immutable mapped-row comparison."""

    def write(self, result: ReportRowParityResult, target: Path) -> Path:
        if result.logical_sha256 != _logical_sha256(result.to_dict(include_hash=False)):
            raise EvidenceContractError("REQ-G12-REPORT-ROW: result hash mismatch")
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError("REQ-G12-REPORT-ROW: result already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target
