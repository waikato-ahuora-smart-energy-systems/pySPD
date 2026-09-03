"""Validated Python application service for the supported PySPD profiles."""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pyspd import __version__
from pyspd.data import SymbolCatalog
from pyspd.data.gdx import GdxAdapter
from pyspd.data.legacy import (
    LEGACY_V3_INPUT_SCHEMA,
    SUPPORTED_INPUT_SCHEMAS,
    V5_INPUT_SCHEMA,
    LegacyV3InputAdapter,
)
from pyspd.orchestration import (
    DailyCasePreparer,
    DailyCaseRunner,
    DailyCaseSelector,
    DailyRunConfiguration,
    DailyRunner,
    DailyRunResult,
    OverrideApplier,
    ReserveCaseExecutor,
    Spd16CaseExecutor,
)
from pyspd.orchestration.pricing import MarketPricePostProcessor
from pyspd.orchestration.solver import CaseExecutor
from pyspd.orchestration.types import PreparedCase
from pyspd.reporting import (
    ArtifactProvenance,
    DailyReportRegistry,
    ReportBundle,
    ReportManifest,
    daily_report_registry,
)
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from pyspd.solver import CbcBackend, ClpBackend
from pyspd.v16.compatibility import SPD16_FORMULATION_ID
from pyspd.v16.preprocess import SPD16_SOURCE_PROFILE_ID

PORTABLE_SOLVER_PROFILE = "scip-mip-fixed-highs-rmip"
CLP_VALIDATION_SOLVER_PROFILE = "scip-mip-fixed-clp-rmip"
CBC_HIGHS_VALIDATION_SOLVER_PROFILE = "cbc-mip-fixed-highs-rmip"
CBC_CLP_VALIDATION_SOLVER_PROFILE = "cbc-mip-fixed-clp-rmip"
SUPPORTED_SOLVER_PROFILES = frozenset(
    {
        PORTABLE_SOLVER_PROFILE,
        CLP_VALIDATION_SOLVER_PROFILE,
        CBC_HIGHS_VALIDATION_SOLVER_PROFILE,
        CBC_CLP_VALIDATION_SOLVER_PROFILE,
    }
)


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
    solver_profile: str = PORTABLE_SOLVER_PROFILE
    input_schema: str = V5_INPUT_SCHEMA
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
        if self.solver_profile not in SUPPORTED_SOLVER_PROFILES:
            raise ConfigurationError(
                "solver_profile must explicitly select one of "
                + ", ".join(sorted(SUPPORTED_SOLVER_PROFILES))
            )
        if self.input_schema not in SUPPORTED_INPUT_SCHEMAS:
            raise ConfigurationError(
                "input_schema must explicitly select one of "
                + ", ".join(sorted(SUPPORTED_INPUT_SCHEMAS))
            )
        if (
            self.input_schema == LEGACY_V3_INPUT_SCHEMA
            and self.formulation_id == SPD16_FORMULATION_ID
        ):
            raise ConfigurationError(
                "legacy v3 input is not valid for the SPD v16 formulation"
            )
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
            "input_schema": self.input_schema,
            "case_ids": list(self.case_ids),
            "maximum_solve_loops": self.maximum_solve_loops,
            "price_rounding_decimals": self.price_rounding_decimals,
            "solver_profile": self.solver_profile,
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
        daily_configuration = self.daily_configuration(configuration)
        prepared = tuple(self.iter_prepared_cases(configuration))
        result = DailyRunner(
            self.case_executor(configuration),
            postprocessor=self.price_postprocessor(configuration),
        ).run(daily_configuration, prepared)
        bundle = self.render_report_bundle(configuration, result)
        manifest = bundle.write(configuration.output_directory)
        return ApplicationRun(result, manifest, configuration.output_directory)

    def iter_prepared_cases(
        self,
        configuration: ApplicationConfiguration,
        *,
        start_ordinal: int = 0,
    ) -> Iterator[PreparedCase]:
        """Prepare selected cases lazily from a validated immutable GDX source."""

        self.validate_formulation(configuration.formulation_id)
        if isinstance(start_ordinal, bool) or start_ordinal < 0:
            raise ConfigurationError("start_ordinal must be a non-negative integer")
        symbols = GdxAdapter.read(
            configuration.input_path,
            system_directory=configuration.gams_system_directory,
        )
        if symbols.source_sha256 != configuration.source_sha256:
            raise ConfigurationError("GDX adapter source hash mismatch")
        if configuration.input_schema == LEGACY_V3_INPUT_SCHEMA:
            symbols = LegacyV3InputAdapter().normalize(symbols)
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
        if start_ordinal > len(selected):
            raise ConfigurationError("start_ordinal exceeds selected case count")
        for specification in selected[start_ordinal:]:
            case_data = selector.case_data(
                symbols, specification, formulation_id=source_profile
            )
            case_data, audit = OverrideApplier().apply(case_data, ())
            yield DailyCasePreparer().prepare(
                case_data,
                specification,
                daily_mode=True,
                override_audit=audit,
                formulation_id=configuration.formulation_id,
            )

    def daily_configuration(
        self, configuration: ApplicationConfiguration
    ) -> DailyRunConfiguration:
        self.validate_formulation(configuration.formulation_id)
        return DailyRunConfiguration(
            configuration.formulation_id,
            configuration.source_sha256,
            maximum_solve_loops=configuration.maximum_solve_loops,
            price_rounding_decimals=configuration.price_rounding_decimals,
            environment_fingerprint=(
                f"{platform.system()}-{platform.machine()}-"
                + configuration.solver_profile.replace("scip-mip", "native-scip")
                .replace("cbc-mip", "cbc")
                .replace("-fixed-", "-")
                .replace("-rmip", "")
            ),
            application_configuration_sha256=configuration.logical_sha256,
        )

    def case_executor(self, configuration: ApplicationConfiguration) -> CaseExecutor:
        self.validate_formulation(configuration.formulation_id)
        pricing_backend = (
            ClpBackend()
            if configuration.solver_profile
            in {CLP_VALIDATION_SOLVER_PROFILE, CBC_CLP_VALIDATION_SOLVER_PROFILE}
            else None
        )
        primary_backend = (
            CbcBackend()
            if configuration.solver_profile
            in {
                CBC_HIGHS_VALIDATION_SOLVER_PROFILE,
                CBC_CLP_VALIDATION_SOLVER_PROFILE,
            }
            else None
        )
        return (
            Spd16CaseExecutor(
                primary_backend=primary_backend,
                pricing_backend=pricing_backend,
            )
            if configuration.formulation_id == SPD16_FORMULATION_ID
            else ReserveCaseExecutor(
                primary_backend=primary_backend,
                pricing_backend=pricing_backend,
            )
        )

    def case_runner(self, configuration: ApplicationConfiguration) -> DailyCaseRunner:
        return DailyCaseRunner(
            self.case_executor(configuration),
            postprocessor=self.price_postprocessor(configuration),
        )

    def price_postprocessor(
        self, configuration: ApplicationConfiguration
    ) -> MarketPricePostProcessor:
        self.validate_formulation(configuration.formulation_id)
        return MarketPricePostProcessor(
            bad_price_factor=(
                3.0 if configuration.formulation_id == SPD16_FORMULATION_ID else 5.0
            )
        )

    def render_report_bundle(
        self,
        configuration: ApplicationConfiguration,
        result: DailyRunResult,
    ) -> ReportBundle:
        """Render deterministic reports without requiring an eager application run."""

        daily_configuration = self.daily_configuration(configuration)
        if result.configuration_sha256 != daily_configuration.logical_sha256:
            raise ConfigurationError("result configuration hash mismatch")
        lock_path = Path(__file__).resolve().parents[2] / "uv.lock"
        provenance = ArtifactProvenance(
            configuration.formulation_id,
            configuration.source_sha256,
            result.configuration_sha256,
            __version__,
            _file_sha256(lock_path),
            configuration.solver_profile,
            daily_configuration.environment_fingerprint,
        )
        profile = self._reports.resolve(configuration.formulation_id)
        return profile.report_renderer().render(
            profile.result_schema().collect(result, provenance)
        )
