"""Daily GDX case selection and solver-ready Gate 8 preparation."""

from __future__ import annotations

from datetime import UTC, datetime

from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data.raw import RawSymbol, RawSymbols
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.preprocess.input import CaseInput, nonzero
from pyspd.reserve import ReserveCase
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from pyspd.v16.compatibility import SPD16_FORMULATION_ID
from pyspd.v16.data import Spd16Case
from pyspd.v16.preprocess import SPD16_SOURCE_PROFILE_ID, Spd16SourcePreprocessor

from .overrides import OverrideAudit
from .types import DailyCase, OrchestrationError, PreparedCase, ScheduleType

_BASE_FORMULATION = "vspd-v5.0.6"
_STUDY_MODES = {
    101: ScheduleType.RTD,
    201: ScheduleType.RTD,
    130: ScheduleType.PRSS,
    131: ScheduleType.PRSS,
    111: ScheduleType.SPD,
}


class DailyCaseSelector:
    """Select vSPD cases in source datetime/record order."""

    def select(
        self,
        symbols: RawSymbols,
        *,
        case_ids: tuple[str, ...] = (),
        trading_periods: tuple[str, ...] = (),
        schedule_types: tuple[ScheduleType, ...] = (),
        publication_only: bool = False,
    ) -> tuple[DailyCase, ...]:
        run_mode = _numeric(symbols["i_runMode"])
        period_map = symbols["i_dateTimeTradePeriodMap"].records
        seconds = _numeric(symbols["i_priceCaseFilesPublishedSecs"])
        selected_ids = frozenset(case_ids)
        selected_periods = frozenset(trading_periods)
        selected_types = frozenset(schedule_types)
        discovered: list[DailyCase] = []
        for source_ordinal, record in enumerate(period_map):
            case_id, date_time, trading_period = record.keys
            mode = int(run_mode.get((case_id, "studyMode"), 0.0))
            schedule = _STUDY_MODES.get(mode)
            if schedule is None:
                continue
            published = seconds.get((case_id, trading_period), 0.0)
            if selected_ids and case_id not in selected_ids:
                continue
            if selected_periods and trading_period not in selected_periods:
                continue
            if selected_types and schedule not in selected_types:
                continue
            if publication_only and published <= 0.0:
                continue
            discovered.append(
                DailyCase(
                    case_id=case_id,
                    date_time=date_time,
                    trading_period=trading_period,
                    study_mode=mode,
                    schedule_type=schedule,
                    interval_minutes=run_mode.get((case_id, "intervalLength"), 0.0),
                    publication_seconds=published,
                    ordinal=source_ordinal,
                    source_sha256=symbols.source_sha256,
                )
            )
        discovered.sort(
            key=lambda item: (_date_time_or_max(item.date_time), item.ordinal)
        )
        discovered_ids = {item.case_id for item in discovered}
        missing_ids = selected_ids - discovered_ids
        if missing_ids:
            raise OrchestrationError(
                "requested case IDs are absent from the selected source surface: "
                + ", ".join(sorted(missing_ids))
            )
        return tuple(
            DailyCase(
                case_id=item.case_id,
                date_time=item.date_time,
                trading_period=item.trading_period,
                study_mode=item.study_mode,
                schedule_type=item.schedule_type,
                interval_minutes=item.interval_minutes,
                publication_seconds=item.publication_seconds,
                ordinal=ordinal,
                source_sha256=item.source_sha256,
            )
            for ordinal, item in enumerate(discovered)
        )

    def case_data(
        self,
        symbols: RawSymbols,
        selected: DailyCase,
        *,
        formulation_id: str = _BASE_FORMULATION,
    ) -> CaseData:
        if selected.source_sha256 != symbols.source_sha256:
            raise OrchestrationError("selected case belongs to a different source")
        case_symbols: list[RawSymbol] = []
        for symbol in symbols.symbols:
            records = symbol.records
            if symbol.domains and symbol.domains[0] in {"ca", "caseID"}:
                records = tuple(
                    record for record in records if record.keys[0] == selected.case_id
                )
            case_symbols.append(
                RawSymbol(
                    symbol.name,
                    symbol.symbol_type,
                    symbol.dimension,
                    symbol.domains,
                    symbol.description,
                    symbol.uel_orders,
                    records,
                )
            )
        return CaseData(
            formulation_id,
            CaseIdentifier(
                selected.case_id, selected.date_time, selected.trading_period
            ),
            RawSymbols(symbols.source_name, symbols.source_sha256, tuple(case_symbols)),
        )


class DailyCasePreparer:
    """Project one selected raw case into immutable full-formulation state."""

    def prepare(
        self,
        case_data: CaseData,
        selected: DailyCase,
        *,
        daily_mode: bool,
        override_audit: OverrideAudit | None = None,
        formulation_id: str = RESERVE_FORMULATION_ID,
    ) -> PreparedCase:
        if case_data.identifier.case_id != selected.case_id:
            raise OrchestrationError("case data does not match selected case")
        settings = PreprocessingSettings(
            daily_mode=daily_mode,
            # vSPDsolve.gms performs the RTD required-load calculation only
            # when dailymode = 0.  Daily replay must retain source demand.
            apply_rtd_load_reconstruction=not daily_mode,
        )
        if formulation_id == RESERVE_FORMULATION_ID:
            if case_data.formulation_id != _BASE_FORMULATION:
                raise OrchestrationError("v5 model requires the v5 source profile")
            preprocessing = Vspd506Preprocessor(settings).transform(case_data)
            reserve_case: ReserveCase = ReserveCase.from_sources(
                preprocessing, case_data
            )
        elif formulation_id == SPD16_FORMULATION_ID:
            if case_data.formulation_id != SPD16_SOURCE_PROFILE_ID:
                raise OrchestrationError("v16 model requires the v16 source profile")
            preprocessing = Spd16SourcePreprocessor(settings).transform(case_data)
            reserve_case = Spd16Case.from_sources(preprocessing, case_data)
        else:
            raise OrchestrationError(f"unknown formulation: {formulation_id}")
        assert reserve_case.network is not None
        source = CaseInput(case_data)
        dt_parameter = source.numeric("i_dateTimeParameter")
        node_parameter = source.numeric("i_dateTimeNodeParameter")
        period = (selected.case_id, selected.date_time)
        maximum = int(dt_parameter.get((*period, "maxSolveLoop"), 0.0))
        if maximum == 0:
            maximum = 5
        nodes = reserve_case.nodes
        transfer_map = tuple(
            (key[:3], key[:2] + (key[3],))
            for key in source.members("i_dateTimeNodetoNode")
        )
        active_branches = reserve_case.network.branches
        outage = source.optional_members("i_dateTimeNodeOutageBranch")
        inconsistent = frozenset(
            node
            for node in nodes
            if any(key[:3] == node for key in outage)
            and any(
                key[:3] == node and key[:2] + (key[3],) not in active_branches
                for key in outage
            )
        )
        node_island = {
            key[:3]: float(_island_number(key[3]))
            for key in preprocessing.set("node_island").members
        }
        # Preserve electrical-island 0 from the bus inputs for dead-node rules.
        for node in nodes:
            buses = [key[3] for key in reserve_case.network.node_bus if key[:3] == node]
            values = [
                reserve_case.network.bus_electrical_island.get((*node[:2], bus), 0.0)
                for bus in buses
            ]
            if values:
                node_island[node] = min(values)
        return PreparedCase(
            specification=selected,
            payload=reserve_case,
            required_load=reserve_case.network.node_load,
            generation_start={
                key[2]: value for key, value in reserve_case.generation_start.items()
            },
            load_override_nodes=_flagged(nodes, node_parameter, "loadIsOverride"),
            load_bad_nodes=_flagged(nodes, node_parameter, "loadIsBad"),
            instructed_shed_nodes=_flagged(
                nodes, node_parameter, "instructedShedActive"
            ),
            potential_inconsistency_nodes=inconsistent,
            node_transfer=transfer_map,
            use_actual_load=nonzero(dt_parameter.get((*period, "useActualLoad"), 0.0)),
            rtd_load_reconstruction_enabled=not daily_mode,
            # vSPDsolve.gms suppresses shortfall transfer for RTD/PRSS cases in
            # daily mode, even when the source flag is enabled. Non-daily runs
            # and other study modes retain the source-controlled path.
            transfer_enabled=(
                nonzero(
                    dt_parameter.get((*period, "enrgShortfallTransfer"), 0.0)
                )
                and (not daily_mode or selected.study_mode not in {101, 201})
            ),
            price_transfer_enabled=nonzero(
                dt_parameter.get((*period, "priceTransfer"), 0.0)
            ),
            shortfall_removal_margin=dt_parameter.get(
                (*period, "shortfallRemovalMargin"), 0.0
            ),
            maximum_solve_loops=maximum,
            override_entry_count=(
                len(override_audit.entries) if override_audit is not None else 0
            ),
            override_input_sha256=(
                override_audit.input_logical_sha256
                if override_audit is not None
                else case_data.symbols.logical_sha256
            ),
            override_output_sha256=(
                override_audit.output_logical_sha256
                if override_audit is not None
                else case_data.symbols.logical_sha256
            ),
        )


def _numeric(symbol: RawSymbol) -> dict[tuple[str, ...], float]:
    output: dict[tuple[str, ...], float] = {}
    for record in symbol.records:
        value = record.values.get("value")
        if value is not None and value.number is not None:
            output[record.keys] = float(value.number)
    return output


def _flagged(
    nodes: frozenset[tuple[str, ...]],
    values: dict[tuple[str, ...], float],
    component: str,
) -> frozenset[tuple[str, ...]]:
    return frozenset(
        node for node in nodes if nonzero(values.get((*node, component), 0.0))
    )


def _date_time_or_max(value: str) -> datetime:
    try:
        return datetime.strptime(value.title(), "%d-%b-%Y %H:%M").replace(tzinfo=UTC)
    except ValueError:
        # Canonical test fixtures and future schemas may use opaque datetime
        # labels.  Their authoritative GDX record order remains deterministic.
        return datetime.max.replace(tzinfo=UTC)


def _island_number(value: str) -> int:
    # NI/SI are market islands rather than electrical-island identifiers.  The
    # fallback is only used when a bus-level electrical island is absent.
    return {"NI": 1, "SI": 2}.get(value.upper(), 0)
