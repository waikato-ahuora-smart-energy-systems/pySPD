"""Gate 12 v16 end-to-end oracle qualification contracts."""

from __future__ import annotations

from tools.gate12.v16_parity import load_v16_oracle


def test_v16_oracle_loader_preserves_price_identity_and_precision(tmp_path) -> None:
    prefix = tmp_path / "oracle"
    (tmp_path / "oracle_SummaryResults_TP.csv").write_text(
        '"CaseID","SystemOFV"\n"case-1",224118715.52425\n',
        encoding="utf-8",
    )
    (tmp_path / "oracle_PublishedEnergyPrices_TP.csv").write_text(
        '"DateTime","TradingPeriod","Pnodename","vSPDDollarsPerMegawattHour"\n'
        '"03-JUL-2026 14:55","TP30","ABY0111",68.02517\n',
        encoding="utf-8",
    )
    (tmp_path / "oracle_PublishedReservePrices_TP.csv").write_text(
        '"DateTime","TradingPeriod","Island",'
        '"vSPDFIRDollarsPerMegawattHour","vSPDSIRDollarsPerMegawattHour"\n'
        '"03-JUL-2026 14:55","TP30","NI",0.11000,0.50000\n',
        encoding="utf-8",
    )

    oracle = load_v16_oracle(prefix=prefix, case_id="case-1")

    assert oracle.objective == 224118715.52425
    assert [item.key for item in oracle.energy] == [
        (
            "case-1",
            "energy_price",
            ("03-JUL-2026 14:55", "TP30", "ABY0111"),
        )
    ]
    assert [item.value for item in oracle.reserve] == [0.11, 0.5]
    assert [item.identity[-1] for item in oracle.reserve] == ["FIR", "SIR"]
