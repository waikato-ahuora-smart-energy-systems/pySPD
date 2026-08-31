"""Probity tests for pinned-v5.0.2 affected-interval evidence."""

import json
from pathlib import Path

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    GamsTransferCaseIndexLoader,
    HistoricalAffectedManifestBuilder,
    HistoricalDailyCompletionValidator,
    HistoricalGdxCaseIndex,
    HistoricalInputArtifact,
    HistoricalInputInventory,
    HistoricalPopulationCheckpoint,
    HistoricalPopulationCheckpointStore,
    HistoricalShortfallEvidence,
    HistoricalVspdSourcePatcher,
)
from tools.oracle.vspd import ListingResult, SolveRecord

HEADER = (
    "case_id|datetime|node|target_node|loop|energy_shortfall_mw|adjustment_mw|"
    "model_status|solver_status\n"
)


def test_case_index_selects_only_disclosed_rtd_modes() -> None:
    index = GamsTransferCaseIndexLoader.select_rtd(
        periods={
            ("rtd", "06-NOV-2022 07:00"): "TP15",
            ("dispatch_lite", "06-NOV-2022 07:05"): "TP15",
            ("prss", "06-NOV-2022 07:30"): "TP16",
        },
        study_mode={"rtd": 101, "dispatch_lite": 201, "prss": 130},
    )

    assert index.cases == (
        ("rtd", "06-NOV-2022 07:00"),
        ("dispatch_lite", "06-NOV-2022 07:05"),
    )


def test_exact_positive_selector_is_machine_readably_invalidated() -> None:
    root = Path(__file__).resolve().parents[2]
    original = json.loads(
        (root / "docs/gate-12/historical-exact-positive-qualification.json").read_text()
    )
    evidence = json.loads(
        (root / "docs/gate-12/historical-exact-positive-invalidation.json").read_text()
    )

    assert original["classification"].startswith("invalidated-")
    assert original["qualifies_population"] is False
    assert original["superseded_by"].endswith("invalidation.json")
    assert evidence["classification"] == "invalidated-population-selector"
    assert evidence["observed_identity_count"] > evidence["declared_population_count"]
    assert evidence["observed_date_count"] < 139
    assert evidence["qualifies_population"] is False
    assert "dailymode0" in evidence["replacement_profile"]
    assert "actual node-to-node transfers" in evidence["replacement_rule"]


def test_material_transfer_population_method_is_hash_bound_and_qualified() -> None:
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads(
        (
            root / "docs/gate-12/historical-material-transfer-qualification.json"
        ).read_text()
    )

    assert evidence["classification"] == "qualifying-single-date-population-method"
    assert evidence["selected_case_count"] == evidence["solved_case_count"] == 270
    assert evidence["all_solves_optimal"] is True
    assert evidence["affected_identity_count"] == len(evidence["identities"]) == 4
    assert (
        evidence["evidence_record_count"]
        == sum(len(identity["transfers"]) for identity in evidence["identities"])
        == 6
    )
    assert all(evidence["independent_analytic_match"].values())
    assert evidence["population_passed"] is False
    assert all(len(value) == 64 for value in evidence["artifact_sha256"].values())


def test_historical_shortfall_evidence_accepts_optimal_material_transfer_rows() -> None:
    text = HEADER + (
        "51012022111800831|06-NOV-2022 07:00|WAI0111|WAI0501|1|4.5969|4.5971|1|1\n"
        "51012022111800831|06-NOV-2022 07:00|WAI0501|WAI1101|1|0.5108|0.5110|1|1\n"
        "51012022111815836|06-NOV-2022 07:15|WAI0111|WAI0501|1|1.25|1.2502|1|1\n"
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
            "5101|06-NOV-2022 07:00|WAI0111|WAI0501|2|4.5|4.5002|1|1\n",
            "first solve loop",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111|WAI0501|1|-0.0000001|0.0002001|1|1\n",
            "material shortfall",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111|WAI0501|1|4.5|4.5002|8|1\n",
            "optimal solve",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111|WAI0501|1|nan|4.5002|1|1\n",
            "finite",
        ),
        (
            "5101|06-NOV-2022 07:00|WAI0111||1|4.5|4.5002|1|1\n",
            "identity fields",
        ),
    ],
)
def test_historical_shortfall_evidence_fails_closed(row: str, match: str) -> None:
    with pytest.raises(EvidenceContractError, match=match):
        HistoricalShortfallEvidence.parse(HEADER + row, source_name="Pricing_20221106")


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
        + ".Optfile = 1 ;\n"
        * 3
        + '$if not exist "%inputPath%\\%GDXname%.gdx" $goto nextInput\n'
        '$gdxin "%inputPath%\\%GDXname%.gdx"\n'
        "PotentialModellingInconsistency(ca,dt,n)= 1 $ outage(ca,dt,n) ;\n"
        "EnergyShortFallCheck(t,n) = 1 $ { (EnergyShortfallMW(t,n) > 0) and ok(t,n) } ;\n"
        "loop( (t,n) $ EnergyShortfallMW(t,n),\n"
        "ShortfallAdjustmentMW(t,n) $ EligibleShortfallRemoval(t,n) = EnergyShortfallMW(t,n) ;\n"
        "            loop( nodeTonode(t,n,n1) $ ShortfallTransferFromTo(t,n,n1),\n"
        "               putclose rep 'Short fall adjustment from 'n.tl' to ', n1.tl,': ', ShortfallAdjustmentMW(t,n)' MW' /;\n"
        "            ) ;\n"
        '$if not exist "%inputPath%\\%GDXname%.gdx" putclose rep "missing";\n'
        '$gdxin "%inputPath%\\%GDXname%.gdx"\n'
    )

    patcher = HistoricalVspdSourcePatcher()
    result = patcher.apply(programs)

    assert result.profile == (
        "historical-v5.0.2-dailymode0-scip-first-loop-material-transfer"
    )
    assert len(result.logical_sha256) == 64
    settings = (programs / "vSPDsettings.inc").read_text()
    solve = (programs / "vSPDsolve.gms").read_text()
    assert "Scalar dailymode                         / 0 / ;" in settings
    assert "option lp = HiGHS ;" in solve
    assert "option mip = SCIP ;" in solve
    assert solve.count(".Optfile = 0 ;") == 3
    assert set(result.file_sha256) == {
        "vSPDperiod.gms",
        "vSPDsettings.inc",
        "vSPDsolve.gms",
    }
    assert "EnergyShortfallMW(t,n) > 0" in solve
    assert "EnergyShortfallMW(t,n) > 0.000001" not in solve
    assert "loop( (t,n) $ (abs(EnergyShortfallMW(t,n)) > 0.000001)," in solve
    assert "gate12_%GDXname%_shortfall.txt" in solve
    assert "n1.tl:0" in solve

    with pytest.raises(EvidenceContractError, match="source drift"):
        patcher.apply(programs)


def test_historical_evidence_rejects_eps_scale_actual_transfer() -> None:
    with pytest.raises(EvidenceContractError, match="material shortfall"):
        HistoricalShortfallEvidence.parse(
            HEADER + "case|date|node|target|1|0.0|0.0000001|1|1\n",
            source_name="Pricing_20221106",
        )


def _checkpoint() -> HistoricalPopulationCheckpoint:
    evidence = HistoricalShortfallEvidence.parse(
        HEADER
        + "51012022111800831|06-NOV-2022 07:00|WAI0111|WAI0501|1|4.5969|4.5971|1|1\n",
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
        artifact_sha256={
            "progress": "a" * 64,
            "listing": "b" * 64,
            "evidence": "c" * 64,
        },
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
    assert loaded.artifact_sha256 == {
        "evidence": "c" * 64,
        "listing": "b" * 64,
        "progress": "a" * 64,
    }
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
        "artifact_sha256": {
            "progress": "a" * 64,
            "listing": "b" * 64,
            "evidence": "c" * 64,
        },
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
    path.write_text(
        path.read_text().replace('"solved_case_count":278', '"solved_case_count":1')
    )

    with pytest.raises(EvidenceContractError, match="logical hash"):
        store.load("20221106")


def _solve(case_id: str, *, model_status: int = 1) -> SolveRecord:
    return SolveRecord(
        scenario=case_id,
        model="vSPD_NMIR",
        solve_type="MIP",
        solver="SCIP",
        solver_status_code=1,
        solver_status="Normal Completion",
        model_status_code=model_status,
        model_status="Optimal" if model_status == 1 else "Integer Solution",
        objective=1.0,
    )


def test_daily_completion_requires_exact_successful_optimal_population() -> None:
    selected = (
        ("51012022111800831", "06-NOV-2022 07:00"),
        ("51012022111805834", "06-NOV-2022 07:05"),
    )
    progress = "\n".join(
        f"The caseID: {case} ({date_time}) is 1st solved successfully."
        for case, date_time in selected
    )
    listing = ListingResult(records=tuple(_solve(case) for case, _ in selected))

    checkpoint = HistoricalDailyCompletionValidator().validate(
        trading_date="20221106",
        source_sha256="2" * 64,
        patch_sha256="a" * 64,
        solver_profile="historical-v5.0.2-scip-first-loop",
        selected_cases=selected,
        progress_text=progress,
        listing=listing,
        listing_text="listing",
        evidence_text=HEADER
        + "51012022111800831|06-NOV-2022 07:00|WAI0111|WAI0501|1|4.5|4.5|1|1\n",
    )

    assert checkpoint.selected_case_count == 2
    assert checkpoint.solved_case_count == 2


def test_daily_completion_rejects_noncanonical_solve_order() -> None:
    selected = (
        ("case_1", "06-NOV-2022 07:00"),
        ("case_2", "06-NOV-2022 07:05"),
    )
    progress = "\n".join(
        f"The caseID: {case} ({date_time}) is 1st solved successfully."
        for case, date_time in reversed(selected)
    )

    with pytest.raises(EvidenceContractError, match="daily completion"):
        HistoricalDailyCompletionValidator().validate(
            trading_date="20221106",
            source_sha256="2" * 64,
            patch_sha256="a" * 64,
            solver_profile="historical-v5.0.2-scip-first-loop",
            selected_cases=selected,
            progress_text=progress,
            listing=ListingResult(records=tuple(_solve(case) for case, _ in selected)),
            listing_text="listing",
            evidence_text=HEADER,
        )


@pytest.mark.parametrize("failure", ["missing", "non_optimal", "wrong_solver"])
def test_daily_completion_fails_closed(failure: str) -> None:
    selected = (("case_1", "06-NOV-2022 07:00"),)
    progress = "The caseID: case_1 (06-NOV-2022 07:00) is 1st solved successfully."
    record = _solve("case_1", model_status=8 if failure == "non_optimal" else 1)
    if failure == "wrong_solver":
        record = SolveRecord(**{**record.__dict__, "solver": "CPLEX"})
    if failure == "missing":
        progress = ""

    with pytest.raises(EvidenceContractError, match="daily completion"):
        HistoricalDailyCompletionValidator().validate(
            trading_date="20221106",
            source_sha256="2" * 64,
            patch_sha256="a" * 64,
            solver_profile="historical-v5.0.2-scip-first-loop",
            selected_cases=selected,
            progress_text=progress,
            listing=ListingResult(records=(record,)),
            listing_text="listing",
            evidence_text=HEADER,
        )


def test_historical_manifest_builder_requires_exact_546_across_139_dates() -> None:
    artifacts = []
    checkpoints = []
    indices = {}
    for date_index in range(139):
        trading_date = f"2022{date_index:04d}"
        source_sha256 = f"{date_index + 1:064x}"
        affected_count = 4 if date_index < 129 else 3
        cases = tuple(
            (f"case_{date_index}_{case_index}", f"DT-{date_index}-{case_index}")
            for case_index in range(affected_count)
        )
        rows = "".join(
            f"{case}|{date_time}|NODE|TARGET|1|1.0|1.0|1|1\n"
            for case, date_time in cases
        )
        evidence = HistoricalShortfallEvidence.parse(
            HEADER + rows, source_name=f"Pricing_{trading_date}"
        )
        artifacts.append(HistoricalInputArtifact(trading_date, 1, source_sha256))
        checkpoints.append(
            HistoricalPopulationCheckpoint.create(
                trading_date=trading_date,
                source_sha256=source_sha256,
                patch_sha256="a" * 64,
                solver_profile="historical-v5.0.2-scip-first-loop",
                selected_case_count=affected_count,
                solved_case_count=affected_count,
                all_solves_optimal=True,
                artifact_sha256={
                    "progress": "a" * 64,
                    "listing": "b" * 64,
                    "evidence": "c" * 64,
                },
                evidence=evidence,
            )
        )
        indices[trading_date] = HistoricalGdxCaseIndex(
            cases=cases,
            trading_periods={case: f"TP{i + 1}" for i, case in enumerate(cases)},
        )

    manifest = HistoricalAffectedManifestBuilder().build(
        checkpoints=tuple(checkpoints),
        inventory=HistoricalInputInventory(tuple(artifacts)),
        case_indices=indices,
        source_release="v5.0.4",
        reference_commit="3360a91",
    )

    assert len(manifest.identities) == 546
    assert len({identity.trading_date for identity in manifest.identities}) == 139
    assert "first-loop" in manifest.identities[0].discovery_rationale
    assert "non-daily" in manifest.identities[0].discovery_rationale
    assert "material shortfall transfer" in manifest.identities[0].discovery_rationale
