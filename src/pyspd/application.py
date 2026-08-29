"""Validated Python application service for the supported PySPD profiles."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from pathlib import Path

from pyspd import __version__
from pyspd.data import SymbolCatalog
from pyspd.data.gdx import GdxAdapter
from pyspd.orchestration import (
    DailyCasePreparer,
    DailyCaseSelector,
    DailyRunConfiguration,
    DailyRunner,
    DailyRunResult,
    OverrideApplier,
    ReserveCaseExecutor,
    Spd16CaseExecutor,
)
from pyspd.orchestration.pricing import MarketPricePostProcessor
from pyspd.reporting import (
    ArtifactProvenance,
    DailyReportRegistry,
    ReportManifest,
    daily_report_registry,
)
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from pyspd.v16.compatibility import SPD16_FORMULATION_ID
from pyspd.v16.preprocess import SPD16_SOURCE_PROFILE_ID


class ConfigurationError(ValueError):
    """Public application configuration is invalid or ambiguous."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ApplicationConfiguration:
    formulation_id: str
    input_path: Path
    output_directory: Path
    source_sha256: str
    gams_system_directory: Path
    case_ids: tuple[str, ...] = ()
    maximum_solve_loops: int = 5
    price_rounding_decimals: int = 5

    def __post_init__(self) -> None:
        input_path = self.input_path.expanduser().resolve()
        output = self.output_directory.expanduser().resolve()
        system = self.gams_system_directory.expanduser().resolve()
        object.__setattr__(self, "input_path", input_path)
        object.__setattr__(self, "output_directory", output)
        object.__setattr__(self, "gams_system_directory", system)
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if not self.formulation_id.strip():
            raise ConfigurationError("formulation_id must be explicit")
        if not input_path.is_file():
            raise ConfigurationError(f"input file does not exist: {input_path}")
        if not system.is_dir():
            raise ConfigurationError(f"GAMS system directory does not exist: {system}")
        if len(set(self.case_ids)) != len(self.case_ids) or any(
            not case_id.strip() for case_id in self.case_ids
        ):
            raise ConfigurationError("case_ids must be unique and non-empty")
        if _file_sha256(input_path) != self.source_sha256:
            raise ConfigurationError("input source hash mismatch")
        if self.maximum_solve_loops <= 0:
            raise ConfigurationError("maximum_solve_loops must be positive")
        if not 0 <= self.price_rounding_decimals <= 12:
            raise ConfigurationError("price_rounding_decimals must lie in [0, 12]")

    @property
    def logical_sha256(self) -> str:
        payload = {
            "formulation_id": self.formulation_id,
            "input_name": self.input_path.name,
            "case_ids": list(self.case_ids),
            "maximum_solve_loops": self.maximum_solve_loops,
            "price_rounding_decimals": self.price_rounding_decimals,
            "source_sha256": self.source_sha256,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @classmethod
    def from_json(cls, path: Path) -> ApplicationConfiguration:
        payload = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field for field in cls.__dataclass_fields__}
        unknown = set(payload) - allowed
        if unknown:
            raise ConfigurationError(f"unknown configuration fields: {sorted(unknown)}")
        for field in ("input_path", "output_directory", "gams_system_directory"):
            payload[field] = Path(payload[field])
        if "case_ids" in payload:
            payload["case_ids"] = tuple(payload["case_ids"])
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class ApplicationRun:
    result: DailyRunResult
    report_manifest: ReportManifest
    output_directory: Path


class PyspdApplication:
    """Composition root with explicit formulation selection and no date switching."""

    def __init__(self) -> None:
        self._formulations = {
            RESERVE_FORMULATION_ID: RESERVE_FORMULATION_ID,
            SPD16_FORMULATION_ID: SPD16_FORMULATION_ID,
        }
        self._reports = daily_report_registry()

    @property
    def report_registry(self) -> DailyReportRegistry:
        return self._reports

    @property
    def formulation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._formulations))

    def validate_formulation(self, formulation_id: str) -> None:
        if formulation_id not in self._formulations:
            raise ConfigurationError(f"unknown formulation: {formulation_id}")

    def run(self, configuration: ApplicationConfiguration) -> ApplicationRun:
        self.validate_formulation(configuration.formulation_id)
        symbols = GdxAdapter.read(
            configuration.input_path,
            system_directory=configuration.gams_system_directory,
        )
        if symbols.source_sha256 != configuration.source_sha256:
            raise ConfigurationError("GDX adapter source hash mismatch")
        catalog = (
            SymbolCatalog.spd_v16()
            if configuration.formulation_id == SPD16_FORMULATION_ID
            else SymbolCatalog.vspd_v5()
        )
        catalog.validate(symbols)
        source_profile = (
            SPD16_SOURCE_PROFILE_ID
            if configuration.formulation_id == SPD16_FORMULATION_ID
            else "vspd-v5.0.6"
        )
        selector = DailyCaseSelector()
        selected = selector.select(symbols, case_ids=configuration.case_ids)
        prepared = []
        for specification in selected:
            case_data = selector.case_data(
                symbols, specification, formulation_id=source_profile
            )
            case_data, audit = OverrideApplier().apply(case_data, ())
            prepared.append(
                DailyCasePreparer().prepare(
                    case_data,
                    specification,
                    daily_mode=True,
                    override_audit=audit,
                    formulation_id=configuration.formulation_id,
                )
            )
        daily_configuration = DailyRunConfiguration(
            configuration.formulation_id,
            configuration.source_sha256,
            maximum_solve_loops=configuration.maximum_solve_loops,
            price_rounding_decimals=configuration.price_rounding_decimals,
            environment_fingerprint=(
                f"{platform.system()}-{platform.machine()}-gams-scip-highs"
            ),
        )
        executor = (
            Spd16CaseExecutor()
            if configuration.formulation_id == SPD16_FORMULATION_ID
            else ReserveCaseExecutor()
        )
        postprocessor = MarketPricePostProcessor(
            bad_price_factor=(
                3.0 if configuration.formulation_id == SPD16_FORMULATION_ID else 5.0
            )
        )
        result = DailyRunner(executor, postprocessor=postprocessor).run(
            daily_configuration, tuple(prepared)
        )
        lock_path = Path(__file__).resolve().parents[2] / "uv.lock"
        provenance = ArtifactProvenance(
            configuration.formulation_id,
            configuration.source_sha256,
            result.configuration_sha256,
            __version__,
            _file_sha256(lock_path),
            "scip-mip-fixed-highs-rmip",
            daily_configuration.environment_fingerprint,
        )
        profile = self._reports.resolve(configuration.formulation_id)
        bundle = profile.report_renderer().render(
            profile.result_schema().collect(result, provenance)
        )
        manifest = bundle.write(configuration.output_directory)
        return ApplicationRun(result, manifest, configuration.output_directory)
