from __future__ import annotations

from dataclasses import replace

from pyspd.orchestration import (
    CaseRunResult,
    CaseRunStatus,
    IndependentPublicationValidator,
    MarketPricePostProcessor,
    PublishedPriceAccumulator,
    PublishedPriceAggregator,
)
from tests.orchestration.conftest import make_daily_case, make_observation


def test_allocation_weighted_node_prices_keep_raw_and_repaired_layers() -> None:
    observation = make_observation(raw_prices=(40.0, 60.0))
    trace = MarketPricePostProcessor().process(
        observation, price_transfer_enabled=False
    )
    assert trace.raw_bus != {}
    assert trace.raw_bus == trace.repaired_bus
    assert trace.node[("C1", "01-JAN-2024 00:00", "N1")] == 40.0


def test_analytic_bus_interval_is_allocated_to_node_without_endpoint_metadata() -> None:
    observation = make_observation(raw_prices=(40.0, 60.0))
    bus = ("C1", "01-JAN-2024 00:00", "B1")
    node = ("C1", "01-JAN-2024 00:00", "N1")
    observation = replace(
        observation,
        raw_bus_price_intervals={bus: (39.5, 40.5)},
    )

    trace = MarketPricePostProcessor().process(
        observation, price_transfer_enabled=False
    )

    assert trace.raw_bus_intervals == {bus: (39.5, 40.5)}
    assert trace.repaired_bus_intervals == {bus: (39.5, 40.5)}
    assert trace.node_intervals == {node: (39.5, 40.5)}


def test_sos_invalid_price_is_replaced_from_adjacent_valid_bus() -> None:
    observation = make_observation(raw_prices=(50.0, 60.0), sos=True)
    trace = MarketPricePostProcessor().process(
        observation, price_transfer_enabled=False
    )
    b1 = ("C1", "01-JAN-2024 00:00", "B1")
    assert trace.raw_bus[b1] == 50.0
    assert trace.repaired_bus[b1] == 60.0
    assert not trace.invalid_buses


def test_disconnected_bus_zero_and_dead_node_price_transfer() -> None:
    observation = make_observation()
    ca, dt = "C1", "01-JAN-2024 00:00"
    b1, b2 = (ca, dt, "B1"), (ca, dt, "B2")
    n1, n2 = (ca, dt, "N1"), (ca, dt, "N2")
    observation = replace(
        observation,
        bus_load={b1: 0.0, b2: 20.0},
        bus_electrical_island={b1: 0.0, b2: 1.0},
        node_electrical_island={n1: 0.0, n2: 1.0},
    )
    trace = MarketPricePostProcessor().process(observation, price_transfer_enabled=True)
    assert trace.repaired_bus[b1] == 0.0
    assert trace.node[n1] == trace.node[n2]
    assert trace.dead_node_price_source[n1] == n2


def test_persistent_pre_shortfall_disconnection_overrides_dead_bus_penalty() -> None:
    observation = make_observation()
    ca, dt = "C1", "01-JAN-2024 00:00"
    b1 = (ca, dt, "B1")
    n1 = (ca, dt, "N1")
    observation = replace(
        observation,
        bus_generation={b1: 0.0, (ca, dt, "B2"): 20.0},
        bus_load={b1: 0.3, (ca, dt, "B2"): 20.0},
        bus_electrical_island={b1: 0.0, (ca, dt, "B2"): 1.0},
        persistent_disconnected_buses=frozenset({b1}),
    )

    trace = MarketPricePostProcessor().process(
        observation, price_transfer_enabled=False
    )

    assert trace.raw_bus[b1] == 50.0
    assert trace.repaired_bus[b1] == 0.0
    assert trace.node[n1] == 0.0
    assert b1 in trace.disconnected_buses


def test_dead_price_transfer_uses_market_not_electrical_island_identity() -> None:
    observation = make_observation()
    ca, dt = "C1", "01-JAN-2024 00:00"
    b1, b2 = (ca, dt, "B1"), (ca, dt, "B2")
    n1, n2 = (ca, dt, "N1"), (ca, dt, "N2")
    observation = replace(
        observation,
        bus_load={b1: 0.0, b2: 20.0},
        bus_electrical_island={b1: 3.0, b2: 1.0},
        node_electrical_island={n1: 3.0, n2: 1.0},
        node_market_island={n1: "NI", n2: "NI"},
    )

    trace = MarketPricePostProcessor().process(observation, price_transfer_enabled=True)

    assert trace.node[n1] == trace.node[n2]
    assert trace.dead_node_price_source[n1] == n2


def test_publication_uses_seconds_skips_zero_and_rounds() -> None:
    first = make_daily_case(seconds=100.0)
    second = make_daily_case("C2", "01-JAN-2024 00:05", ordinal=1, seconds=200.0)
    zero = make_daily_case("C3", "01-JAN-2024 00:10", ordinal=2, seconds=0.0)
    processor = MarketPricePostProcessor()

    def result(case: object, price: float) -> CaseRunResult:
        selected = case
        observation = make_observation(selected, raw_prices=(price, price))  # type: ignore[arg-type]
        trace = processor.process(observation, price_transfer_enabled=False)
        return CaseRunResult(
            selected,  # type: ignore[arg-type]
            CaseRunStatus.COMPLETE,
            1,
            observation,
            trace,
            (),
            {},
            {},
            frozenset(),
        )

    published = PublishedPriceAggregator().aggregate(
        (result(first, 10.0), result(second, 20.0), result(zero, 999.0)),
        decimals=5,
    )
    assert published.energy[("TP1", "N1")] == 16.66667
    assert published.total_seconds["TP1"] == 300.0
    assert published.date_time["TP1"] == "01-JAN-2024 00:00"


def test_publication_weights_analytic_intervals_and_omits_scalar_only_nodes() -> None:
    first = make_daily_case(seconds=100.0)
    second = make_daily_case("C2", "01-JAN-2024 00:05", ordinal=1, seconds=200.0)
    processor = MarketPricePostProcessor()

    def result(case, prices, interval):
        observation = make_observation(case, raw_prices=prices)
        first_bus = min(observation.raw_bus_prices)
        observation = replace(
            observation,
            raw_bus_price_intervals={first_bus: interval} if interval else {},
        )
        return CaseRunResult(
            case,
            CaseRunStatus.COMPLETE,
            1,
            observation,
            processor.process(observation, price_transfer_enabled=False),
            (),
            {},
            {},
            frozenset(),
        )

    published = PublishedPriceAggregator().aggregate(
        (
            result(first, (10.0, 30.0), (9.0, 11.0)),
            result(second, (20.0, 30.0), None),
        ),
        decimals=5,
    )

    assert published.energy[("TP1", "N1")] == 16.66667
    assert published.energy_intervals[("TP1", "N1")] == (16.33333, 17.0)
    assert ("TP1", "N2") not in published.energy_intervals
    assert IndependentPublicationValidator().validate(
        (
            result(first, (10.0, 30.0), (9.0, 11.0)),
            result(second, (20.0, 30.0), None),
        ),
        published,
    ).passed
    wrong = replace(
        published,
        energy_intervals={("TP1", "N1"): (16.0, 18.0)},
    )
    assert not IndependentPublicationValidator().validate(
        (
            result(first, (10.0, 30.0), (9.0, 11.0)),
            result(second, (20.0, 30.0), None),
        ),
        wrong,
    ).passed


def test_publication_accumulator_resumes_without_retaining_case_results() -> None:
    first = make_daily_case(seconds=100.0)
    second = make_daily_case("C2", "01-JAN-2024 00:05", ordinal=1, seconds=200.0)
    processor = MarketPricePostProcessor()

    def result(case: object, price: float) -> CaseRunResult:
        selected = case
        observation = make_observation(selected, raw_prices=(price, price))  # type: ignore[arg-type]
        return CaseRunResult(
            selected,  # type: ignore[arg-type]
            CaseRunStatus.COMPLETE,
            1,
            observation,
            processor.process(observation, price_transfer_enabled=False),
            (),
            {},
            {},
            frozenset(),
        )

    accumulator = PublishedPriceAccumulator()
    accumulator.add(result(first, 10.0))
    resumed = PublishedPriceAccumulator(
        energy_numerator=accumulator.energy_numerator,
        energy_lower_numerator=accumulator.energy_lower_numerator,
        energy_upper_numerator=accumulator.energy_upper_numerator,
        energy_interval_keys=frozenset(accumulator.energy_interval_keys),
        reserve_numerator=accumulator.reserve_numerator,
        total_seconds=accumulator.total_seconds,
        date_time=accumulator.date_time,
    )
    resumed.add(result(second, 20.0))

    assert resumed.finish(decimals=5) == PublishedPriceAggregator().aggregate(
        (result(first, 10.0), result(second, 20.0)), decimals=5
    )
