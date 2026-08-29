"""Probity tests for pinned-v5.0.2 affected-interval evidence."""

from __future__ import annotations

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import HistoricalShortfallEvidence

HEADER = (
    "case_id|datetime|node|loop|energy_shortfall_mw|adjustment_mw|"
    "model_status|solver_status\n"
)


def test_historical_shortfall_evidence_accepts_optimal_first_loop_rows() -> None:
    text = HEADER + (
        "51012022111800831|06-NOV-2022 07:00|WAI0111|1|4.5969|4.5971|1|1\n"
        "51012022111800831|06-NOV-2022 07:00|WAI0501|1|0.5108|0.5110|1|1\n"
        "51012022111815836|06-NOV-2022 07:15|WAI0111|1|1.25|1.2502|1|1\n"
    )

    evidence = HistoricalShortfallEvidence.parse(text, source_name="Pricing_20221106")

    assert evidence.source_name == "Pricing_20221106"
    assert len(evidence.records) == 3
    assert evidence.affected_cases == (
        ("51012022111800831", "06-NOV-2022 07:00"),
        ("51012022111815836", "06-NOV-2022 07:15"),
    )


@pytest.mark.parametrize(
    "row,match",
    [
        (
            "5101|06-NOV-2022 07:00|WAI0111|2|4.5|4.5002|1|1\n",
            "first solve loop",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111|1|0.0000001|0.0002001|1|1\n",
            "material shortfall",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111|1|4.5|4.5002|8|1\n",
            "optimal solve",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111|1|nan|4.5002|1|1\n",
            "finite",
        ),
    ],
)
def test_historical_shortfall_evidence_fails_closed(row: str, match: str) -> None:
    with pytest.raises(EvidenceContractError, match=match):
        HistoricalShortfallEvidence.parse(
            HEADER + row, source_name="Pricing_20221106"
        )


def test_historical_shortfall_evidence_rejects_schema_drift() -> None:
    with pytest.raises(EvidenceContractError, match="schema"):
        HistoricalShortfallEvidence.parse(
            "case_id|datetime|node\n5101|date|node\n",
            source_name="Pricing_20221106",
        )
