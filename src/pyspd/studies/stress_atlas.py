"""Hash-bound classification of historical CPLEX result days by stress signal."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class AtlasError(ValueError):
    """An atlas source or result violates the preregistered contract."""


class StressCategory(StrEnum):
    """Stable machine-readable stress-event categories."""

    DST_LONG_DAY = "dst-long-day"
    DST_SHORT_DAY = "dst-short-day"
    HIGH_ENERGY_PRICE = "high-energy-price"
    HIGH_RESERVE_PRICE = "high-reserve-price"
    NEGATIVE_ENERGY_PRICE = "negative-energy-price"
    NETWORK_STRESS = "network-stress"
    SOLVE_FAILURE = "solve-failure"
    VIOLATION = "violation"


@dataclass(frozen=True, slots=True)
class AtlasThresholds:
    high_energy_price: float = 1_000.0
    negative_energy_price: float = 0.0
    high_reserve_price: float = 300.0
    network_utilization: float = 0.98
    violation_mw: float = 1e-6

    def __post_init__(self) -> None:
        values = (
            self.high_energy_price,
            self.negative_energy_price,
            self.high_reserve_price,
            self.network_utilization,
            self.violation_mw,
        )
        if not all(math.isfinite(value) for value in values):
            raise AtlasError("atlas thresholds must be finite")
        if self.high_energy_price <= self.negative_energy_price:
            raise AtlasError("high energy threshold must exceed negative threshold")
        if self.high_reserve_price < 0.0:
            raise AtlasError("high reserve threshold must be nonnegative")
        if not 0.0 < self.network_utilization <= 1.0:
            raise AtlasError("network utilization threshold must lie in (0, 1]")
        if self.violation_mw < 0.0:
            raise AtlasError("violation threshold must be nonnegative")


@dataclass(frozen=True, slots=True)
class HistoricalDaySource:
    date: str
    input_schema: str
    input_path: Path
    input_sha256: str
    result_directory: Path
    result_tree_sha256: str
    source_profile: str
    selection_reason: str
    expected_period_count: int | None = None
    expected_summary_case_count: int | None = None
    declared_categories: tuple[StressCategory, ...] = ()
    input_reference: str = ""

    def __post_init__(self) -> None:
        if not self.date or not self.input_schema or not self.source_profile:
            raise AtlasError("date, schema, and source profile must not be empty")
        for label, value in (
            ("input", self.input_sha256),
            ("result tree", self.result_tree_sha256),
        ):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise AtlasError(f"{label} SHA-256 must be lowercase hexadecimal")
        if self.expected_period_count is not None and self.expected_period_count <= 0:
            raise AtlasError("expected period count must be positive")
        if (
            self.expected_summary_case_count is not None
            and self.expected_summary_case_count <= 0
        ):
            raise AtlasError("expected summary case count must be positive")
        object.__setattr__(
            self,
            "declared_categories",
            tuple(sorted(set(self.declared_categories), key=str)),
        )


@dataclass(frozen=True, slots=True)
class DayStressMetrics:
    period_count: int
    summary_case_count: int
    all_solves_successful: bool
    total_system_cost: float
    total_violation_cost: float
    maximum_violation_mw: float
    minimum_energy_price: float | None
    maximum_energy_price: float | None
    maximum_reserve_price: float | None
    maximum_branch_utilization: float | None


@dataclass(frozen=True, slots=True)
class StressEvent:
    date: str
    input_schema: str
    source_profile: str
    input_path: str
    input_sha256: str
    result_tree_sha256: str
    selection_reason: str
    categories: tuple[StressCategory, ...]
    metrics: DayStressMetrics


@dataclass(frozen=True, slots=True)
class StressEventAtlas:
    schema_version: int
    thresholds: AtlasThresholds
    events: tuple[StressEvent, ...]
    source_tree_sha256: str
    preregistration_sha256: str = ""
    logical_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.preregistration_sha256 and (
            len(self.preregistration_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.preregistration_sha256
            )
        ):
            raise AtlasError("preregistration SHA-256 must be lowercase hexadecimal")
        payload = self.to_dict(include_logical_sha256=False)
        object.__setattr__(self, "logical_sha256", _json_sha256(payload))

    def to_dict(self, *, include_logical_sha256: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "thresholds": asdict(self.thresholds),
            "source_tree_sha256": self.source_tree_sha256,
            "preregistration_sha256": self.preregistration_sha256,
            "events": [
                {
                    "date": event.date,
                    "input_schema": event.input_schema,
                    "source_profile": event.source_profile,
                    "input_path": event.input_path,
                    "input_sha256": event.input_sha256,
                    "result_tree_sha256": event.result_tree_sha256,
                    "selection_reason": event.selection_reason,
                    "categories": [str(category) for category in event.categories],
                    "metrics": asdict(event.metrics),
                }
                for event in self.events
            ],
        }
        if include_logical_sha256:
            payload["logical_sha256"] = self.logical_sha256
        return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def result_tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.iterdir(), key=lambda item: item.name.encode()):
        if not child.is_file():
            raise AtlasError(f"result tree contains a non-file entry: {child}")
        digest.update(child.name.encode())
        digest.update(b"\0")
        digest.update(file_sha256(child).encode())
        digest.update(b"\n")
    return digest.hexdigest()


class AtlasCorpusLoader:
    """Resolve heterogeneous retained-corpus manifests into canonical days."""

    def load(self, manifests: Sequence[Path]) -> tuple[HistoricalDaySource, ...]:
        by_date: dict[str, HistoricalDaySource] = {}
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            profile = str(manifest.get("profile", "")).strip()
            if not profile:
                raise AtlasError(f"manifest has no profile: {manifest_path}")
            root = manifest_path.parent
            for raw_day in manifest.get("days", ()):
                if not raw_day.get("result_tree_sha256"):
                    continue
                input_path = root / str(raw_day["input"])
                result_directory = input_path.parent.parent / "results"
                reason = str(
                    raw_day.get(
                        "selection_reason",
                        f"retained by the {profile} selection rule",
                    )
                )
                declared = self._declared_categories(reason)
                expected_period_count = None
                if StressCategory.DST_SHORT_DAY in declared:
                    expected_period_count = 46
                elif StressCategory.DST_LONG_DAY in declared:
                    expected_period_count = 50
                source = HistoricalDaySource(
                    date=str(raw_day["date"]),
                    input_schema=str(
                        raw_day.get("input_schema")
                        or (
                            "vspd-v3-final-pricing"
                            if input_path.name.startswith("FP_")
                            else "vspd-v5.0.6"
                        )
                    ),
                    input_path=input_path,
                    input_sha256=str(raw_day["input_sha256"]),
                    result_directory=result_directory,
                    result_tree_sha256=str(raw_day["result_tree_sha256"]),
                    source_profile=profile,
                    selection_reason=reason,
                    expected_period_count=expected_period_count,
                    expected_summary_case_count=(
                        int(raw_day["summary_rows"])
                        if raw_day.get("summary_rows") is not None
                        else None
                    ),
                    declared_categories=declared,
                    input_reference=f"{profile}:{raw_day['input']}",
                )
                previous = by_date.get(source.date)
                if previous is not None and previous != source:
                    raise AtlasError(f"conflicting duplicate date: {source.date}")
                by_date[source.date] = source
        if not by_date:
            raise AtlasError("no result-backed historical days were found")
        return tuple(by_date[date] for date in sorted(by_date))

    @staticmethod
    def _declared_categories(reason: str) -> tuple[StressCategory, ...]:
        lowered = reason.lower()
        categories: set[StressCategory] = set()
        if "46 trading" in lowered or "spring-forward" in lowered:
            categories.add(StressCategory.DST_SHORT_DAY)
        if "50 trading" in lowered or "fall-back" in lowered:
            categories.add(StressCategory.DST_LONG_DAY)
        return tuple(sorted(categories, key=str))


class StressEventAtlasBuilder:
    """Extract comparable metrics and classify a predeclared source population."""

    def __init__(self, thresholds: AtlasThresholds | None = None) -> None:
        self.thresholds = thresholds or AtlasThresholds()

    def build(
        self,
        sources: Iterable[HistoricalDaySource],
        *,
        verify_hashes: bool = True,
        preregistration_sha256: str = "",
    ) -> StressEventAtlas:
        ordered = tuple(sorted(sources, key=lambda source: source.date))
        if not ordered:
            raise AtlasError("an atlas requires at least one source day")
        if len({source.date for source in ordered}) != len(ordered):
            raise AtlasError("atlas source dates must be unique")
        events = tuple(
            self._build_event(source, verify_hashes=verify_hashes) for source in ordered
        )
        source_payload = [
            {
                "date": source.date,
                "input_sha256": source.input_sha256,
                "result_tree_sha256": source.result_tree_sha256,
            }
            for source in ordered
        ]
        return StressEventAtlas(
            schema_version=1,
            thresholds=self.thresholds,
            events=events,
            source_tree_sha256=_json_sha256(source_payload),
            preregistration_sha256=preregistration_sha256,
        )

    def _build_event(
        self, source: HistoricalDaySource, *, verify_hashes: bool
    ) -> StressEvent:
        if not source.input_path.is_file():
            raise AtlasError(f"missing input: {source.input_path}")
        if not source.result_directory.is_dir():
            raise AtlasError(f"missing result directory: {source.result_directory}")
        if verify_hashes and file_sha256(source.input_path) != source.input_sha256:
            raise AtlasError(f"input SHA-256 mismatch for {source.date}")
        if (
            verify_hashes
            and result_tree_sha256(source.result_directory) != source.result_tree_sha256
        ):
            raise AtlasError(f"result tree SHA-256 mismatch for {source.date}")

        summary = self._one(source.result_directory, "*SummaryResults_TP.csv")
        node = self._one(source.result_directory, "*node_results.csv")
        reserve = self._one(source.result_directory, "*reserve_results.csv")
        branch = self._one(source.result_directory, "*BranchResults_TP.csv")
        summary_rows = self._rows(summary)
        node_rows = self._rows(node)
        reserve_rows = self._rows(reserve)
        branch_rows = self._rows(branch)

        period_labels = {
            str(row.get("Period") or row.get("TP") or row.get("DateTime"))
            for row in summary_rows
        }
        period_count = len(period_labels)
        if (
            source.expected_period_count is not None
            and period_count != source.expected_period_count
        ):
            raise AtlasError(
                f"period count for {source.date} is {period_count}; "
                f"expected {source.expected_period_count}"
            )
        if (
            source.expected_summary_case_count is not None
            and len(summary_rows) != source.expected_summary_case_count
        ):
            raise AtlasError(
                f"summary case count for {source.date} is {len(summary_rows)}; "
                f"expected {source.expected_summary_case_count}"
            )

        violation_columns = tuple(
            name for name in summary_rows[0] if "Viol" in name and "(MW)" in name
        )
        violations = [
            abs(_float(row.get(column)))
            for row in summary_rows
            for column in violation_columns
        ]
        energy_prices = [_float(row.get("Price ($/MWh)")) for row in node_rows]
        reserve_prices = [
            _float(value)
            for row in reserve_rows
            for name, value in row.items()
            if "Price ($/MW)" in name
        ]
        utilizations = [
            abs(_float(row.get("Flow (MW) (From->To)")))
            / abs(_float(row.get("Capacity (MW)")))
            for row in branch_rows
            if abs(_float(row.get("Capacity (MW)"))) > 0.0
        ]
        metrics = DayStressMetrics(
            period_count=period_count,
            summary_case_count=len(summary_rows),
            all_solves_successful=all(
                _float(row.get("SolveStatus (1=OK)")) == 1.0 for row in summary_rows
            ),
            total_system_cost=sum(
                _float(row.get("SystemCost")) for row in summary_rows
            ),
            total_violation_cost=sum(
                _float(row.get("ViolationCost")) for row in summary_rows
            ),
            maximum_violation_mw=max(violations, default=0.0),
            minimum_energy_price=min(energy_prices, default=None),
            maximum_energy_price=max(energy_prices, default=None),
            maximum_reserve_price=max(reserve_prices, default=None),
            maximum_branch_utilization=max(utilizations, default=None),
        )
        categories = set(source.declared_categories)
        if period_count == 46:
            categories.add(StressCategory.DST_SHORT_DAY)
        if period_count == 50:
            categories.add(StressCategory.DST_LONG_DAY)
        if not metrics.all_solves_successful:
            categories.add(StressCategory.SOLVE_FAILURE)
        if (
            metrics.maximum_energy_price is not None
            and metrics.maximum_energy_price >= self.thresholds.high_energy_price
        ):
            categories.add(StressCategory.HIGH_ENERGY_PRICE)
        if (
            metrics.minimum_energy_price is not None
            and metrics.minimum_energy_price < self.thresholds.negative_energy_price
        ):
            categories.add(StressCategory.NEGATIVE_ENERGY_PRICE)
        if (
            metrics.maximum_reserve_price is not None
            and metrics.maximum_reserve_price >= self.thresholds.high_reserve_price
        ):
            categories.add(StressCategory.HIGH_RESERVE_PRICE)
        if (
            metrics.maximum_branch_utilization is not None
            and metrics.maximum_branch_utilization
            >= self.thresholds.network_utilization
        ):
            categories.add(StressCategory.NETWORK_STRESS)
        if (
            metrics.maximum_violation_mw > self.thresholds.violation_mw
            or metrics.total_violation_cost > 0.0
        ):
            categories.add(StressCategory.VIOLATION)
        return StressEvent(
            date=source.date,
            input_schema=source.input_schema,
            source_profile=source.source_profile,
            input_path=source.input_reference or source.input_path.name,
            input_sha256=source.input_sha256,
            result_tree_sha256=source.result_tree_sha256,
            selection_reason=source.selection_reason,
            categories=tuple(sorted(categories, key=str)),
            metrics=metrics,
        )

    @staticmethod
    def _one(directory: Path, pattern: str) -> Path:
        matches = tuple(directory.glob(pattern))
        if len(matches) != 1:
            raise AtlasError(
                f"expected one {pattern!r} in {directory}, found {len(matches)}"
            )
        return matches[0]

    @staticmethod
    def _rows(path: Path) -> tuple[dict[str, str], ...]:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = tuple(dict(row) for row in csv.DictReader(handle))
        if not rows:
            raise AtlasError(f"result table is empty: {path}")
        return rows


class StressEventAtlasWriter:
    """Write deterministic machine-readable and human-readable atlas views."""

    def write(
        self, atlas: StressEventAtlas, output_directory: Path
    ) -> tuple[Path, ...]:
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "atlas.json"
        csv_path = output_directory / "events.csv"
        markdown_path = output_directory / "README.md"
        json_path.write_text(
            json.dumps(atlas.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(
                (
                    "date",
                    "input_schema",
                    "categories",
                    "period_count",
                    "summary_case_count",
                    "total_system_cost",
                    "total_violation_cost",
                    "maximum_violation_mw",
                    "minimum_energy_price",
                    "maximum_energy_price",
                    "maximum_reserve_price",
                    "maximum_branch_utilization",
                    "input_sha256",
                    "result_tree_sha256",
                )
            )
            for event in atlas.events:
                metrics = event.metrics
                writer.writerow(
                    (
                        event.date,
                        event.input_schema,
                        ";".join(map(str, event.categories)),
                        metrics.period_count,
                        metrics.summary_case_count,
                        _number(metrics.total_system_cost),
                        _number(metrics.total_violation_cost),
                        _number(metrics.maximum_violation_mw),
                        _number(metrics.minimum_energy_price),
                        _number(metrics.maximum_energy_price),
                        _number(metrics.maximum_reserve_price),
                        _number(metrics.maximum_branch_utilization),
                        event.input_sha256,
                        event.result_tree_sha256,
                    )
                )
        markdown_path.write_text(self._markdown(atlas), encoding="utf-8")
        return (json_path, csv_path, markdown_path)

    @staticmethod
    def _markdown(atlas: StressEventAtlas) -> str:
        lines = [
            "# Historical stress-event atlas",
            "",
            f"Atlas SHA-256: `{atlas.logical_sha256}`",
            "",
            "| Date | Categories | Periods | Maximum energy price | Violation cost |",
            "|---|---|---:|---:|---:|",
        ]
        for event in atlas.events:
            metrics = event.metrics
            lines.append(
                "| "
                + " | ".join(
                    (
                        event.date,
                        ", ".join(map(str, event.categories)) or "control",
                        str(metrics.period_count),
                        _number(metrics.maximum_energy_price),
                        _number(metrics.total_violation_cost),
                    )
                )
                + " |"
            )
        lines.extend(
            (
                "",
                "Categories are threshold-based screening signals. They do not, by",
                "themselves, establish the cause of an observed market outcome.",
                "",
            )
        )
        return "\n".join(lines)


def _float(value: object) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        result = float(str(value))
    except ValueError as error:
        raise AtlasError(f"non-numeric result value: {value!r}") from error
    if not math.isfinite(result):
        raise AtlasError(f"non-finite result value: {value!r}")
    return result


def _number(value: float | None) -> str:
    return "" if value is None else format(value, ".12g")


def _json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
