from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.oracle.vspd import (
    ReportInventory,
    ScipHighsPricingProfile,
    ScipSmokeProfile,
    SourcePatchError,
    VspdRunConfiguration,
    VspdRunner,
    VspdSourcePatcher,
)


def test_scip_profile_applies_fail_closed_source_overlay(tmp_path: Path) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    settings = programs / "vSPDsettings.inc"
    solve = programs / "vSPDsolve.gms"
    report = programs / "vSPDreport.gms"
    settings.write_text("$setglobal Solver                          Cplex\n")
    solve.write_text(
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "vSPD_BranchFlowMIP.Optfile = 1 ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
    )
    report.write_text("loop(b $ o_bus(ca,dt,b), put b.tl);\n")

    VspdSourcePatcher().apply(programs, ScipSmokeProfile())

    assert "Solver                          SCIP" in settings.read_text()
    patched = solve.read_text()
    assert "option lp = HiGHS ;" in patched
    assert "option mip = %Solver% ;" in patched
    assert patched.count(".Optfile = 0 ;") == 3


def test_source_overlay_rejects_unexpected_upstream_text(tmp_path: Path) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "vSPDsettings.inc").write_text("$setglobal Solver Xpress\n")
    (programs / "vSPDsolve.gms").write_text("changed upstream")

    with pytest.raises(SourcePatchError, match="expected exactly"):
        VspdSourcePatcher().apply(programs, ScipSmokeProfile())


def test_explicit_run_configuration_overlay_is_fail_closed_and_hashed(
    tmp_path: Path,
) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    settings = programs / "vSPDsettings.inc"
    solve = programs / "vSPDsolve.gms"
    settings.write_text(
        "$setglobal runName                       source_default\n"
        "$setglobal opMode                          DPS\n"
        "$setglobal Solver                          Cplex\n"
    )
    solve.write_text(
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "vSPD_BranchFlowMIP.Optfile = 1 ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
    )
    configuration = VspdRunConfiguration(
        run_name="gate1_spd_fixture",
        operation_mode="SPD",
    )

    VspdSourcePatcher().apply(programs, ScipSmokeProfile(), configuration)

    patched = settings.read_text()
    assert "$setglobal runName                       gate1_spd_fixture" in patched
    assert "$setglobal opMode                          SPD" in patched
    assert len(configuration.logical_sha256) == 64


def test_audit_overlay_repairs_pinned_undeclared_bus_alias(tmp_path: Path) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    settings = programs / "vSPDsettings.inc"
    solve = programs / "vSPDsolve.gms"
    report = programs / "vSPDreport.gms"
    settings.write_text(
        "$setglobal runName                       source_default\n"
        "$setglobal opMode                          DPS\n"
        "$setglobal Solver                          Cplex\n"
    )
    solve.write_text(
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "vSPD_BranchFlowMIP.Optfile = 1 ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
    )
    report.write_text("loop(b $ o_bus(ca,dt,b), put b.tl);\n")

    VspdSourcePatcher().apply(
        programs,
        ScipSmokeProfile(),
        VspdRunConfiguration("gate1_aud_fixture", "AUD"),
    )

    assert "o_bus(ca,dt,b)" not in report.read_text()
    assert "bus(ca,dt,b)" in report.read_text()


@pytest.mark.parametrize(
    ("run_name", "operation_mode"),
    (("unsafe/name", "SPD"), ("safe_name", "PVT")),
)
def test_run_configuration_rejects_unsafe_or_out_of_scope_values(
    run_name: str,
    operation_mode: str,
) -> None:
    with pytest.raises(ValueError):
        VspdRunConfiguration(run_name, operation_mode)


def test_report_inventory_is_recursive_deterministic_and_content_addressed(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    nested = output / "nested"
    nested.mkdir(parents=True)
    (output / "summary.csv").write_text("a,b\n1,2\n")
    (nested / "audit.csv").write_text("x\n3\n")

    inventory = ReportInventory.build(output)

    assert [artifact.path for artifact in inventory.artifacts] == [
        "nested/audit.csv",
        "summary.csv",
    ]
    assert (
        inventory.artifacts[1].sha256
        == hashlib.sha256((output / "summary.csv").read_bytes()).hexdigest()
    )
    assert len(inventory.logical_sha256) == 64


def test_audit_mode_uses_normal_report_setup() -> None:
    assert VspdRunner._report_setup("AUD") == "vSPDreportSetup.gms"


def test_source_staging_excludes_repository_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Programs").mkdir()
    (source / "Programs" / "model.gms").write_text("model data")
    (source / ".git").mkdir()
    (source / ".git" / "objects").write_text("large history")
    destination = tmp_path / "stage"

    VspdRunner._stage_source_tree(source, destination)

    assert (destination / "Programs" / "model.gms").read_text() == "model data"
    assert not (destination / ".git").exists()


def test_fixed_lp_profile_injects_pricing_solve_after_each_mip(tmp_path: Path) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    settings = programs / "vSPDsettings.inc"
    solve = programs / "vSPDsolve.gms"
    settings.write_text("$setglobal Solver                          Cplex\n")
    solve.write_text(
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        "Parameters existing;\n"
        "Scalars\n"
        "  modelSolved 'status' / 0 /\n"
        "  ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
        "vSPD_BranchFlowMIP.Optfile = 1 ;\n"
        "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
        "*=====================================================================================\n"
        "* 9. Write results to CSV report files and GDX files\n"
        "*=====================================================================================\n"
    )

    VspdSourcePatcher().apply(programs, ScipHighsPricingProfile())

    patched = solve.read_text()
    assert "option rmip = HiGHS ;" in patched
    assert patched.count("$include pyspd_fixed_lp_solve.inc") == 3
    assert "$include pyspd_pricing_declarations.inc\n\nScalars" in patched
    assert (programs / "pyspd_pricing_declarations.inc").is_file()
    assert (programs / "pyspd_matrix_export.inc").is_file()
    assert (programs / "convert.opt").is_file()
    assert (programs / "scip.opt").read_text() == "numerics/feastol = 1e-7\n"
    assert "dual_feasibility_tolerance = 1e-9" in (
        programs / "highs.opt"
    ).read_text()
    assert patched.count(".Optfile = 1 ;") == 3
    pricing = (programs / "pyspd_fixed_lp_solve.inc").read_text()
    assert "HVDCSENDING.fx(t,isl)" in pricing
    assert "LAMBDAHVDCRESERVE.fx(t,isl,resC,rd,rsbp)" in pricing
    assert "solve %pyspdPricingModel% using rmip" in pricing
    assert "%pyspdPricingModel%.Optfile = 1;" in pricing
    assert "HVDCSENDING.lo(t,isl) = pyspd_HVDCSENDING_lo(t,isl);" in pricing
    assert "$include pyspd_matrix_export.inc" in patched
    matrix_export = (programs / "pyspd_matrix_export.inc").read_text()
    assert "execute_unload 'pyspd_pricing_solution.gdx'" in matrix_export
    assert "ord(drs) = card(drs)" in matrix_export
    assert "pyspd_active_drs_ord" in matrix_export
    assert "busDisconnected" in matrix_export
    assert "dtParameter, studyMode, node2node, nodeIsland" in matrix_export
    assert "option rmip = Convert;" in matrix_export
    assert "option rmip = HiGHS;" in matrix_export
    assert "solve vSPD_NMIR using rmip" in matrix_export
    assert "$else.pyspdDPS" in matrix_export
    assert "o_nodePrice_TP" in matrix_export
