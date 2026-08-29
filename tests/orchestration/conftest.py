from __future__ import annotations

from collections.abc import Iterable

from pyspd.orchestration import DailyCase, PreparedCase, ScheduleType, SolveObservation


def make_daily_case(
    case_id: str = "C1",
    date_time: str = "01-JAN-2024 00:00",
    trading_period: str = "TP1",
    *,
    ordinal: int = 0,
    seconds: float = 300.0,
    schedule_type: ScheduleType = ScheduleType.RTD,
) -> DailyCase:
    return DailyCase(
        case_id,
        date_time,
        trading_period,
        101 if schedule_type is ScheduleType.RTD else 130,
        schedule_type,
        5.0 if schedule_type is ScheduleType.RTD else 30.0,
        seconds,
        ordinal,
        "0" * 64,
    )


def make_prepared(case: DailyCase | None = None) -> PreparedCase:
    selected = case or make_daily_case()
    ca, dt = selected.case_id, selected.date_time
    n1, n2 = (ca, dt, "N1"), (ca, dt, "N2")
    return PreparedCase(
        selected,
        object(),
        {n1: 10.0, n2: 20.0},
        {"G1": 0.0},
        load_bad_nodes=frozenset({n1}),
        potential_inconsistency_nodes=frozenset({n1}),
        node_transfer=((n1, n2),),
        use_actual_load=True,
        shortfall_removal_margin=0.2,
        maximum_solve_loops=3,
    )


def make_observation(
    case: DailyCase | None = None,
    *,
    shortfall: float = 0.0,
    generation: float = 30.0,
    raw_prices: tuple[float, float] = (50.0, 60.0),
    sos: bool = False,
    degraded: Iterable[str] = (),
) -> SolveObservation:
    selected = case or make_daily_case()
    ca, dt = selected.case_id, selected.date_time
    n1, n2 = (ca, dt, "N1"), (ca, dt, "N2")
    b1, b2 = (ca, dt, "B1"), (ca, dt, "B2")
    return SolveObservation(
        generation={"G1": generation},
        energy_shortfall={n1: shortfall, n2: 0.0},
        bus_generation={b1: 10.0, b2: 20.0},
        bus_load={b1: 10.0, b2: 20.0},
        raw_bus_prices={b1: raw_prices[0], b2: raw_prices[1]},
        reserve_prices={(ca, dt, "NI", "FIR"): 5.0},
        node_bus_allocation={(*n1, "B1"): 1.0, (*n2, "B2"): 1.0},
        bus_electrical_island={b1: 1.0, b2: 1.0},
        node_electrical_island={n1: 1.0, n2: 1.0},
        node_market_island={n1: "NI", n2: "NI"},
        node_transfer=((n1, n2),),
        bus_adjacency=frozenset({(b1, b2)}),
        connected_bus_flow={b1: 0.0, b2: 1.0},
        cleared_offer_price={b1: 50.0, b2: 20.0},
        sos_price_repair_required=sos,
        objective=100.0,
        degraded_reasons=tuple(degraded),
    )


class SequenceExecutor:
    def __init__(self, observations: Iterable[SolveObservation]) -> None:
        self.observations = list(observations)
        self.calls: list[PreparedCase] = []

    def solve(self, prepared: PreparedCase) -> SolveObservation:
        self.calls.append(prepared)
        index = min(len(self.calls) - 1, len(self.observations) - 1)
        return self.observations[index]
