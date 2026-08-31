"""Hash-bound Authority-to-PySPD report schema crosswalk evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore

REPORT_SCHEMA_CROSSWALK_PROFILE = "authority-pyspd-report-schema-crosswalk-v1"


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class _FieldRule:
    reference: str
    candidate: tuple[str, ...]
    kind: str = "direct"
    expression: str | None = None


def _rule(
    reference: str,
    *candidate: str,
    kind: str = "direct",
    expression: str | None = None,
) -> _FieldRule:
    return _FieldRule(reference, candidate, kind, expression)


_TABLE_RULES: dict[str, tuple[str, tuple[_FieldRule, ...]]] = {
    "BidResults_TP": (
        "bid",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Bid", "bid"),
            _rule("Cleared Bid (MW)", "purchase_mw"),
        ),
    ),
    "BrConstraintResults_TP": (
        "constraint",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule(
                "BranchConstraint",
                "constraint",
                "index",
                kind="derived",
                expression="constraint identity and index",
            ),
            _rule("LHS (MW)", "body"),
            _rule(
                "Sense (-1:<=, 0:=, 1:>=)",
                "lower",
                "upper",
                kind="derived",
                expression="finite lower/upper bound pattern",
            ),
            _rule(
                "RHS (MW)",
                "lower",
                "upper",
                kind="derived",
                expression="active finite bound",
            ),
        ),
    ),
    "BranchResults_TP": (
        "branch",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Branch", "branch"),
            _rule("Flow (MW) (From->To)", "flow_mw"),
        ),
    ),
    "BusResults_TP": (
        "bus",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Bus", "bus"),
            _rule("Price ($/MWh)", "repaired_price_nzd_per_mwh"),
        ),
    ),
    "IslandResults_TP": (
        "island",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Island", "island"),
            _rule(
                "FIR Price ($/MWh)",
                "reserve_class",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="reserve_class=FIR",
            ),
            _rule(
                "SIR Price ($/MWh)",
                "reserve_class",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="reserve_class=SIR",
            ),
        ),
    ),
    "MNodeConstraintResults_TP": (
        "constraint",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule(
                "MNodeConstraint",
                "constraint",
                "index",
                kind="derived",
                expression="constraint identity and index",
            ),
            _rule("LHS (MW)", "body"),
            _rule(
                "Sense (-1:<=, 0:=, 1:>=)",
                "lower",
                "upper",
                kind="derived",
                expression="finite lower/upper bound pattern",
            ),
            _rule(
                "RHS (MW)",
                "lower",
                "upper",
                kind="derived",
                expression="active finite bound",
            ),
        ),
    ),
    "NodeResults_TP": (
        "node",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Node", "node"),
            _rule("Price ($/MWh)", "price_nzd_per_mwh"),
        ),
    ),
    "OfferResults_TP": (
        "offer",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Offer", "offer"),
            _rule("Generation (MW)", "generation_mw"),
        ),
    ),
    "PublishedEnergyPrices_TP": (
        "published_price",
        (
            _rule("TradingPeriod", "trading_period"),
            _rule("Pnodename", "location"),
            _rule(
                "vSPDDollarsPerMegawattHour",
                "product",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="product=energy",
            ),
        ),
    ),
    "PublishedReservePrices_TP": (
        "published_price",
        (
            _rule("TradingPeriod", "trading_period"),
            _rule("Island", "location"),
            _rule(
                "vSPDFIRDollarsPerMegawattHour",
                "product",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="product=FIR",
            ),
            _rule(
                "vSPDSIRDollarsPerMegawattHour",
                "product",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="product=SIR",
            ),
        ),
    ),
    "ReserveResults_TP": (
        "reserve",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule("Island", "island"),
            _rule(
                "FIR Price ($/MW)",
                "reserve_class",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="reserve_class=FIR",
            ),
            _rule(
                "SIR Price ($/MW)",
                "reserve_class",
                "price_nzd_per_mwh",
                kind="pivot",
                expression="reserve_class=SIR",
            ),
        ),
    ),
    "RiskResults_TP": (
        "risk",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
        ),
    ),
    "SummaryResults_TP": (
        "summary",
        (
            _rule("CaseID", "case_id"),
            _rule("DateTime", "date_time"),
            _rule(
                "Period",
                "date_time",
                kind="derived",
                expression="trading period from date_time",
            ),
            _rule(
                "SolveStatus (1=OK)",
                "status",
                kind="derived",
                expression="status to Authority solve-status code",
            ),
            _rule("SystemOFV", "objective_nzd"),
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class ReportFieldMapping:
    reference_field: str
    candidate_fields: tuple[str, ...]
    kind: str
    expression: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_field": self.reference_field,
            "candidate_fields": list(self.candidate_fields),
            "kind": self.kind,
            "expression": self.expression,
        }


@dataclass(frozen=True, slots=True)
class ReportTableCrosswalk:
    reference_table: str
    candidate_table: str
    reference_fields: tuple[str, ...]
    candidate_fields: tuple[str, ...]
    field_mappings: tuple[ReportFieldMapping, ...]
    unmapped_reference_fields: tuple[str, ...]
    unmapped_candidate_fields: tuple[str, ...]

    @property
    def mapped_reference_fields(self) -> int:
        return len(self.field_mappings)

    @property
    def mapping_kinds(self) -> dict[str, int]:
        return dict(sorted(Counter(item.kind for item in self.field_mappings).items()))

    @property
    def passed(self) -> bool:
        return not self.unmapped_reference_fields and not self.unmapped_candidate_fields

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_table": self.reference_table,
            "candidate_table": self.candidate_table,
            "reference_fields": list(self.reference_fields),
            "candidate_fields": list(self.candidate_fields),
            "field_mappings": [item.to_dict() for item in self.field_mappings],
            "mapped_reference_fields": self.mapped_reference_fields,
            "unmapped_reference_fields": list(self.unmapped_reference_fields),
            "unmapped_candidate_fields": list(self.unmapped_candidate_fields),
            "mapping_kinds": self.mapping_kinds,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ReportCaseCrosswalk:
    case_id: str
    reference_report_sha256: str
    candidate_report_sha256: str
    tables: tuple[ReportTableCrosswalk, ...]
    unmapped_candidate_tables: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return bool(
            self.tables
            and all(item.passed for item in self.tables)
            and not self.unmapped_candidate_tables
        )

    @property
    def unmapped_reference_field_count(self) -> int:
        return sum(len(item.unmapped_reference_fields) for item in self.tables)

    @property
    def unmapped_candidate_field_count(self) -> int:
        return sum(len(item.unmapped_candidate_fields) for item in self.tables)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "reference_report_sha256": self.reference_report_sha256,
            "candidate_report_sha256": self.candidate_report_sha256,
            "unmapped_reference_field_count": self.unmapped_reference_field_count,
            "unmapped_candidate_field_count": self.unmapped_candidate_field_count,
            "unmapped_candidate_tables": list(self.unmapped_candidate_tables),
            "tables": [item.to_dict() for item in self.tables],
        }


class ReportSchemaCrosswalkValidator:
    """Compare schemas only; this class makes no row-value parity claim."""

    def compare(
        self, *, case_id: str, reference: bytes, candidate: bytes
    ) -> ReportCaseCrosswalk:
        if not case_id.strip():
            raise EvidenceContractError(
                "REQ-G12-REPORT-CROSSWALK: case identity is required"
            )
        reference_payload = self._object(reference, "reference")
        candidate_payload = self._object(candidate, "candidate")
        references: dict[str, tuple[str, ...]] = {}
        for raw_name, raw_table in reference_payload.items():
            suffixes = [
                name
                for name in _TABLE_RULES
                if raw_name == name or raw_name.endswith(f"_{name}")
            ]
            if len(suffixes) != 1:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-CROSSWALK: unknown reference table"
                )
            suffix = suffixes[0]
            if suffix in references:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-CROSSWALK: duplicate reference table"
                )
            references[suffix] = self._fields(raw_table, "fields", "reference")
        candidate_schemas = {
            name: self._fields(table, "field_order", "candidate")
            for name, table in candidate_payload.items()
        }
        tables = tuple(
            self._compare_table(name, references[name], candidate_schemas)
            for name in sorted(references)
        )
        expected_candidate_tables = {item.candidate_table for item in tables}
        return ReportCaseCrosswalk(
            case_id=case_id,
            reference_report_sha256=hashlib.sha256(reference).hexdigest(),
            candidate_report_sha256=hashlib.sha256(candidate).hexdigest(),
            tables=tables,
            unmapped_candidate_tables=tuple(
                sorted(set(candidate_schemas) - expected_candidate_tables)
            ),
        )

    def _compare_table(
        self,
        name: str,
        reference_fields: tuple[str, ...],
        candidates: dict[str, tuple[str, ...]],
    ) -> ReportTableCrosswalk:
        candidate_name, rules = _TABLE_RULES[name]
        candidate_fields = candidates.get(candidate_name, ())
        rule_by_reference = {item.reference: item for item in rules}
        mappings: list[ReportFieldMapping] = []
        consumed: set[str] = set()
        unmapped_reference: list[str] = []
        for field in reference_fields:
            rule = rule_by_reference.get(field)
            if rule is None or not set(rule.candidate).issubset(candidate_fields):
                unmapped_reference.append(field)
                continue
            mappings.append(
                ReportFieldMapping(field, rule.candidate, rule.kind, rule.expression)
            )
            consumed.update(rule.candidate)
        return ReportTableCrosswalk(
            reference_table=name,
            candidate_table=candidate_name,
            reference_fields=reference_fields,
            candidate_fields=candidate_fields,
            field_mappings=tuple(mappings),
            unmapped_reference_fields=tuple(unmapped_reference),
            unmapped_candidate_fields=tuple(
                field for field in candidate_fields if field not in consumed
            ),
        )

    @staticmethod
    def _object(raw: bytes, role: str) -> dict[str, Any]:
        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            output: dict[str, Any] = {}
            for key, value in pairs:
                if key in output:
                    raise EvidenceContractError(
                        f"REQ-G12-REPORT-CROSSWALK: duplicate {role} JSON key"
                    )
                output[key] = value
            return output

        try:
            payload = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                f"REQ-G12-REPORT-CROSSWALK: invalid {role} report JSON"
            ) from error
        if not isinstance(payload, dict) or not payload:
            raise EvidenceContractError(
                f"REQ-G12-REPORT-CROSSWALK: {role} report must be a non-empty object"
            )
        return payload

    @staticmethod
    def _fields(table: object, key: str, role: str) -> tuple[str, ...]:
        if not isinstance(table, dict) or key not in table:
            raise EvidenceContractError(
                f"REQ-G12-REPORT-CROSSWALK: malformed {role} table"
            )
        fields = table[key]
        if (
            not isinstance(fields, list)
            or not fields
            or any(not isinstance(item, str) or not item for item in fields)
            or len(fields) != len(set(fields))
        ):
            raise EvidenceContractError(
                f"REQ-G12-REPORT-CROSSWALK: invalid {role} fields"
            )
        return tuple(fields)


@dataclass(frozen=True, slots=True)
class ReportSchemaCrosswalkResult:
    trading_date: str
    source_sha256: str
    work_item_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    cases: tuple[ReportCaseCrosswalk, ...]
    logical_sha256: str

    @property
    def passed(self) -> bool:
        return bool(self.cases and all(case.passed for case in self.cases))

    @property
    def unmapped_reference_field_count(self) -> int:
        return sum(case.unmapped_reference_field_count for case in self.cases)

    @property
    def unmapped_candidate_field_count(self) -> int:
        return sum(case.unmapped_candidate_field_count for case in self.cases)

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": REPORT_SCHEMA_CROSSWALK_PROFILE,
            "scope": "schema-only-no-row-value-parity-claim",
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "work_item_sha256": self.work_item_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "passed": self.passed,
            "unmapped_reference_field_count": self.unmapped_reference_field_count,
            "unmapped_candidate_field_count": self.unmapped_candidate_field_count,
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class ReportSchemaCrosswalkRunner:
    """Crosswalk every affected case from two provenance-matched bundles."""

    def __init__(self, *, reference_root: Path, candidate_root: Path) -> None:
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.validator = ReportSchemaCrosswalkValidator()

    def compare(self, trading_date: str) -> ReportSchemaCrosswalkResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-CROSSWALK: replay bundle provenance does not match"
            )
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        cases = tuple(
            self.validator.compare(
                case_id=case.case_id,
                reference=case.surfaces["report-field"],
                candidate=candidate_by_id[case.case_id].surfaces["report-field"],
            )
            for case in reference_cases
        )
        unsigned = {
            "schema_version": 1,
            "profile": REPORT_SCHEMA_CROSSWALK_PROFILE,
            "scope": "schema-only-no-row-value-parity-claim",
            "trading_date": trading_date,
            "source_sha256": reference.source_sha256,
            "work_item_sha256": reference.work_item_sha256,
            "reference_bundle_sha256": reference.logical_sha256,
            "candidate_bundle_sha256": candidate.logical_sha256,
            "passed": bool(cases and all(case.passed for case in cases)),
            "unmapped_reference_field_count": sum(
                case.unmapped_reference_field_count for case in cases
            ),
            "unmapped_candidate_field_count": sum(
                case.unmapped_candidate_field_count for case in cases
            ),
            "cases": [case.to_dict() for case in cases],
        }
        return ReportSchemaCrosswalkResult(
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            work_item_sha256=reference.work_item_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            cases=cases,
            logical_sha256=_logical_sha256(unsigned),
        )


class ReportSchemaCrosswalkResultStore:
    """Atomically persist one immutable, self-hashed crosswalk artifact."""

    def write(self, result: ReportSchemaCrosswalkResult, target: Path) -> Path:
        if result.logical_sha256 != _logical_sha256(result.to_dict(include_hash=False)):
            raise EvidenceContractError(
                "REQ-G12-REPORT-CROSSWALK: result hash mismatch"
            )
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-REPORT-CROSSWALK: result already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target
