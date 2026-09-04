"""Daily GDX case selection and solver-ready Gate 8 preparation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType

from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols
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

type _RecordRange = tuple[int, int]


class DailyCaseDataIndex:
    """Index case-scoped GDX records once for repeated period extraction.

    GDX symbols are ordered by their declared domains, but an input adapter is
    allowed to present the same case in more than one record run.  Retaining
    ranges rather than assuming one contiguous block preserves source order
    while avoiding a full-record scan for every trading period.
    """

    def __init__(
        self,
        symbols: RawSymbols,
        *,
        case_ids: tuple[str, ...] = (),
    ) -> None:
        self._symbols = symbols
        self._case_ids = frozenset(case_ids) if case_ids else None
        ranges_by_symbol: dict[
            str, MappingProxyType[str, tuple[_RecordRange, ...]]
        ] = {}
        for symbol in symbols.symbols:
            if not _is_case_scoped(symbol):
                continue
            ranges: dict[str, list[_RecordRange]] = {}
            active_case: str | None = None
            active_start = 0
            for position, record in enumerate(symbol.records):
                case_id = record.keys[0]
                if active_case is None:
                    active_case = case_id
                    active_start = position
                elif case_id != active_case:
                    self._retain_range(
                        ranges, active_case, active_start, position
                    )
                    active_case = case_id
                    active_start = position
            if active_case is not None:
                self._retain_range(
                    ranges, active_case, active_start, len(symbol.records)
                )
            ranges_by_symbol[symbol.name] = MappingProxyType(
                {case_id: tuple(items) for case_id, items in ranges.items()}
            )
        self._ranges_by_symbol = MappingProxyType(ranges_by_symbol)

    def case_data(
        self,
        selected: DailyCase,
        *,
        formulation_id: str = _BASE_FORMULATION,
    ) -> CaseData:
        """Return the exact isolated source view for one indexed case."""

        if selected.source_sha256 != self._symbols.source_sha256:
            raise OrchestrationError("selected case belongs to a different source")
        if self._case_ids is not None and selected.case_id not in self._case_ids:
            raise OrchestrationError(
                f"case {selected.case_id!r} is not present in case-data index"
            )
        case_symbols = tuple(
            RawSymbol(
                symbol.name,
                symbol.symbol_type,
                symbol.dimension,
                symbol.domains,
                symbol.description,
                symbol.uel_orders,
                self._case_records(symbol, selected.case_id),
            )
            for symbol in self._symbols.symbols
        )
        return CaseData(
            formulation_id,
            CaseIdentifier(
                selected.case_id, selected.date_time, selected.trading_period
            ),
            RawSymbols(
                self._symbols.source_name,
                self._symbols.source_sha256,
                case_symbols,
            ),
        )

    def _retain_range(
        self,
        ranges: dict[str, list[_RecordRange]],
        case_id: str,
        start: int,
        stop: int,
    ) -> None:
        if self._case_ids is None or case_id in self._case_ids:
            ranges.setdefault(case_id, []).append((start, stop))

    def _case_records(
        self, symbol: RawSymbol, case_id: str
    ) -> tuple[RawRecord, ...]:
        if not _is_case_scoped(symbol):
            return symbol.records
        ranges = self._ranges_by_symbol[symbol.name].get(case_id, ())
        if not ranges:
            return ()
        if len(ranges) == 1:
            start, stop = ranges[0]
            return symbol.records[start:stop]
        return tuple(
            symbol.records[position]
            for start, stop in ranges
            for position in range(start, stop)
        )


def _is_case_scoped(symbol: RawSymbol) -> bool:
    return bool(symbol.domains and symbol.domains[0] in {"ca", "caseID"})


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
        return DailyCaseDataIndex(
            symbols, case_ids=(selected.case_id,)
        ).case_data(selected, formulation_id=formulation_id)


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
