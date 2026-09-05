"""Validated Python application service for the supported PySPD profiles."""

from __future__ import annotations

import gc
import hashlib
import json
import platform
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields, replace
from functools import partial
from pathlib import Path
from typing import Any, cast

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
    CaseBoundary,
    CaseRunResult,
    CaseRunStatus,
    CaseShard,
    DailyCaseDataIndex,
    DailyCasePreparer,
    DailyCaseRunner,
    DailyCaseSelector,
    DailyRunConfiguration,
    DailyRunner,
    DailyRunResult,
    DailyRunState,
    DynamicCaseJobPlanner,
    GenerationStartBoundaryClassifier,
    OrchestrationError,
    OverrideApplier,
    PriceTrace,
    ProcessShardCoordinator,
    PublishedPriceAggregator,
    ReserveCaseExecutor,
    RunEvent,
    RunEventKind,
    SolveObservation,
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
    ReportTable,
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
    worker_count: int = 1

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
        if isinstance(self.worker_count, bool) or self.worker_count <= 0:
            raise ConfigurationError("worker_count must be a positive integer")

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
            "worker_count": self.worker_count,
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


@dataclass(frozen=True, slots=True)
class ParallelCaseResultPayload:
    """Pickle-safe solved-case state returned across a process boundary."""

    specification: object
    status: str
    solve_count: int
    accepted: Mapping[str, object] | None
    prices: Mapping[str, object] | None
    events: tuple[Mapping[str, object], ...]
    final_required_load: Mapping[tuple[str, ...], float]
    transfers: Mapping[tuple[tuple[str, ...], tuple[str, ...]], float]
    untransferred_nodes: frozenset[tuple[str, ...]]


class ParallelCaseResultCodec:
    """Remove live solver objects while preserving every public result surface."""

    def encode(self, result: CaseRunResult) -> ParallelCaseResultPayload:
        accepted = (
            None
            if result.accepted is None
            else self._dataclass_payload(result.accepted, strip_solve_payload=True)
        )
        prices = (
            None
            if result.prices is None
            else self._dataclass_payload(result.prices)
        )
        events = tuple(
            {
                "sequence": event.sequence,
                "kind": event.kind.value,
                "case_id": event.case_id,
                "solve_loop": event.solve_loop,
                "details": dict(event.details),
            }
            for event in result.events
        )
        return ParallelCaseResultPayload(
            specification=result.specification,
            status=result.status.value,
            solve_count=result.solve_count,
            accepted=accepted,
            prices=prices,
            events=events,
            final_required_load=dict(result.final_required_load),
            transfers=dict(result.transfers),
            untransferred_nodes=frozenset(result.untransferred_nodes),
        )

    def decode(self, payload: ParallelCaseResultPayload) -> CaseRunResult:
        accepted = (
            None
            if payload.accepted is None
            else SolveObservation(
                **cast(dict[str, Any], dict(payload.accepted))
            )
        )
        prices = (
            None
            if payload.prices is None
            else PriceTrace(**cast(dict[str, Any], dict(payload.prices)))
        )
        events = tuple(
            RunEvent(
                int(cast(int, event["sequence"])),
                RunEventKind(str(event["kind"])),
                None if event["case_id"] is None else str(event["case_id"]),
                (
                    None
                    if event["solve_loop"] is None
                    else int(cast(int, event["solve_loop"]))
                ),
                dict(
                    cast(Mapping[str, str | int | float | bool], event["details"])
                ),
            )
            for event in payload.events
        )
        return CaseRunResult(
            payload.specification,  # type: ignore[arg-type]
            CaseRunStatus(payload.status),
            payload.solve_count,
            accepted,
            prices,
            events,
            dict(payload.final_required_load),
            dict(payload.transfers),
            payload.untransferred_nodes,
        )

    @staticmethod
    def _dataclass_payload(
        value: SolveObservation | PriceTrace,
        *,
        strip_solve_payload: bool = False,
    ) -> dict[str, object]:
        payload: dict[str, object] = {}
        for field in fields(value):
            item = getattr(value, field.name)
            if strip_solve_payload and field.name == "solve_payload":
                item = None
            elif isinstance(item, Mapping):
                item = dict(item)
            payload[field.name] = item
        return payload


class ParallelDailyResultAssembler:
    """Rebuild one canonical daily result from ordered independent case payloads."""

    def __init__(self, *, codec: ParallelCaseResultCodec | None = None) -> None:
        self._codec = codec or ParallelCaseResultCodec()

    def assemble(
        self,
        configuration: DailyRunConfiguration,
        payloads: tuple[ParallelCaseResultPayload, ...],
    ) -> DailyRunResult:
        if not payloads:
            raise OrchestrationError("parallel daily run returned no cases")
        cases: list[CaseRunResult] = []
        events: list[RunEvent] = []
        identities: set[tuple[str, str, str]] = set()
        sequence = 0
        for ordinal, payload in enumerate(payloads):
            decoded = self._codec.decode(payload)
            specification = decoded.specification
            if specification.ordinal != ordinal:
                raise OrchestrationError(
                    "parallel daily result is not in canonical ordinal order"
                )
            identity = (
                specification.case_id,
                specification.date_time,
                specification.trading_period,
            )
            if identity in identities:
                raise OrchestrationError("parallel daily result contains duplicate case")
            if specification.source_sha256 != configuration.source_sha256:
                raise OrchestrationError("parallel case source does not match configuration")
            identities.add(identity)
            case_events = tuple(
                RunEvent(
                    sequence + index,
                    event.kind,
                    event.case_id,
                    event.solve_loop,
                    dict(event.details),
                )
                for index, event in enumerate(decoded.events)
            )
            sequence += len(case_events)
            events.extend(case_events)
            cases.append(replace(decoded, events=case_events))
        published = PublishedPriceAggregator().aggregate(
            tuple(cases), decimals=configuration.price_rounding_decimals
        )
        events.append(
            RunEvent(
                sequence,
                RunEventKind.PRICES_PUBLISHED,
                None,
                details={
                    "energy_count": len(published.energy),
                    "reserve_count": len(published.reserve),
                },
            )
        )
        state = (
            DailyRunState.FAILED
            if any(case.status is CaseRunStatus.FAILED for case in cases)
            else DailyRunState.COMPLETE
        )
        return DailyRunResult(
            state,
            configuration.logical_sha256,
            tuple(cases),
            published,
            tuple(events),
        )


@dataclass(frozen=True, slots=True)
class ParallelApplicationShardArtifact:
    """One ordered worker shard with portable results and complete report rows."""

    shard_index: int
    case_payloads: tuple[ParallelCaseResultPayload, ...]
    report_rows: Mapping[str, tuple[Mapping[str, str], ...]]


class ApplicationCaseSource:
    """Read, validate, index, and lazily prepare one immutable daily GDX source."""

    def __init__(self, configuration: ApplicationConfiguration) -> None:
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
        self.configuration = configuration
        self.symbols = symbols
        self.selected = DailyCaseSelector().select(
            symbols, case_ids=configuration.case_ids
        )
        self._case_data_index = DailyCaseDataIndex(
            symbols, case_ids=tuple(item.case_id for item in self.selected)
        )
        self._source_profile = (
            SPD16_SOURCE_PROFILE_ID
            if configuration.formulation_id == SPD16_FORMULATION_ID
            else "vspd-v5.0.6"
        )

    def boundaries(self) -> tuple[CaseBoundary, ...]:
        """Return exact independence evidence without full case preprocessing."""

        return GenerationStartBoundaryClassifier().classify(
            self.symbols, self.selected
        )

    def iter_prepared_cases(
        self,
        *,
        start_ordinal: int = 0,
        maximum_cases: int | None = None,
    ) -> Iterator[PreparedCase]:
        if isinstance(start_ordinal, bool) or start_ordinal < 0:
            raise ConfigurationError("start_ordinal must be a non-negative integer")
        if (
            maximum_cases is not None
            and (isinstance(maximum_cases, bool) or maximum_cases <= 0)
        ):
            raise ConfigurationError("maximum_cases must be a positive integer")
        if start_ordinal > len(self.selected):
            raise ConfigurationError("start_ordinal exceeds selected case count")
        stop_ordinal = (
            None if maximum_cases is None else start_ordinal + maximum_cases
        )
        for specification in self.selected[start_ordinal:stop_ordinal]:
            case_data = self._case_data_index.case_data(
                specification, formulation_id=self._source_profile
            )
            case_data, audit = OverrideApplier().apply(case_data, ())
            yield DailyCasePreparer().prepare(
                case_data,
                specification,
                daily_mode=True,
                override_audit=audit,
                formulation_id=self.configuration.formulation_id,
            )


_WORKER_CASE_SOURCES: dict[str, ApplicationCaseSource] = {}


def _application_worker_source(
    configuration: ApplicationConfiguration,
) -> ApplicationCaseSource:
    key = configuration.logical_sha256
    source = _WORKER_CASE_SOURCES.get(key)
    if source is None:
        _WORKER_CASE_SOURCES.clear()
        source = ApplicationCaseSource(configuration)
        _WORKER_CASE_SOURCES[key] = source
    return source


def _execute_application_shard(
    configuration: ApplicationConfiguration,
    shard: CaseShard,
) -> ParallelApplicationShardArtifact:
    """Solve and fully render a shard inside one isolated worker process."""

    application = PyspdApplication()
    source = _application_worker_source(configuration)
    daily_configuration = application.daily_configuration(configuration)
    runner = application.case_runner(configuration)
    previous_generation: dict[str, float] = {}
    event_sequence = 0
    payloads: list[ParallelCaseResultPayload] = []
    rows: dict[str, list[Mapping[str, str]]] = {}
    prepared_cases = tuple(
        source.iter_prepared_cases(
            start_ordinal=shard.start_ordinal,
            maximum_cases=shard.case_count,
        )
    )
    if tuple(case.specification.case_id for case in prepared_cases) != shard.case_ids:
        raise OrchestrationError("parallel worker source range does not match its shard")
    for prepared in prepared_cases:
        execution = runner.execute(
            daily_configuration,
            prepared,
            previous_generation=previous_generation,
            event_sequence=event_sequence,
        )
        result = execution.result
        one_case = DailyRunResult(
            DailyRunState.COMPLETE,
            daily_configuration.logical_sha256,
            (result,),
            None,
            result.events,
        )
        bundle = application.render_report_bundle(configuration, one_case)
        for name, table in bundle.tables.items():
            if name in {"audit", "published_price"}:
                continue
            rows.setdefault(name, []).extend(dict(row) for row in table.rows)
        payloads.append(ParallelCaseResultCodec().encode(result))
        previous_generation = execution.previous_generation
        event_sequence = execution.next_event_sequence
        del execution, result, one_case, bundle
        gc.collect()
    return ParallelApplicationShardArtifact(
        shard.index,
        tuple(payloads),
        {name: tuple(items) for name, items in rows.items()},
    )


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
        if configuration.worker_count > 1:
            return self._run_parallel(configuration)
        daily_configuration = self.daily_configuration(configuration)
        prepared = tuple(self.iter_prepared_cases(configuration))
        result = DailyRunner(
            self.case_executor(configuration),
            postprocessor=self.price_postprocessor(configuration),
        ).run(daily_configuration, prepared)
        bundle = self.render_report_bundle(configuration, result)
        manifest = bundle.write(configuration.output_directory)
        return ApplicationRun(result, manifest, configuration.output_directory)

    def _run_parallel(
        self, configuration: ApplicationConfiguration
    ) -> ApplicationRun:
        self.validate_formulation(configuration.formulation_id)
        source = ApplicationCaseSource(configuration)
        if not source.selected:
            daily_configuration = self.daily_configuration(configuration)
            result = DailyRunner(
                self.case_executor(configuration),
                postprocessor=self.price_postprocessor(configuration),
            ).run(daily_configuration, ())
            bundle = self.render_report_bundle(configuration, result)
            manifest = bundle.write(configuration.output_directory)
            return ApplicationRun(result, manifest, configuration.output_directory)
        plan = DynamicCaseJobPlanner().plan(
            source.boundaries(), workers=configuration.worker_count, cases_per_job=1
        )
        # The parent retains only the auditable boundary plan. Each spawned
        # process reads and caches its own immutable GDX view.
        del source
        artifacts = ProcessShardCoordinator().run(
            plan, partial(_execute_application_shard, configuration)
        )
        for shard, artifact in zip(plan.shards, artifacts, strict=True):
            if artifact.shard_index != shard.index:
                raise OrchestrationError(
                    "parallel worker artifacts are not in canonical shard order"
                )
            if len(artifact.case_payloads) != shard.case_count:
                raise OrchestrationError(
                    f"parallel shard {shard.index} returned an incomplete case range"
                )
        payloads = tuple(
            payload
            for artifact in artifacts
            for payload in artifact.case_payloads
        )
        daily_configuration = self.daily_configuration(configuration)
        result = ParallelDailyResultAssembler().assemble(
            daily_configuration, payloads
        )
        base_bundle = self.render_report_bundle(configuration, result)
        merged_tables: dict[str, ReportTable] = {}
        for name, base_table in base_bundle.tables.items():
            if name in {"audit", "published_price"}:
                merged_tables[name] = base_table
                continue
            merged_rows = tuple(
                row
                for artifact in artifacts
                for row in artifact.report_rows.get(name, ())
            )
            merged_tables[name] = ReportTable(base_table.definition, merged_rows)
        bundle = ReportBundle(base_bundle.provenance, merged_tables)
        manifest = bundle.write(configuration.output_directory)
        return ApplicationRun(result, manifest, configuration.output_directory)

    def iter_prepared_cases(
        self,
        configuration: ApplicationConfiguration,
        *,
        start_ordinal: int = 0,
        maximum_cases: int | None = None,
    ) -> Iterator[PreparedCase]:
        """Prepare selected cases lazily from a validated immutable GDX source."""

        self.validate_formulation(configuration.formulation_id)
        if isinstance(start_ordinal, bool) or start_ordinal < 0:
            raise ConfigurationError("start_ordinal must be a non-negative integer")
        if (
            maximum_cases is not None
            and (isinstance(maximum_cases, bool) or maximum_cases <= 0)
        ):
            raise ConfigurationError("maximum_cases must be a positive integer")
        yield from ApplicationCaseSource(configuration).iter_prepared_cases(
            start_ordinal=start_ordinal,
            maximum_cases=maximum_cases,
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
