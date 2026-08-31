"""Qualified alternative-optimum evidence for published Gate 12 prices."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.orchestration.types import CaseRunStatus, RunEventKind
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.execution_provenance import python_execution_sha256
from tools.gate12.historical_population import GamsTransferCaseIndexLoader
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore

PUBLISHED_PRICE_DEGENERACY_PROFILE = "gams-pyspd-published-alternative-optimum-v1"


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class PublishedPriceValueCertificate:
    """One published value reproduced by a qualified alternative solve path."""

    product: str
    identity: tuple[str, ...]
    reference: float
    governed_candidate: float
    qualified_alternative: float
    tolerance: float
    all_cases_complete: bool
    fallback_count: int

    @property
    def governed_absolute_error(self) -> float:
        return abs(self.reference - self.governed_candidate)

    @property
    def alternative_absolute_error(self) -> float:
        return abs(self.reference - self.qualified_alternative)

    @property
    def reference_within_observed_envelope(self) -> bool:
        lower = min(self.governed_candidate, self.qualified_alternative)
        upper = max(self.governed_candidate, self.qualified_alternative)
        return lower - self.tolerance <= self.reference <= upper + self.tolerance

    @property
    def passed(self) -> bool:
        return (
            self.all_cases_complete
            and self.fallback_count == 0
            and self.alternative_absolute_error <= self.tolerance
            and self.reference_within_observed_envelope
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "product": self.product,
            "identity": list(self.identity),
            "reference": self.reference.hex(),
            "governed_candidate": self.governed_candidate.hex(),
            "qualified_alternative": self.qualified_alternative.hex(),
            "tolerance": self.tolerance.hex(),
            "governed_absolute_error": self.governed_absolute_error.hex(),
            "alternative_absolute_error": self.alternative_absolute_error.hex(),
            "reference_within_observed_envelope": (
                self.reference_within_observed_envelope
            ),
            "all_cases_complete": self.all_cases_complete,
            "fallback_count": self.fallback_count,
            "passed": self.passed,
        }


class PublishedPriceAlternativeValidator:
    """Require an optimal no-fallback alternative that matches the oracle."""

    def __init__(self, *, tolerance: float = 1e-4) -> None:
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise EvidenceContractError(
                "REQ-G12-PUBLISHED-CERT: tolerance must be finite and non-negative"
            )
        self.tolerance = tolerance

    def compare(
        self,
        *,
        product: str,
        identity: tuple[str, ...],
        reference: float,
        governed_candidate: float,
        qualified_alternative: float,
        all_cases_complete: bool,
        fallback_count: int,
    ) -> PublishedPriceValueCertificate:
        values = (reference, governed_candidate, qualified_alternative)
        if (
            product not in {"energy", "reserve"}
            or not identity
            or any(not item for item in identity)
            or any(not math.isfinite(value) for value in values)
            or isinstance(fallback_count, bool)
            or fallback_count < 0
        ):
            raise EvidenceContractError(
                "REQ-G12-PUBLISHED-CERT: invalid alternative-price evidence"
            )
        return PublishedPriceValueCertificate(
            product=product,
            identity=identity,
            reference=reference,
            governed_candidate=governed_candidate,
            qualified_alternative=qualified_alternative,
            tolerance=self.tolerance,
            all_cases_complete=all_cases_complete,
            fallback_count=fallback_count,
        )


@dataclass(frozen=True, slots=True)
class PublishedPricePeriodCertificate:
    """One period's qualified warmup and target-case execution evidence."""

    trading_period: str
    warmup_case_id: str
    target_case_ids: tuple[str, ...]
    report_manifest_sha256: str
    values: tuple[PublishedPriceValueCertificate, ...]

    @property
    def passed(self) -> bool:
        return bool(self.values and all(value.passed for value in self.values))

    def to_dict(self) -> dict[str, object]:
        return {
            "trading_period": self.trading_period,
            "warmup_case_id": self.warmup_case_id,
            "target_case_ids": list(self.target_case_ids),
            "report_manifest_sha256": self.report_manifest_sha256,
            "passed": self.passed,
            "values": [value.to_dict() for value in self.values],
        }


@dataclass(frozen=True, slots=True)
class PublishedPriceDegeneracyResult:
    """Hash-bound daily alternative-optimum published-price certificate."""

    trading_date: str
    source_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    execution_sha256: str
    periods: tuple[PublishedPricePeriodCertificate, ...]
    logical_sha256: str

    @property
    def passed(self) -> bool:
        return bool(self.periods and all(period.passed for period in self.periods))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": PUBLISHED_PRICE_DEGENERACY_PROFILE,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "execution_sha256": self.execution_sha256,
            "passed": self.passed,
            "periods": [period.to_dict() for period in self.periods],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


def _published_values(payload: bytes) -> dict[tuple[str, tuple[str, ...]], float]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceContractError(
            "REQ-G12-PUBLISHED-CERT: unreadable rounded publication surface"
        ) from error
    output: dict[tuple[str, tuple[str, ...]], float] = {}
    try:
        for product in ("energy", "reserve"):
            for row in document[product]:
                identity = tuple(row["identity"])
                output[(product, identity)] = float.fromhex(row["value"])
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceContractError(
            "REQ-G12-PUBLISHED-CERT: invalid rounded publication surface"
        ) from error
    return output


class PublishedPriceDegeneracyRunner:
    """Rerun one warmup plus each discrepant period under the qualified profile."""

    def __init__(
        self,
        *,
        input_path: Path,
        system_directory: Path,
        reference_root: Path,
        candidate_root: Path,
        run_root: Path,
    ) -> None:
        self.input_path = input_path
        self.system_directory = system_directory
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.run_root = run_root
        self.validator = PublishedPriceAlternativeValidator()

    def run(self, trading_date: str) -> PublishedPriceDegeneracyResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-PUBLISHED-CERT: replay bundle provenance does not match"
            )
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        targets: dict[
            str, dict[tuple[str, tuple[str, ...]], tuple[float, float]]
        ] = {}
        for expected in reference_cases:
            actual = candidate_by_id[expected.case_id]
            expected_values = _published_values(
                expected.surfaces["rounded-published-output"]
            )
            actual_values = _published_values(
                actual.surfaces["rounded-published-output"]
            )
            for key in set(expected_values) & set(actual_values):
                error = abs(expected_values[key] - actual_values[key])
                if error > self.validator.tolerance:
                    period = key[1][0]
                    targets.setdefault(period, {})[key] = (
                        expected_values[key],
                        actual_values[key],
                    )
        if not targets:
            raise EvidenceContractError(
                "REQ-G12-PUBLISHED-CERT: no above-tolerance published price"
            )
        index = GamsTransferCaseIndexLoader().load(
            self.input_path, self.system_directory
        )
        ordered = tuple(index.cases)
        periods = []
        for period, values in sorted(targets.items()):
            positions = [
                position
                for position, case in enumerate(ordered)
                if index.trading_periods[case] == period
            ]
            if not positions or positions[0] == 0:
                raise EvidenceContractError(
                    "REQ-G12-PUBLISHED-CERT: target period has no warmup case"
                )
            warmup = ordered[positions[0] - 1]
            target_cases = tuple(ordered[position] for position in positions)
            case_ids = (warmup[0], *(case[0] for case in target_cases))
            output = self.run_root / trading_date / period
            if output.exists():
                raise EvidenceContractError(
                    "REQ-G12-PUBLISHED-CERT: alternative run output already exists"
                )
            configuration = ApplicationConfiguration(
                formulation_id=RESERVE_FORMULATION_ID,
                input_path=self.input_path,
                output_directory=output,
                source_sha256=reference.source_sha256,
                gams_system_directory=self.system_directory,
                case_ids=case_ids,
            )
            alternative = PyspdApplication().run(configuration)
            target_results = alternative.result.cases[1:]
            all_complete = all(
                case.status is CaseRunStatus.COMPLETE for case in target_results
            )
            fallback_count = sum(
                event.kind is RunEventKind.INITIALIZED
                and bool(event.details.get("prior_period_fallback"))
                for case in target_results
                for event in case.events
            )
            if alternative.result.published is None:
                raise EvidenceContractError(
                    "REQ-G12-PUBLISHED-CERT: alternative publication is absent"
                )
            certificates = []
            for (product, identity), (reference_value, governed) in sorted(
                values.items()
            ):
                published = alternative.result.published
                if product == "energy" and len(identity) == 2:
                    alternative_value = published.energy[(identity[0], identity[1])]
                elif product == "reserve" and len(identity) == 3:
                    alternative_value = published.reserve[
                        (identity[0], identity[1], identity[2])
                    ]
                else:
                    raise EvidenceContractError(
                        "REQ-G12-PUBLISHED-CERT: published identity arity mismatch"
                    )
                certificates.append(
                    self.validator.compare(
                        product=product,
                        identity=identity,
                        reference=reference_value,
                        governed_candidate=governed,
                        qualified_alternative=alternative_value,
                        all_cases_complete=all_complete,
                        fallback_count=fallback_count,
                    )
                )
            periods.append(
                PublishedPricePeriodCertificate(
                    trading_period=period,
                    warmup_case_id=warmup[0],
                    target_case_ids=tuple(case[0] for case in target_cases),
                    report_manifest_sha256=alternative.report_manifest.logical_sha256,
                    values=tuple(certificates),
                )
            )
        execution_sha256 = python_execution_sha256()
        unsigned = {
            "schema_version": 1,
            "profile": PUBLISHED_PRICE_DEGENERACY_PROFILE,
            "trading_date": trading_date,
            "source_sha256": reference.source_sha256,
            "reference_bundle_sha256": reference.logical_sha256,
            "candidate_bundle_sha256": candidate.logical_sha256,
            "execution_sha256": execution_sha256,
            "passed": bool(periods and all(period.passed for period in periods)),
            "periods": [period.to_dict() for period in periods],
        }
        return PublishedPriceDegeneracyResult(
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            execution_sha256=execution_sha256,
            periods=tuple(periods),
            logical_sha256=_logical_sha256(unsigned),
        )


class PublishedPriceDegeneracyResultStore:
    """Atomically persist an immutable published-price certificate."""

    def write(self, result: PublishedPriceDegeneracyResult, target: Path) -> Path:
        if result.logical_sha256 != _logical_sha256(
            result.to_dict(include_hash=False)
        ):
            raise EvidenceContractError(
                "REQ-G12-PUBLISHED-CERT: certificate hash mismatch"
            )
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-PUBLISHED-CERT: certificate output already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target
