from pyspd.contracts import CaseData
from pyspd.preprocess import Vspd506Preprocessor


def test_topology_derivations_match_vspd_semantics(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor().transform(representative_case)

    assert result.set("node").members == {
        ("C1", "D1", "N1"),
        ("C1", "D1", "N2"),
    }
    assert result.set("node_island").members == {
        ("C1", "D1", "N1", "NI"),
        ("C1", "D1", "N2", "SI"),
    }
    assert result.parameter("total_bus_allocation").get(("C1", "D1", "B1")) == 2.0
    assert (
        result.parameter("bus_node_allocation_factor").get(("C1", "D1", "B1", "N1"))
        == 1.0
    )
    assert result.set("ac_branch").members == {("C1", "D1", "BR1")}
    assert result.set("hvdc_link").members == {("C1", "D1", "HV1")}
    assert ("C1", "D1", "HV1") in result.set("branch").members
