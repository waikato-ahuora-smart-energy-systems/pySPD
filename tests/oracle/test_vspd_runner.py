from __future__ import annotations

from pathlib import Path

import pytest

from tools.oracle.vspd import (
    ScipHighsPricingProfile,
    ScipSmokeProfile,
    SourcePatchError,
    VspdSourcePatcher,
)


def test_scip_profile_applies_fail_closed_source_overlay(tmp_path: Path) -> None:
    programs = tmp_path / "Programs"
    programs.mkdir()
    settings = programs / "vSPDsettings.inc"
    solve = programs / "vSPDsolve.gms"
    settings.write_text("$setglobal Solver                          Cplex\n")
    solve.write_text(
        "option lp = %Solver% ;\n"
        "option mip = %Solver% ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
        "vSPD_BranchFlowMIP.Optfile = 1 ;\n"
        "vSPD_NMIR.Optfile = 1 ;\n"
    )

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
    pricing = (programs / "pyspd_fixed_lp_solve.inc").read_text()
    assert "HVDCSENDING.fx(t,isl)" in pricing
    assert "LAMBDAHVDCRESERVE.fx(t,isl,resC,rd,rsbp)" in pricing
    assert "solve %pyspdPricingModel% using rmip" in pricing
    assert "HVDCSENDING.lo(t,isl) = pyspd_HVDCSENDING_lo(t,isl);" in pricing
    assert "$include pyspd_matrix_export.inc" in patched
    matrix_export = (programs / "pyspd_matrix_export.inc").read_text()
    assert "execute_unload 'pyspd_pricing_solution.gdx'" in matrix_export
    assert "ord(drs) = card(drs)" in matrix_export
    assert "pyspd_active_drs_ord" in matrix_export
    assert "option rmip = Convert;" in matrix_export
    assert "option rmip = HiGHS;" in matrix_export
    assert "solve vSPD_NMIR using rmip" in matrix_export
