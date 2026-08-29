"""Probity tests for pinned-v5.0.2 affected-interval evidence."""

from __future__ import annotations

import pytest
from pathlib import Path

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    HistoricalPopulationCheckpoint,
    HistoricalPopulationCheckpointStore,
    HistoricalShortfallEvidence,
    HistoricalVspdSourcePatcher,
)

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


def test_historical_source_patcher_is_exact_and_fail_closed(tmp_path) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "vSPDsettings.inc").write_text(
        "$setglobal inputPath                     '%system.fp%..\\Input\\'\n"
        "$setglobal outputPath                    '%system.fp%..\\Output\\'\n"
        "$setglobal ovrdPath                      '%system.fp%..\\Override\\'\n"
        "Scalar dailymode                         / 1 / ;\n"
        "$setglobal Solver                          Cplex\n"
    )
    (programs / "vSPDperiod.gms").write_text(
        '$ifthen exist "%inputPath%\\%GDXname%.gdx"\n'
        '$gdxin "%inputPath%\\%GDXname%.gdx"\n'
        "execute_unload '%programPath%\\vSPDperiod.gdx'\n"
    )
    (programs / "vSPDsolve.gms").write_text(
        'File rep "Write to a report" /"ProgressReport.txt"/;\n'
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        + '.Optfile = 1 ;\n' * 3
        +
        '$if not exist "%inputPath%\\%GDXname%.gdx" $goto nextInput\n'
        '$gdxin "%inputPath%\\%GDXname%.gdx"\n'
        "PotentialModellingInconsistency(ca,dt,n)= 1 $ outage(ca,dt,n) ;\n"
        "EnergyShortFallCheck(t,n) = 1 $ { (EnergyShortfallMW(t,n) > 0) and ok(t,n) } ;\n"
        "ShortfallAdjustmentMW(t,n) $ EligibleShortfallRemoval(t,n) = EnergyShortfallMW(t,n) ;\n"
        '$if not exist "%inputPath%\\%GDXname%.gdx" putclose rep "missing";\n'
    )

    patcher = HistoricalVspdSourcePatcher()
    result = patcher.apply(programs)

    assert result.profile == "historical-v5.0.2-scip-first-loop"
    assert len(result.logical_sha256) == 64
    settings = (programs / "vSPDsettings.inc").read_text()
    solve = (programs / "vSPDsolve.gms").read_text()
    assert "Scalar dailymode                         / 0 / ;" in settings
    assert "option lp = HiGHS ;" in solve
    assert "option mip = SCIP ;" in solve
    assert "EnergyShortfallMW(t,n) > 0.000001" in solve
    assert "gate12_%GDXname%_shortfall.txt" in solve

    with pytest.raises(EvidenceContractError, match="source drift"):
        patcher.apply(programs)


def _checkpoint() -> HistoricalPopulationCheckpoint:
    evidence = HistoricalShortfallEvidence.parse(
        HEADER
        + "51012022111800831|06-NOV-2022 07:00|WAI0111|1|4.5969|4.5971|1|1\n",
        source_name="Pricing_20221106",
    )
    return HistoricalPopulationCheckpoint.create(
        trading_date="20221106",
        source_sha256="2" * 64,
        patch_sha256="a" * 64,
        solver_profile="historical-v5.0.2-scip-first-loop",
        selected_case_count=278,
        solved_case_count=278,
        all_solves_optimal=True,
        evidence=evidence,
    )


def test_population_checkpoint_round_trips_and_is_reusable(tmp_path: Path) -> None:
    store = HistoricalPopulationCheckpointStore(tmp_path)
    checkpoint = _checkpoint()

    store.write(checkpoint)
    loaded = store.load("20221106")

    assert loaded == checkpoint
    assert loaded is not None
    assert loaded.affected_case_count == 1
    assert len(loaded.logical_sha256) == 64
    assert store.reusable(
        "20221106",
        source_sha256="2" * 64,
        patch_sha256="a" * 64,
        solver_profile="historical-v5.0.2-scip-first-loop",
    )
    assert not store.reusable(
        "20221106",
        source_sha256="3" * 64,
        patch_sha256="a" * 64,
        solver_profile="historical-v5.0.2-scip-first-loop",
    )


@pytest.mark.parametrize(
    "change,match",
    [
        ({"selected_case_count": 278, "solved_case_count": 277}, "every selected case"),
        ({"all_solves_optimal": False}, "optimal"),
        ({"source_sha256": "bad"}, "SHA-256"),
        ({"trading_date": "2022-11-06"}, "trading date"),
    ],
)
def test_population_checkpoint_fails_closed(
    change: dict[str, object], match: str
) -> None:
    arguments: dict[str, object] = {
        "trading_date": "20221106",
        "source_sha256": "2" * 64,
        "patch_sha256": "a" * 64,
        "solver_profile": "historical-v5.0.2-scip-first-loop",
        "selected_case_count": 278,
        "solved_case_count": 278,
        "all_solves_optimal": True,
        "evidence": HistoricalShortfallEvidence.parse(
            HEADER, source_name="Pricing_20221106"
        ),
    }
    arguments.update(change)

    with pytest.raises(EvidenceContractError, match=match):
        HistoricalPopulationCheckpoint.create(**arguments)  # type: ignore[arg-type]


def test_checkpoint_store_rejects_tampering(tmp_path: Path) -> None:
    store = HistoricalPopulationCheckpointStore(tmp_path)
    store.write(_checkpoint())
    path = tmp_path / "20221106.json"
    path.write_text(path.read_text().replace('"solved_case_count":278', '"solved_case_count":1'))

    with pytest.raises(EvidenceContractError, match="logical hash"):
        store.load("20221106")
