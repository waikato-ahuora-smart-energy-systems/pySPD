import pytest

from pyspd.preprocess import ShortfallTransferResolver, ShortfallTransferState


def test_shortfall_transfer_follows_ordered_mapped_node_chain() -> None:
    source = ("C", "D", "A")
    first = ("C", "D", "B")
    second = ("C", "D", "C")
    state = ShortfallTransferState(
        required_load={source: 20.0, first: 30.0, second: 40.0},
        adjustment_mw={source: 5.0},
        energy_shortfall_mw={first: 1.0},
        dead_nodes=frozenset(),
        load_override_nodes=frozenset(),
        instructed_shed_nodes=frozenset(),
        electrical_island={source: 1.0, first: 1.0, second: 1.0},
    )

    result = ShortfallTransferResolver().resolve(
        ((source, first), (first, second)), state
    )

    assert result.transfers == {(source, second): 5.0}
    assert result.required_load[source] == 15.0
    assert result.required_load[second] == 45.0
    assert result.did_transfer == {source, second}


@pytest.mark.parametrize("blocked_by", ["override", "shed", "island"])
def test_ineligible_mapped_candidate_does_not_receive_transfer(
    blocked_by: str,
) -> None:
    source = ("C", "D", "A")
    target = ("C", "D", "B")
    state = ShortfallTransferState(
        required_load={source: 3.0, target: 2.0},
        adjustment_mw={source: 5.0},
        energy_shortfall_mw={},
        dead_nodes=frozenset(),
        load_override_nodes=frozenset({target})
        if blocked_by == "override"
        else frozenset(),
        instructed_shed_nodes=frozenset({target})
        if blocked_by == "shed"
        else frozenset(),
        electrical_island={source: 1.0, target: 2.0 if blocked_by == "island" else 1.0},
    )

    result = ShortfallTransferResolver().resolve(((source, target),), state)

    assert result.required_load[source] == 0.0
    assert result.required_load[target] == 2.0
    assert result.untransferred == {source}
