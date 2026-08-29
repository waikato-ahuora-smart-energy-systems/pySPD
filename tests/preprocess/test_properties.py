from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from pyspd.contracts import CaseData
from pyspd.data import RawSymbols
from pyspd.preprocess import Vspd506Preprocessor
from pyspd.preprocess.losses import MAX_FLOW_SEGMENT, _loss_points


@given(
    capacity=st.floats(min_value=1.0, max_value=5000.0, allow_nan=False),
    resistance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_three_tranche_curve_is_ordered_and_finite(
    capacity: float, resistance: float
) -> None:
    points, factors = _loss_points(3, capacity, resistance)

    assert 0.0 < points[0] < points[1] < MAX_FLOW_SEGMENT
    assert points[2] == MAX_FLOW_SEGMENT
    assert all(value >= 0.0 for value in factors)


@given(scale=st.floats(min_value=0.1, max_value=10.0, allow_nan=False))
def test_zero_loss_curve_capacity_scales_metamorphically(scale: float) -> None:
    points, factors = _loss_points(0, 100.0 * scale, 0.5)

    assert points == [100.0 * scale]
    assert factors == [0.0]


def test_entity_relabeling_preserves_economic_values(
    representative_case: CaseData,
) -> None:
    renames = {
        "N1": "NODE-X",
        "B1": "BUS-X",
        "BR1": "BRANCH-X",
        "O1": "OFFER-X",
        "BD1": "BID-X",
    }
    symbols = tuple(
        replace(
            symbol,
            records=tuple(
                replace(
                    record,
                    keys=tuple(renames.get(key, key) for key in record.keys),
                )
                for record in symbol.records
            ),
            uel_orders=tuple(
                tuple(renames.get(uel, uel) for uel in order)
                for order in symbol.uel_orders
            ),
        )
        for symbol in representative_case.symbols.symbols
    )
    relabeled = replace(
        representative_case,
        symbols=RawSymbols(
            representative_case.symbols.source_name,
            representative_case.symbols.source_sha256,
            symbols,
        ),
    )

    original = Vspd506Preprocessor().transform(representative_case)
    changed = Vspd506Preprocessor().transform(relabeled)
    for name in (
        "energy_offer_mw",
        "energy_offer_price",
        "demand_bid_mw",
        "required_load",
        "branch_capacity",
        "loss_segment_factor",
    ):
        assert sorted(original.parameter(name).values.values()) == sorted(
            changed.parameter(name).values.values()
        )
    for name in ("node", "bus", "branch", "offer", "bid"):
        assert len(original.set(name).members) == len(changed.set(name).members)


def test_meaningful_block_order_changes_are_preserved(
    representative_case: CaseData,
) -> None:
    symbols = []
    for symbol in representative_case.symbols.symbols:
        if symbol.name != "i_dateTimeEnergyOffer":
            symbols.append(symbol)
            continue
        uel_orders = list(symbol.uel_orders)
        uel_orders[3] = ("t2", "t1")
        symbols.append(replace(symbol, uel_orders=tuple(uel_orders)))
    reordered = replace(
        representative_case,
        symbols=RawSymbols(
            representative_case.symbols.source_name,
            representative_case.symbols.source_sha256,
            tuple(symbols),
        ),
    )

    original = Vspd506Preprocessor().transform(representative_case)
    changed = Vspd506Preprocessor().transform(reordered)
    assert (
        original.parameter("energy_offer_block_order").get(("C1", "D1", "O1", "t1"))
        == 1.0
    )
    assert (
        changed.parameter("energy_offer_block_order").get(("C1", "D1", "O1", "t1"))
        == 2.0
    )
    assert (
        original.parameter("energy_offer_mw").values
        == changed.parameter("energy_offer_mw").values
    )
