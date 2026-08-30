"""Probity tests for pinned-GAMS Gate 12 replay instrumentation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.orchestration.conftest import make_daily_case
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.gams_replay import (
    GamsReplaySurfaceExporter,
    Gate12GamsSourcePatcher,
)
from tools.gate12.incremental_replay import IncrementalReplayWorkItem
from tools.gate12.pyspd_surfaces import CanonicalCaseSurfaces
from tools.oracle.vspd import ScipHighsPricingProfile, VspdRunConfiguration


def _programs(tmp_path: Path) -> Path:
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "vSPDsettings.inc").write_text(
        "$setglobal runName                       source_default\n"
        "$setglobal opMode                          SPD\n"
        "$setglobal Solver                          Cplex\n"
        "Scalar dailymode                         / 1 / ;\n"
    )
    (programs / "vSPDsolve.gms").write_text(
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        "Parameters\n"
        "  casefileseconds(ca,tp) description\n"
        "\nScalars\n"
        "  modelSolved 'status' / 0 /\n"
        "  ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
        "vSPD_BranchFlowMIP.Optfile = 1 ;\n"
        "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
        "        busPrice(bus(t,b))      = ACnodeNetInjectionDefinition2.m(t,b) ;\n"
        "            ShortfallAdjustmentMW(t,n) $ sum[ n1, ShortfallTransferFromTo(t,n,n1)] = 0;\n"
        "*   Reporting at trading period start\n"
        "*       branch output\n"
        "* 9. Write results to CSV report files and GDX files\n"
    )
    (programs / "vSPDperiod.gms").write_text("period source\n")
    return programs


def test_gams_replay_overlay_captures_cumulative_daily_state(tmp_path: Path) -> None:
    programs = _programs(tmp_path)
    configuration = VspdRunConfiguration(
        "gate12_ref_20221106",
        "SPD",
        daily_mode=1,
        case_ids=("warmup", "affected"),
    )

    Gate12GamsSourcePatcher(affected_case_ids=("affected",)).apply(
        programs,
        ScipHighsPricingProfile(capture_state_evidence=False),
        configuration,
    )

    solve = (programs / "vSPDsolve.gms").read_text()
    assert "pyspd_gate12_raw_bus_price" in solve
    assert "pyspd_gate12_repaired_bus_price" in solve
    assert "pyspd_gate12_transfer_mw" in solve
    assert "pyspd_gate12_final_required_load" in solve
    assert "pyspd_gate12_HVDCSENDING" in solve
    assert "execute_unload 'pyspd_gate12_results.gdx'" in solve
    assert "o_PublisedSIRPrice_TP" in solve
    assert (programs / "vSPDtpsToSolve.inc").read_text() == ("/ warmup, affected /\n")


def test_gams_replay_overlay_rejects_non_daily_or_partial_prefix(
    tmp_path: Path,
) -> None:
    programs = _programs(tmp_path)
    patcher = Gate12GamsSourcePatcher(affected_case_ids=("affected",))

    with pytest.raises(EvidenceContractError, match="daily mode"):
        patcher.apply(
            programs,
            ScipHighsPricingProfile(capture_state_evidence=False),
            VspdRunConfiguration(
                "gate12_ref", "SPD", daily_mode=0, case_ids=("affected",)
            ),
        )

    with pytest.raises(EvidenceContractError, match="absent from the replay prefix"):
        patcher.apply(
            programs,
            ScipHighsPricingProfile(capture_state_evidence=False),
            VspdRunConfiguration(
                "gate12_ref", "SPD", daily_mode=1, case_ids=("warmup",)
            ),
        )


class _Evidence:
    def __init__(self, case_id: str, date_time: str) -> None:
        prefix = (case_id, date_time)
        self.data = {
            "o_offerEnergy_TP": {(*prefix, "O1"): 10.0},
            "o_busGeneration_TP": {(*prefix, "B1"): 10.0},
            "o_busLoad_TP": {(*prefix, "B1"): 10.0},
            "pyspd_gate12_raw_bus_price": {(*prefix, "B1"): 49.0},
            "pyspd_gate12_repaired_bus_price": {(*prefix, "B1"): 50.0},
            "o_nodePrice_TP": {(*prefix, "N1"): 50.0},
            "pyspd_gate12_final_required_load": {(*prefix, "N1"): 10.0},
            "pyspd_gate12_final_energy_shortfall": {(*prefix, "N1"): 0.0},
            "o_ResPrice_TP": {(*prefix, "NI", "FIR"): 5.0},
            "pyspd_gate12_transfer_mw": {},
            "pyspd_gate12_untransferred": {},
            "pyspd_gate12_solve_count": {prefix: 1.0},
            "pyspd_gate12_primary_objective": {prefix: 100.0},
            "o_PublisedPrice_TP": {("TP1", "N1"): 50.0},
            "o_PublisedFIRPrice_TP": {("TP1", "NI"): 5.0},
            "o_PublisedSIRPrice_TP": {("TP1", "NI"): 0.0},
        }

    def members(self, name, *, prefix):
        suffix = {"offer": "O1", "bus": "B1", "node": "N1"}[name]
        return ((*prefix, suffix),)

    def numeric(self, name):
        return self.data.get(name, {})

    def value(self, name, key):
        return self.numeric(name).get(key, 0.0)


def test_gams_surface_projection_keeps_all_twelve_layers(tmp_path: Path) -> None:
    case_id = "affected"
    selected = make_daily_case(case_id, trading_period="TP1")
    work_item = IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256="0" * 64,
        discovery_checkpoint_sha256="1" * 64,
        case_ids=(case_id,),
        affected_case_ids=(case_id,),
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "gate12_BusResults_TP.csv").write_text(
        '"CaseID","DateTime","Period","Bus","Price"\n'
        f'"{case_id}","{selected.date_time}","TP1","B1",50.000\n'
    )

    projected = GamsReplaySurfaceExporter()._case_surfaces(
        work_item=work_item,
        selected=selected,
        evidence=_Evidence(case_id, selected.date_time),  # type: ignore[arg-type]
        report_directory=reports,
        total_seconds={"TP1": 300.0},
    )

    assert isinstance(projected, CanonicalCaseSurfaces)
    assert len(projected.surfaces) == 12
    assert (
        projected.surface_sha256["raw-bus-price"]
        != projected.surface_sha256["repaired-bus-price"]
    )
