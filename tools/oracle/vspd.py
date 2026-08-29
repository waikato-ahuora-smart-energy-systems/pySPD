"""Fail-closed execution and objective comparison for pinned vSPD sources.

The runner stages a source checkout before changing any settings. The pinned
checkout and input fixture therefore remain immutable evidence. The qualified
SCIP MIP to fixed-discrete HiGHS RMIP profile is the active interim reference;
native CPLEX remains deferred cross-validation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import resource
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Final

from tools.oracle.canonical import (
    ConvertDictionaryReader,
    ConvertMatrixReader,
    GdxCanonicalizer,
    LinearMatrixValidation,
    LinearMatrixValidator,
)
from tools.oracle.price_validation import (
    GdxPriceValidator,
    GdxPublishedPriceValidator,
    IndependentPriceValidation,
)

PRIMARY_MODEL: Final = "vSPD_NMIR"
CLEANUP_MODEL: Final = "vSPD_BranchFlowMIP"

_PRICING_DECLARATIONS: Final = """* pySPD Gate 1 fixed-LP pricing overlay
Parameters
  pyspd_HVDCSENDING_lo(ca,dt,isl)
  pyspd_HVDCSENDING_up(ca,dt,isl)
  pyspd_INZONE_lo(ca,dt,isl,resC,z)
  pyspd_INZONE_up(ca,dt,isl,resC,z)
  pyspd_HVDCSENTINSEGMENT_lo(ca,dt,isl,los)
  pyspd_HVDCSENTINSEGMENT_up(ca,dt,isl,los)
  pyspd_PURCHASEBLOCKBINARY_lo(ca,dt,bd,blk)
  pyspd_PURCHASEBLOCKBINARY_up(ca,dt,bd,blk)
  pyspd_HVDCSENDZERO_lo(ca,dt,isl)
  pyspd_HVDCSENDZERO_up(ca,dt,isl)
  pyspd_ACBRANCHFLOWDIRECTED_INTEGER_lo(ca,dt,br,fd)
  pyspd_ACBRANCHFLOWDIRECTED_INTEGER_up(ca,dt,br,fd)
  pyspd_HVDCLINKFLOWDIRECTED_INTEGER_lo(ca,dt,fd)
  pyspd_HVDCLINKFLOWDIRECTED_INTEGER_up(ca,dt,fd)
  pyspd_HVDCPOLEFLOW_INTEGER_lo(ca,dt,pole,fd)
  pyspd_HVDCPOLEFLOW_INTEGER_up(ca,dt,pole,fd)
  pyspd_LAMBDAINTEGER_lo(ca,dt,br,bp)
  pyspd_LAMBDAINTEGER_up(ca,dt,br,bp)
  pyspd_LAMBDAHVDCENERGY_lo(ca,dt,isl,bp)
  pyspd_LAMBDAHVDCENERGY_up(ca,dt,isl,bp)
  pyspd_LAMBDAHVDCRESERVE_lo(ca,dt,isl,resC,rd,rsbp)
  pyspd_LAMBDAHVDCRESERVE_up(ca,dt,isl,resC,rd,rsbp)
  ;
Scalar
  pyspd_primary_objective
  pyspd_pricing_objective_delta
  pyspd_active_drs_ord
  pyspd_solve_ordinal / 0 /
  ;
Sets
  pyspd_snapshot_model(*) 'model selected for the current solve snapshot'
  pyspd_snapshot_type(*)  'solve type selected for the current solve snapshot'
  pyspd_snapshot_phase(*) 'pre or post phase of the current solve snapshot'
  ;
File pyspd_convert_options / 'convert.opt' /;
"""

_PRE_SOLVE_SNAPSHOT: Final = """* pySPD Gate 1 complete pre-solve state snapshot.
pyspd_solve_ordinal = pyspd_solve_ordinal + 1;
pyspd_snapshot_model('vSPD_NMIR') = no;
pyspd_snapshot_model('vSPD_BranchFlowMIP') = no;
pyspd_snapshot_type('MIP') = no;
pyspd_snapshot_type('RMIP') = no;
pyspd_snapshot_phase('pre') = no;
pyspd_snapshot_phase('post') = no;
pyspd_snapshot_model('%pyspdSolveModel%') = yes;
pyspd_snapshot_type('%pyspdSolveType%') = yes;
pyspd_snapshot_phase('pre') = yes;
put_utility 'gdxout' / 'pyspd_solve_' pyspd_solve_ordinal:0:0 '_pre';
$onImplicitAssign
execute_unload;
$offImplicitAssign
put pyspd_convert_options;
put 'dumpgdx pyspd_solve_' pyspd_solve_ordinal:0:0 '_matrix.gdx'/
    'dictmap pyspd_solve_' pyspd_solve_ordinal:0:0 '_dict.gdx'/
    'gdxnames 1'/
    'gdxuels 1'/
    'headerTimeStamp none'/;
putclose pyspd_convert_options;
option %pyspdSolveType% = Convert;
%pyspdSolveModel%.Optfile = 1;
solve %pyspdSolveModel% using %pyspdSolveType% maximizing NETBENEFIT;
option %pyspdSolveType% = %pyspdSolveSolver%;
"""

_POST_SOLVE_SNAPSHOT: Final = """* pySPD Gate 1 complete post-solve state snapshot.
pyspd_snapshot_phase('pre') = no;
pyspd_snapshot_phase('post') = no;
pyspd_snapshot_phase('post') = yes;
put_utility 'gdxout' / 'pyspd_solve_' pyspd_solve_ordinal:0:0 '_post';
$onImplicitAssign
execute_unload;
$offImplicitAssign
"""

_FIXED_LP_SOLVE: Final = """* pySPD Gate 1: emulate CPLEX solveFinal explicitly.
* Snapshot bounds so the next demand scenario starts from the pristine domains.
pyspd_primary_objective = NETBENEFIT.l;

pyspd_HVDCSENDING_lo(t,isl) = HVDCSENDING.lo(t,isl);
pyspd_HVDCSENDING_up(t,isl) = HVDCSENDING.up(t,isl);
pyspd_INZONE_lo(t,isl,resC,z) = INZONE.lo(t,isl,resC,z);
pyspd_INZONE_up(t,isl,resC,z) = INZONE.up(t,isl,resC,z);
pyspd_HVDCSENTINSEGMENT_lo(t,isl,los) = HVDCSENTINSEGMENT.lo(t,isl,los);
pyspd_HVDCSENTINSEGMENT_up(t,isl,los) = HVDCSENTINSEGMENT.up(t,isl,los);
pyspd_PURCHASEBLOCKBINARY_lo(t,bd,blk) = PURCHASEBLOCKBINARY.lo(t,bd,blk);
pyspd_PURCHASEBLOCKBINARY_up(t,bd,blk) = PURCHASEBLOCKBINARY.up(t,bd,blk);
pyspd_HVDCSENDZERO_lo(t,isl) = HVDCSENDZERO.lo(t,isl);
pyspd_HVDCSENDZERO_up(t,isl) = HVDCSENDZERO.up(t,isl);
pyspd_ACBRANCHFLOWDIRECTED_INTEGER_lo(t,br,fd) = ACBRANCHFLOWDIRECTED_INTEGER.lo(t,br,fd);
pyspd_ACBRANCHFLOWDIRECTED_INTEGER_up(t,br,fd) = ACBRANCHFLOWDIRECTED_INTEGER.up(t,br,fd);
pyspd_HVDCLINKFLOWDIRECTED_INTEGER_lo(t,fd) = HVDCLINKFLOWDIRECTED_INTEGER.lo(t,fd);
pyspd_HVDCLINKFLOWDIRECTED_INTEGER_up(t,fd) = HVDCLINKFLOWDIRECTED_INTEGER.up(t,fd);
pyspd_HVDCPOLEFLOW_INTEGER_lo(t,pole,fd) = HVDCPOLEFLOW_INTEGER.lo(t,pole,fd);
pyspd_HVDCPOLEFLOW_INTEGER_up(t,pole,fd) = HVDCPOLEFLOW_INTEGER.up(t,pole,fd);
pyspd_LAMBDAINTEGER_lo(t,br,bp) = LAMBDAINTEGER.lo(t,br,bp);
pyspd_LAMBDAINTEGER_up(t,br,bp) = LAMBDAINTEGER.up(t,br,bp);
pyspd_LAMBDAHVDCENERGY_lo(t,isl,bp) = LAMBDAHVDCENERGY.lo(t,isl,bp);
pyspd_LAMBDAHVDCENERGY_up(t,isl,bp) = LAMBDAHVDCENERGY.up(t,isl,bp);
pyspd_LAMBDAHVDCRESERVE_lo(t,isl,resC,rd,rsbp) = LAMBDAHVDCRESERVE.lo(t,isl,resC,rd,rsbp);
pyspd_LAMBDAHVDCRESERVE_up(t,isl,resC,rd,rsbp) = LAMBDAHVDCRESERVE.up(t,isl,resC,rd,rsbp);

* GAMS defines binaries and variables in SOS sets as discrete for solveFinal.
HVDCSENDING.fx(t,isl) = round(HVDCSENDING.l(t,isl));
INZONE.fx(t,isl,resC,z) = round(INZONE.l(t,isl,resC,z));
HVDCSENTINSEGMENT.fx(t,isl,los) = round(HVDCSENTINSEGMENT.l(t,isl,los));
PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));
HVDCSENDZERO.fx(t,isl) = round(HVDCSENDZERO.l(t,isl));
ACBRANCHFLOWDIRECTED_INTEGER.fx(t,br,fd) = ACBRANCHFLOWDIRECTED_INTEGER.l(t,br,fd);
HVDCLINKFLOWDIRECTED_INTEGER.fx(t,fd) = HVDCLINKFLOWDIRECTED_INTEGER.l(t,fd);
HVDCPOLEFLOW_INTEGER.fx(t,pole,fd) = HVDCPOLEFLOW_INTEGER.l(t,pole,fd);
LAMBDAINTEGER.fx(t,br,bp) = LAMBDAINTEGER.l(t,br,bp);
LAMBDAHVDCENERGY.fx(t,isl,bp) = LAMBDAHVDCENERGY.l(t,isl,bp);
LAMBDAHVDCRESERVE.fx(t,isl,resC,rd,rsbp) = LAMBDAHVDCRESERVE.l(t,isl,resC,rd,rsbp);

%pyspdPricingModel%.Optfile = 1;
%pyspdPricingModel%.reslim = LPTimeLimit;
%pyspdPricingModel%.iterlim = LPIterationLimit;
$setglobal pyspdSolveModel %pyspdPricingModel%
$setglobal pyspdSolveType RMIP
$setglobal pyspdSolveSolver %pyspdPricingSolver%
$include pyspd_pre_solve_snapshot.inc
solve %pyspdPricingModel% using rmip maximizing NETBENEFIT;
$include pyspd_post_solve_snapshot.inc
abort$((%pyspdPricingModel%.solvestat <> 1) or (%pyspdPricingModel%.modelstat <> 1))
  'pySPD fixed-discrete pricing RMIP failed';
pyspd_pricing_objective_delta = abs(NETBENEFIT.l - pyspd_primary_objective);
abort$(pyspd_pricing_objective_delta > 0.01)
  'pySPD pricing RMIP changed the objective by more than NZD 0.01',
  pyspd_primary_objective, NETBENEFIT.l, pyspd_pricing_objective_delta;

* Restore domains without replacing the pricing-LP levels or equation marginals.
HVDCSENDING.lo(t,isl) = pyspd_HVDCSENDING_lo(t,isl);
HVDCSENDING.up(t,isl) = pyspd_HVDCSENDING_up(t,isl);
INZONE.lo(t,isl,resC,z) = pyspd_INZONE_lo(t,isl,resC,z);
INZONE.up(t,isl,resC,z) = pyspd_INZONE_up(t,isl,resC,z);
HVDCSENTINSEGMENT.lo(t,isl,los) = pyspd_HVDCSENTINSEGMENT_lo(t,isl,los);
HVDCSENTINSEGMENT.up(t,isl,los) = pyspd_HVDCSENTINSEGMENT_up(t,isl,los);
PURCHASEBLOCKBINARY.lo(t,bd,blk) = pyspd_PURCHASEBLOCKBINARY_lo(t,bd,blk);
PURCHASEBLOCKBINARY.up(t,bd,blk) = pyspd_PURCHASEBLOCKBINARY_up(t,bd,blk);
HVDCSENDZERO.lo(t,isl) = pyspd_HVDCSENDZERO_lo(t,isl);
HVDCSENDZERO.up(t,isl) = pyspd_HVDCSENDZERO_up(t,isl);
ACBRANCHFLOWDIRECTED_INTEGER.lo(t,br,fd) = pyspd_ACBRANCHFLOWDIRECTED_INTEGER_lo(t,br,fd);
ACBRANCHFLOWDIRECTED_INTEGER.up(t,br,fd) = pyspd_ACBRANCHFLOWDIRECTED_INTEGER_up(t,br,fd);
HVDCLINKFLOWDIRECTED_INTEGER.lo(t,fd) = pyspd_HVDCLINKFLOWDIRECTED_INTEGER_lo(t,fd);
HVDCLINKFLOWDIRECTED_INTEGER.up(t,fd) = pyspd_HVDCLINKFLOWDIRECTED_INTEGER_up(t,fd);
HVDCPOLEFLOW_INTEGER.lo(t,pole,fd) = pyspd_HVDCPOLEFLOW_INTEGER_lo(t,pole,fd);
HVDCPOLEFLOW_INTEGER.up(t,pole,fd) = pyspd_HVDCPOLEFLOW_INTEGER_up(t,pole,fd);
LAMBDAINTEGER.lo(t,br,bp) = pyspd_LAMBDAINTEGER_lo(t,br,bp);
LAMBDAINTEGER.up(t,br,bp) = pyspd_LAMBDAINTEGER_up(t,br,bp);
LAMBDAHVDCENERGY.lo(t,isl,bp) = pyspd_LAMBDAHVDCENERGY_lo(t,isl,bp);
LAMBDAHVDCENERGY.up(t,isl,bp) = pyspd_LAMBDAHVDCENERGY_up(t,isl,bp);
LAMBDAHVDCRESERVE.lo(t,isl,resC,rd,rsbp) = pyspd_LAMBDAHVDCRESERVE_lo(t,isl,resC,rd,rsbp);
LAMBDAHVDCRESERVE.up(t,isl,resC,rd,rsbp) = pyspd_LAMBDAHVDCRESERVE_up(t,isl,resC,rd,rsbp);
"""

_MATRIX_EXPORT: Final = """* pySPD Gate 1 canonical solution and matrix export.
put pyspd_convert_options;
put 'dumpgdx pyspd_pricing_matrix.gdx'/
    'dictmap pyspd_pricing_dict.gdx'/
    'gdxnames 1'/
    'gdxuels 1'/
    'headerTimeStamp none'/;
putclose pyspd_convert_options;
$iftheni.pyspdDPS %opMode%=='DPS'
if (ord(drs) = card(drs),
  pyspd_active_drs_ord = ord(drs);
  HVDCSENDING.fx(t,isl) = round(HVDCSENDING.l(t,isl));
  INZONE.fx(t,isl,resC,z) = round(INZONE.l(t,isl,resC,z));
  HVDCSENTINSEGMENT.fx(t,isl,los) = round(HVDCSENTINSEGMENT.l(t,isl,los));
  PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));
  HVDCSENDZERO.fx(t,isl) = round(HVDCSENDZERO.l(t,isl));
  ACBRANCHFLOWDIRECTED_INTEGER.fx(t,br,fd) = ACBRANCHFLOWDIRECTED_INTEGER.l(t,br,fd);
  HVDCLINKFLOWDIRECTED_INTEGER.fx(t,fd) = HVDCLINKFLOWDIRECTED_INTEGER.l(t,fd);
  HVDCPOLEFLOW_INTEGER.fx(t,pole,fd) = HVDCPOLEFLOW_INTEGER.l(t,pole,fd);
  LAMBDAINTEGER.fx(t,br,bp) = LAMBDAINTEGER.l(t,br,bp);
  LAMBDAHVDCENERGY.fx(t,isl,bp) = LAMBDAHVDCENERGY.l(t,isl,bp);
  LAMBDAHVDCRESERVE.fx(t,isl,resC,rd,rsbp) = LAMBDAHVDCRESERVE.l(t,isl,resC,rd,rsbp);

  execute_unload 'pyspd_pricing_solution.gdx'
    t, n, b, nodeBus, nodeBusAllocationFactor, pricing_nodes,
    drs, pyspd_active_drs_ord, demandscale, ACnodeNetInjectionDefinition2,
    busPrice, o_nodePrice_TP, o_drsnodeprice, NETBENEFIT,
    HVDCSENDING, INZONE, HVDCSENTINSEGMENT, PURCHASEBLOCKBINARY, HVDCSENDZERO,
    ACBRANCHFLOWDIRECTED_INTEGER, HVDCLINKFLOWDIRECTED_INTEGER,
    HVDCPOLEFLOW_INTEGER, LAMBDAINTEGER, LAMBDAHVDCENERGY, LAMBDAHVDCRESERVE;

  option rmip = Convert;
  if (sum(t, SOS1_solve(t)),
    vSPD_BranchFlowMIP.Optfile = 1;
    solve vSPD_BranchFlowMIP using rmip maximizing NETBENEFIT;
  else
    vSPD_NMIR.Optfile = 1;
    solve vSPD_NMIR using rmip maximizing NETBENEFIT;
  );
  option rmip = HiGHS;
);
$else.pyspdDPS
HVDCSENDING.fx(t,isl) = round(HVDCSENDING.l(t,isl));
INZONE.fx(t,isl,resC,z) = round(INZONE.l(t,isl,resC,z));
HVDCSENTINSEGMENT.fx(t,isl,los) = round(HVDCSENTINSEGMENT.l(t,isl,los));
PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));
HVDCSENDZERO.fx(t,isl) = round(HVDCSENDZERO.l(t,isl));
ACBRANCHFLOWDIRECTED_INTEGER.fx(t,br,fd) = ACBRANCHFLOWDIRECTED_INTEGER.l(t,br,fd);
HVDCLINKFLOWDIRECTED_INTEGER.fx(t,fd) = HVDCLINKFLOWDIRECTED_INTEGER.l(t,fd);
HVDCPOLEFLOW_INTEGER.fx(t,pole,fd) = HVDCPOLEFLOW_INTEGER.l(t,pole,fd);
LAMBDAINTEGER.fx(t,br,bp) = LAMBDAINTEGER.l(t,br,bp);
LAMBDAHVDCENERGY.fx(t,isl,bp) = LAMBDAHVDCENERGY.l(t,isl,bp);
LAMBDAHVDCRESERVE.fx(t,isl,resC,rd,rsbp) = LAMBDAHVDCRESERVE.l(t,isl,resC,rd,rsbp);

execute_unload 'pyspd_pricing_solution.gdx'
  t, n, b, nodeBus, nodeBusAllocationFactor,
  ACnodeNetInjectionDefinition2, busPrice, busDisconnected,
  dtParameter, studyMode, node2node, nodeIsland, o_nodePrice_TP, NETBENEFIT,
  HVDCSENDING, INZONE, HVDCSENTINSEGMENT, PURCHASEBLOCKBINARY, HVDCSENDZERO,
  ACBRANCHFLOWDIRECTED_INTEGER, HVDCLINKFLOWDIRECTED_INTEGER,
  HVDCPOLEFLOW_INTEGER, LAMBDAINTEGER, LAMBDAHVDCENERGY, LAMBDAHVDCRESERVE;

option rmip = Convert;
if (sum(t, SOS1_solve(t)),
  vSPD_BranchFlowMIP.Optfile = 1;
  solve vSPD_BranchFlowMIP using rmip maximizing NETBENEFIT;
else
  vSPD_NMIR.Optfile = 1;
  solve vSPD_NMIR using rmip maximizing NETBENEFIT;
);
option rmip = HiGHS;
$endif.pyspdDPS
"""

_CONVERT_OPTIONS: Final = """dumpgdx pyspd_pricing_matrix.gdx
dictmap pyspd_pricing_dict.gdx
gdxnames 1
gdxuels 1
headerTimeStamp none
"""


def _add_v16_battery_discrete(
    declarations: str, fixed_lp_solve: str, matrix_export: str
) -> tuple[str, str, str]:
    """Extend the v5 pricing overlay with the sole new v16 binary family."""

    declarations = declarations.replace(
        "  pyspd_LAMBDAHVDCRESERVE_up(ca,dt,isl,resC,rd,rsbp)\n  ;",
        "  pyspd_LAMBDAHVDCRESERVE_up(ca,dt,isl,resC,rd,rsbp)\n"
        "  pyspd_BATTERYCHARGINGMODE_lo(ca,dt,n,n1)\n"
        "  pyspd_BATTERYCHARGINGMODE_up(ca,dt,n,n1)\n"
        "  ;",
    )
    fixed_lp_solve = fixed_lp_solve.replace(
        "pyspd_PURCHASEBLOCKBINARY_up(t,bd,blk) = PURCHASEBLOCKBINARY.up(t,bd,blk);",
        "pyspd_PURCHASEBLOCKBINARY_up(t,bd,blk) = PURCHASEBLOCKBINARY.up(t,bd,blk);\n"
        "pyspd_BATTERYCHARGINGMODE_lo(t,n,n1) = BATTERYCHARGINGMODE.lo(t,n,n1);\n"
        "pyspd_BATTERYCHARGINGMODE_up(t,n,n1) = BATTERYCHARGINGMODE.up(t,n,n1);",
        1,
    )
    fixed_lp_solve = fixed_lp_solve.replace(
        "PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));",
        "PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));\n"
        "BATTERYCHARGINGMODE.fx(t,n,n1) = round(BATTERYCHARGINGMODE.l(t,n,n1));",
        1,
    )
    fixed_lp_solve = fixed_lp_solve.replace(
        "PURCHASEBLOCKBINARY.up(t,bd,blk) = pyspd_PURCHASEBLOCKBINARY_up(t,bd,blk);",
        "PURCHASEBLOCKBINARY.up(t,bd,blk) = pyspd_PURCHASEBLOCKBINARY_up(t,bd,blk);\n"
        "BATTERYCHARGINGMODE.lo(t,n,n1) = pyspd_BATTERYCHARGINGMODE_lo(t,n,n1);\n"
        "BATTERYCHARGINGMODE.up(t,n,n1) = pyspd_BATTERYCHARGINGMODE_up(t,n,n1);",
        1,
    )
    matrix_export = matrix_export.replace(
        "PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));",
        "PURCHASEBLOCKBINARY.fx(t,bd,blk) = round(PURCHASEBLOCKBINARY.l(t,bd,blk));\n"
        "BATTERYCHARGINGMODE.fx(t,n,n1) = round(BATTERYCHARGINGMODE.l(t,n,n1));",
    )
    matrix_export = matrix_export.replace(
        "HVDCSENTINSEGMENT, PURCHASEBLOCKBINARY, HVDCSENDZERO,",
        "HVDCSENTINSEGMENT, PURCHASEBLOCKBINARY, BATTERYCHARGINGMODE, HVDCSENDZERO,",
    )
    return declarations, fixed_lp_solve, matrix_export


class ListingParseError(ValueError):
    """Raised when a GAMS listing does not contain the required solve evidence."""


class SourcePatchError(ValueError):
    """Raised when pinned source text differs from the expected overlay target."""


class VspdRunError(RuntimeError):
    """Raised when staged vSPD execution fails."""


class PriceReportError(ValueError):
    """Raised when a vSPD price report is structurally or numerically invalid."""


@dataclass(frozen=True)
class SolveRecord:
    scenario: str
    model: str
    solve_type: str
    solver: str
    solver_status_code: int
    solver_status: str
    model_status_code: int
    model_status: str
    objective: float
    resource_usage_seconds: float | None = None

    @property
    def optimal(self) -> bool:
        return self.solver_status_code == 1 and self.model_status_code == 1


@dataclass(frozen=True)
class ListingResult:
    records: tuple[SolveRecord, ...]

    @property
    def operational_records(self) -> tuple[SolveRecord, ...]:
        """Return optimization records, excluding non-solving Convert exports."""
        return tuple(record for record in self.records if record.solver != "CONVERT")

    @property
    def primary(self) -> tuple[SolveRecord, ...]:
        return tuple(
            record
            for record in self.operational_records
            if record.model == PRIMARY_MODEL and record.solve_type == "MIP"
        )

    @property
    def cleanup(self) -> tuple[SolveRecord, ...]:
        return tuple(
            record
            for record in self.operational_records
            if record.model == CLEANUP_MODEL and record.solve_type == "MIP"
        )

    @property
    def pricing(self) -> tuple[SolveRecord, ...]:
        return tuple(
            record for record in self.operational_records if record.solve_type == "RMIP"
        )

    @property
    def exports(self) -> tuple[SolveRecord, ...]:
        return tuple(record for record in self.records if record.solver == "CONVERT")

    @property
    def all_optimal(self) -> bool:
        return bool(self.operational_records) and all(
            record.optimal for record in self.operational_records
        )

    def matches_profile(self, profile: NativeGamsProfile) -> bool:
        if not self.all_optimal or not self.primary:
            return False
        if any(record.solver != profile.mip_solver.upper() for record in self.primary):
            return False
        if profile.explicit_fixed_lp_pricing:
            if [record.scenario for record in self.pricing] != [
                record.scenario for record in self.primary
            ]:
                return False
            if any(
                record.solver != profile.lp_solver.upper() for record in self.pricing
            ):
                return False
            expected_exports = (
                len(self.operational_records) + 1
                if profile.capture_state_evidence
                else 1
            )
            return len(self.exports) == expected_exports
        return True


class VspdListingParser:
    """Extract scenario-aware solve records from a GAMS vSPD listing."""

    _loop = re.compile(r"^LOOPS\s+drs\s+(?P<scenario>[^\n]+)$", re.MULTILINE)
    _report = re.compile(
        r"Solution Report\s+SOLVE\s+(?P<model>\S+)\s+Using\s+"
        r"(?P<solve_type>\S+).*?"
        r"\bSOLVER\s+(?P<solver>\S+).*?"
        r"\*\*\*\* SOLVER STATUS\s+(?P<solver_code>\d+)\s+"
        r"(?P<solver_status>[^\n]+).*?"
        r"\*\*\*\* MODEL STATUS\s+(?P<model_code>\d+)\s+"
        r"(?P<model_status>[^\n]+).*?"
        r"\*\*\*\* OBJECTIVE VALUE\s+(?P<objective>[-+0-9.Ee]+)",
        re.DOTALL,
    )
    _resource_usage = re.compile(r"RESOURCE USAGE, LIMIT\s+(?P<seconds>[-+0-9.Ee]+)")

    def parse_file(self, path: Path) -> ListingResult:
        return self.parse_text(path.read_text(errors="replace"))

    def parse_text(self, text: str) -> ListingResult:
        loops = tuple(self._loop.finditer(text))
        reports = tuple(self._report.finditer(text))
        records: list[SolveRecord] = []
        for index, report in enumerate(reports):
            preceding = [loop for loop in loops if loop.start() < report.start()]
            scenario = preceding[-1].group("scenario").strip() if preceding else "base"
            next_report_start = (
                reports[index + 1].start() if index + 1 < len(reports) else len(text)
            )
            resource = self._resource_usage.search(
                text, report.end(), next_report_start
            )
            records.append(
                SolveRecord(
                    scenario=scenario,
                    model=report.group("model"),
                    solve_type=report.group("solve_type"),
                    solver=report.group("solver").upper(),
                    solver_status_code=int(report.group("solver_code")),
                    solver_status=report.group("solver_status").strip(),
                    model_status_code=int(report.group("model_code")),
                    model_status=report.group("model_status").strip(),
                    objective=float(report.group("objective")),
                    resource_usage_seconds=(
                        float(resource.group("seconds"))
                        if resource is not None
                        else None
                    ),
                )
            )
        if not records:
            raise ListingParseError("no GAMS solution reports found in listing")
        return ListingResult(records=tuple(records))


@dataclass(frozen=True)
class NodePriceRecord:
    date_time: str
    scenario: str
    node: str
    price: float


@dataclass(frozen=True)
class DpsNodePriceReport:
    records: tuple[NodePriceRecord, ...]

    @property
    def scenario_count(self) -> int:
        return len({record.scenario for record in self.records})

    @property
    def node_count(self) -> int:
        return len({record.node for record in self.records})

    @property
    def minimum_price(self) -> float:
        return min(record.price for record in self.records)

    @property
    def maximum_price(self) -> float:
        return max(record.price for record in self.records)


class DpsNodePriceParser:
    """Parse the vSPD DPS node-price CSV without accepting GAMS special values."""

    _header = ("DateTime", "Scenario", "Node", "Price")

    def parse_file(self, path: Path) -> DpsNodePriceReport:
        return self.parse_text(path.read_text())

    def parse_text(self, text: str) -> DpsNodePriceReport:
        rows = csv.reader(io.StringIO(text))
        header = next(rows, None)
        if header is None or tuple(header) != self._header:
            raise PriceReportError(
                f"unexpected DPS node-price header: {header!r} != {self._header!r}"
            )
        records: list[NodePriceRecord] = []
        keys: set[tuple[str, str, str]] = set()
        for line_number, row in enumerate(rows, start=2):
            if len(row) != 4:
                raise PriceReportError(
                    f"node-price row {line_number} has {len(row)} fields, expected 4"
                )
            key = (row[0], row[1], row[2])
            if key in keys:
                raise PriceReportError(
                    f"duplicate node-price key at row {line_number}: {key!r}"
                )
            keys.add(key)
            try:
                price = float(row[3])
            except ValueError as error:
                raise PriceReportError(
                    f"non-finite or invalid node price at row {line_number}: {row[3]!r}"
                ) from error
            if not math.isfinite(price):
                raise PriceReportError(
                    f"non-finite node price at row {line_number}: {row[3]!r}"
                )
            records.append(
                NodePriceRecord(
                    date_time=row[0],
                    scenario=row[1],
                    node=row[2],
                    price=price,
                )
            )
        if not records:
            raise PriceReportError("DPS node-price report is empty")
        return DpsNodePriceReport(records=tuple(records))


@dataclass(frozen=True)
class PublishedEnergyPriceRecord:
    date_time: str
    trading_period: str
    node: str
    price: float


@dataclass(frozen=True)
class PublishedEnergyPriceReport:
    records: tuple[PublishedEnergyPriceRecord, ...]


class PublishedEnergyPriceParser:
    """Parse normal/AUD published energy prices at native report precision."""

    _header = (
        "DateTime",
        "TradingPeriod",
        "Pnodename",
        "vSPDDollarsPerMegawattHour",
    )

    def parse_file(self, path: Path) -> PublishedEnergyPriceReport:
        return self.parse_text(path.read_text())

    def parse_text(self, text: str) -> PublishedEnergyPriceReport:
        rows = csv.reader(io.StringIO(text))
        header = next(rows, None)
        if header is None or tuple(header) != self._header:
            raise PriceReportError(
                f"unexpected published energy-price header: {header!r}"
            )
        records: list[PublishedEnergyPriceRecord] = []
        keys: set[tuple[str, str, str]] = set()
        for line_number, row in enumerate(rows, start=2):
            if len(row) != 4:
                raise PriceReportError(
                    f"published energy-price row {line_number} has {len(row)} fields"
                )
            key = (row[0], row[1], row[2])
            if key in keys:
                raise PriceReportError(
                    f"duplicate published energy-price key at row {line_number}: {key!r}"
                )
            keys.add(key)
            try:
                price = float(row[3])
            except ValueError as error:
                raise PriceReportError(
                    f"non-finite or invalid published energy price at row "
                    f"{line_number}: {row[3]!r}"
                ) from error
            if not math.isfinite(price):
                raise PriceReportError(
                    f"non-finite published energy price at row {line_number}: "
                    f"{row[3]!r}"
                )
            records.append(PublishedEnergyPriceRecord(*key, price))
        if not records:
            raise PriceReportError("published energy-price report is empty")
        return PublishedEnergyPriceReport(tuple(records))


@dataclass(frozen=True)
class BaselineObjective:
    scenario: str
    value: float


@dataclass(frozen=True)
class ObjectiveBaseline:
    case: str
    source: dict[str, Any]
    objectives: tuple[BaselineObjective, ...]

    @classmethod
    def load(cls, path: Path) -> ObjectiveBaseline:
        payload = json.loads(path.read_text())
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported objective baseline schema_version")
        objectives = tuple(
            BaselineObjective(
                scenario=str(item["scenario"]),
                value=float(item["value"]),
            )
            for item in payload.get("objectives", [])
        )
        if not objectives:
            raise ValueError("objective baseline is empty")
        scenarios = [objective.scenario for objective in objectives]
        if len(set(scenarios)) != len(scenarios):
            raise ValueError("objective baseline contains duplicate scenarios")
        return cls(
            case=str(payload["case"]),
            source=dict(payload.get("source", {})),
            objectives=objectives,
        )


@dataclass(frozen=True)
class ObjectiveDelta:
    scenario: str
    expected: float
    actual: float
    absolute_delta: float
    relative_delta: float
    passed: bool


@dataclass(frozen=True)
class BaselineComparison:
    deltas: tuple[ObjectiveDelta, ...]
    absolute_tolerance: float
    relative_tolerance: float

    @classmethod
    def compare(
        cls,
        actual: Sequence[SolveRecord],
        expected: ObjectiveBaseline,
        absolute_tolerance: float = 0.01,
        relative_tolerance: float = 1e-9,
    ) -> BaselineComparison:
        actual_scenarios = [record.scenario for record in actual]
        expected_scenarios = [item.scenario for item in expected.objectives]
        if actual_scenarios != expected_scenarios:
            raise ValueError(
                "actual scenario sequence does not match objective baseline: "
                f"{actual_scenarios!r} != {expected_scenarios!r}"
            )
        deltas = []
        for record, target in zip(actual, expected.objectives, strict=True):
            absolute_delta = abs(record.objective - target.value)
            relative_delta = absolute_delta / abs(target.value) if target.value else 0.0
            threshold = absolute_tolerance + relative_tolerance * abs(target.value)
            deltas.append(
                ObjectiveDelta(
                    scenario=record.scenario,
                    expected=target.value,
                    actual=record.objective,
                    absolute_delta=absolute_delta,
                    relative_delta=relative_delta,
                    passed=record.optimal and absolute_delta <= threshold,
                )
            )
        return cls(
            deltas=tuple(deltas),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )

    @property
    def passed(self) -> bool:
        return bool(self.deltas) and all(delta.passed for delta in self.deltas)

    @property
    def max_absolute_delta(self) -> float:
        return max(delta.absolute_delta for delta in self.deltas)

    @property
    def max_relative_delta(self) -> float:
        return max(delta.relative_delta for delta in self.deltas)

    @property
    def worst_scenario(self) -> str:
        return max(self.deltas, key=lambda delta: delta.absolute_delta).scenario

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "max_absolute_delta": self.max_absolute_delta,
            "max_relative_delta": self.max_relative_delta,
            "worst_scenario": self.worst_scenario,
            "deltas": [asdict(delta) for delta in self.deltas],
        }


@dataclass(frozen=True)
class InstrumentationNeutralityComparison:
    """Fail-closed equivalence proof for instrumented and control runs."""

    checks: dict[str, bool]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(self.checks.values())

    @classmethod
    def compare(
        cls,
        instrumented: dict[str, Any],
        control: dict[str, Any],
    ) -> InstrumentationNeutralityComparison:
        def value(payload: dict[str, Any], *path: str) -> Any:
            current: Any = payload
            try:
                for key in path:
                    current = current[key]
            except (KeyError, TypeError):
                return object()
            return current

        def same_price_report(name: str) -> bool:
            left = value(instrumented, name)
            right = value(control, name)
            if left is None and right is None:
                return True
            return (
                isinstance(left, dict)
                and isinstance(right, dict)
                and left.get("logical_records_sha256")
                == right.get("logical_records_sha256")
                and left.get("logical_records_sha256") is not None
            )

        def operational_records(payload: dict[str, Any]) -> Any:
            records = value(payload, "records")
            if not isinstance(records, list):
                return object()
            return [
                record
                for record in records
                if isinstance(record, dict) and record.get("solver") != "CONVERT"
            ]

        instrumented_state = value(instrumented, "state_evidence")
        checks = {
            "same_input": value(instrumented, "input", "sha256")
            == value(control, "input", "sha256"),
            "same_configuration": value(
                instrumented, "configuration_overlay", "logical_sha256"
            )
            == value(control, "configuration_overlay", "logical_sha256"),
            "same_solve_records": operational_records(instrumented)
            == operational_records(control),
            "same_reports": value(instrumented, "reports", "logical_sha256")
            == value(control, "reports", "logical_sha256"),
            "same_published_prices": same_price_report("published_energy_prices"),
            "same_dps_prices": same_price_report("node_prices"),
            "same_pricing_solution": value(
                instrumented,
                "canonical",
                "manifests",
                "pricing_solution",
                "logical_sha256",
            )
            == value(
                control,
                "canonical",
                "manifests",
                "pricing_solution",
                "logical_sha256",
            ),
            "same_pricing_matrix_gdx": value(
                instrumented,
                "canonical",
                "manifests",
                "pricing_matrix",
                "logical_sha256",
            )
            == value(
                control,
                "canonical",
                "manifests",
                "pricing_matrix",
                "logical_sha256",
            ),
            "same_pricing_dictionary": value(
                instrumented,
                "canonical",
                "manifests",
                "pricing_dictionary",
                "logical_sha256",
            )
            == value(
                control,
                "canonical",
                "manifests",
                "pricing_dictionary",
                "logical_sha256",
            ),
            "same_matrix_semantics": value(
                instrumented,
                "canonical",
                "matrix_evidence",
                "semantic_logical_sha256",
            )
            == value(
                control,
                "canonical",
                "matrix_evidence",
                "semantic_logical_sha256",
            ),
            "same_price_validation": value(
                instrumented, "canonical", "price_validation"
            )
            == value(control, "canonical", "price_validation"),
            "same_validation_outcomes": value(instrumented, "validation")
            == value(control, "validation"),
            "instrumented_state_present": isinstance(instrumented_state, dict)
            and int(instrumented_state.get("solve_pair_count", 0)) > 0,
            "control_state_absent": value(control, "state_evidence") is None,
        }
        return cls(checks)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks}


@dataclass(frozen=True)
class NativeGamsProfile:
    name: str
    mip_solver: str
    lp_solver: str
    use_option_files: bool
    normative: bool
    supports_marginals: bool
    explicit_fixed_lp_pricing: bool
    capture_state_evidence: bool
    lp_options: tuple[str, ...]


class CplexOracleProfile(NativeGamsProfile):
    def __init__(self) -> None:
        super().__init__(
            name="gams-cplex-oracle",
            mip_solver="Cplex",
            lp_solver="Cplex",
            use_option_files=True,
            normative=True,
            supports_marginals=True,
            explicit_fixed_lp_pricing=False,
            capture_state_evidence=False,
            lp_options=(),
        )


class ScipSmokeProfile(NativeGamsProfile):
    def __init__(self) -> None:
        super().__init__(
            name="gams-scip-smoke",
            mip_solver="SCIP",
            lp_solver="HiGHS",
            use_option_files=False,
            normative=False,
            supports_marginals=False,
            explicit_fixed_lp_pricing=False,
            capture_state_evidence=False,
            lp_options=(),
        )


class ScipHighsPricingProfile(NativeGamsProfile):
    """SCIP primary MIP followed by an explicit HiGHS fixed-discrete RMIP."""

    def __init__(self, capture_state_evidence: bool = True) -> None:
        super().__init__(
            name="gams-scip-highs-pricing",
            mip_solver="SCIP",
            lp_solver="HiGHS",
            use_option_files=True,
            normative=True,
            supports_marginals=True,
            explicit_fixed_lp_pricing=True,
            capture_state_evidence=capture_state_evidence,
            lp_options=(
                "dual_feasibility_tolerance = 1e-9",
                "primal_feasibility_tolerance = 1e-9",
                "dual_residual_tolerance = 1e-9",
                "primal_residual_tolerance = 1e-9",
            ),
        )


class ScipHighsPrimalBasisProfile(NativeGamsProfile):
    """Non-normative primal-simplex/no-presolve basis perturbation profile."""

    def __init__(self) -> None:
        super().__init__(
            name="gams-scip-highs-primal-basis-perturbation",
            mip_solver="SCIP",
            lp_solver="HiGHS",
            use_option_files=True,
            normative=False,
            supports_marginals=True,
            explicit_fixed_lp_pricing=True,
            capture_state_evidence=False,
            lp_options=(
                "dual_feasibility_tolerance = 1e-9",
                "primal_feasibility_tolerance = 1e-9",
                "dual_residual_tolerance = 1e-9",
                "primal_residual_tolerance = 1e-9",
                "solver = simplex",
                "simplex_strategy = 4",
                "presolve = off",
            ),
        )


@dataclass(frozen=True)
class VspdRunConfiguration:
    """Explicit, hash-addressed selection of the supported reference run mode."""

    run_name: str
    operation_mode: str
    daily_mode: int | None = None
    case_ids: tuple[str, ...] = ()

    _safe_name: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+$")
    _supported_modes: ClassVar[set[str]] = {"SPD", "AUD", "DPS"}

    def __post_init__(self) -> None:
        if not self._safe_name.fullmatch(self.run_name):
            raise ValueError(f"unsafe vSPD run name: {self.run_name!r}")
        if self.operation_mode not in self._supported_modes:
            raise ValueError(
                f"unsupported vSPD operation mode: {self.operation_mode!r}"
            )
        if self.daily_mode not in {None, 0, 1}:
            raise ValueError("daily_mode must be 0, 1, or None")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("case_ids must be unique")
        if any(not self._safe_name.fullmatch(case_id) for case_id in self.case_ids):
            raise ValueError("case_ids contain an unsafe identifier")

    @property
    def logical_sha256(self) -> str:
        return _logical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_name": self.run_name,
            "operation_mode": self.operation_mode,
            "daily_mode": self.daily_mode,
            "case_ids": list(self.case_ids),
            "source_patches": (
                ["vspd-v5.0.6-audit-o-bus-alias-v1"]
                if self.operation_mode == "AUD"
                else []
            ),
        }


class VspdSourcePatcher:
    """Apply a minimal solver overlay and reject unexpected source revisions."""

    def apply(
        self,
        programs: Path,
        profile: NativeGamsProfile,
        configuration: VspdRunConfiguration | None = None,
    ) -> None:
        settings = programs / "vSPDsettings.inc"
        solve = programs / "vSPDsolve.gms"
        if configuration is not None:
            self._replace_global_setting(settings, "runName", configuration.run_name)
            self._replace_global_setting(
                settings,
                "opMode",
                configuration.operation_mode,
            )
            if configuration.operation_mode == "AUD":
                self._replace_exact(
                    programs / "vSPDreport.gms",
                    "o_bus(ca,dt,b)",
                    "bus(ca,dt,b)",
                    expected_count=1,
                )
            if configuration.daily_mode is not None:
                self._replace_exact(
                    settings,
                    "Scalar dailymode                         / 1 / ;",
                    "Scalar dailymode                         "
                    f"/ {configuration.daily_mode} / ;",
                    expected_count=1,
                )
            if configuration.case_ids:
                (programs / "vSPDtpsToSolve.inc").write_text(
                    "/ " + ", ".join(configuration.case_ids) + " /\n"
                )
        if profile.mip_solver != "Cplex":
            self._replace_exact(
                settings,
                "$setglobal Solver                          Cplex",
                f"$setglobal Solver                          {profile.mip_solver}",
                expected_count=1,
            )
        if profile.lp_solver != profile.mip_solver:
            self._replace_exact(
                solve,
                "option lp = %Solver% ;",
                f"option lp = {profile.lp_solver} ;",
                expected_count=1,
            )
        if not profile.use_option_files:
            self._replace_exact(
                solve,
                ".Optfile = 1 ;",
                ".Optfile = 0 ;",
                expected_count=3,
            )
        if profile.explicit_fixed_lp_pricing:
            self._apply_fixed_lp_pricing(
                programs,
                solve,
                profile.mip_solver,
                profile.lp_solver,
                profile.capture_state_evidence,
                profile.lp_options,
            )

    def _apply_fixed_lp_pricing(
        self,
        programs: Path,
        solve: Path,
        mip_solver: str,
        pricing_solver: str,
        capture_state_evidence: bool,
        lp_options: tuple[str, ...],
    ) -> None:
        period = programs / "vSPDperiod.gms"
        self._replace_exact(
            solve,
            "option mip = %Solver% ;",
            f"option mip = %Solver% ;\n"
            f"option rmip = {pricing_solver} ;\n"
            f"$setglobal pyspdPricingSolver {pricing_solver}",
            expected_count=1,
        )
        self._replace_exact(
            solve,
            "\nScalars\n  modelSolved",
            "\n$include pyspd_pricing_declarations.inc\n\nScalars\n  modelSolved",
            expected_count=1,
        )
        nmir_solve = (
            "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
            "$setglobal pyspdPricingModel vSPD_NMIR\n"
            "$include pyspd_fixed_lp_solve.inc"
        )
        branch_solve = (
            "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;\n"
            "$setglobal pyspdPricingModel vSPD_BranchFlowMIP\n"
            "$include pyspd_fixed_lp_solve.inc"
        )
        if capture_state_evidence:
            nmir_solve = (
                "\n$setglobal pyspdSolveModel vSPD_NMIR\n"
                "$setglobal pyspdSolveType MIP\n"
                "$setglobal pyspdSolveSolver %Solver%\n"
                "$include pyspd_pre_solve_snapshot.inc\n"
                "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
                "$include pyspd_post_solve_snapshot.inc\n"
                "$setglobal pyspdPricingModel vSPD_NMIR\n"
                "$include pyspd_fixed_lp_solve.inc"
            )
            branch_solve = (
                "\n$setglobal pyspdSolveModel vSPD_BranchFlowMIP\n"
                "$setglobal pyspdSolveType MIP\n"
                "$setglobal pyspdSolveSolver %Solver%\n"
                "$include pyspd_pre_solve_snapshot.inc\n"
                "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;\n"
                "$include pyspd_post_solve_snapshot.inc\n"
                "$setglobal pyspdPricingModel vSPD_BranchFlowMIP\n"
                "$include pyspd_fixed_lp_solve.inc"
            )
        self._replace_exact(
            solve,
            "solve vSPD_NMIR using mip maximizing NETBENEFIT ;",
            nmir_solve,
            expected_count=2,
        )
        self._replace_exact(
            solve,
            "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;",
            branch_solve,
            expected_count=1,
        )
        period_unload = (
            "execute_unload '%programPath%/vSPDperiod.gdx'\n"
            "  sca    = i_caseID\n"
            "  stp    = i_tradePeriod\n"
            "  sdt    = i_dateTime\n"
            "  scase2dt2tp  = i_DateTimeTradePeriod\n"
            "  ;"
        )
        if capture_state_evidence:
            self._replace_exact(
                period,
                period_unload,
                period_unload
                + "\nexecute_unload 'pyspd_checkpoint_period_selection.gdx'\n"
                "  sca    = i_caseID\n"
                "  stp    = i_tradePeriod\n"
                "  sdt    = i_dateTime\n"
                "  scase2dt2tp  = i_DateTimeTradePeriod\n"
                "  ;",
                expected_count=1,
            )
            section_3 = "* 3. Manage model and data compatability"
            self._replace_exact(
                solve,
                section_3,
                "$onImplicitAssign\n"
                "execute_unload 'pyspd_checkpoint_01_loaded.gdx';\n"
                "$offImplicitAssign\n\n" + section_3,
                expected_count=1,
            )
            section_7 = "* 7. The vSPD solve loop"
            self._replace_exact(
                solve,
                section_7,
                "$onImplicitAssign\n"
                "execute_unload 'pyspd_checkpoint_02_preprocessed.gdx';\n"
                "$offImplicitAssign\n\n" + section_7,
                expected_count=1,
            )
        self._replace_exact(
            solve,
            "* 9. Write results to CSV report files and GDX files",
            "$include pyspd_matrix_export.inc\n\n"
            "* 9. Write results to CSV report files and GDX files",
            expected_count=1,
        )
        declarations = _PRICING_DECLARATIONS
        fixed_lp_solve = _FIXED_LP_SOLVE
        matrix_export = _MATRIX_EXPORT
        if "BATTERYCHARGINGMODE" in solve.read_text():
            declarations, fixed_lp_solve, matrix_export = _add_v16_battery_discrete(
                declarations, fixed_lp_solve, matrix_export
            )
        (programs / "pyspd_pricing_declarations.inc").write_text(declarations)
        if not capture_state_evidence:
            fixed_lp_solve = fixed_lp_solve.replace(
                "$setglobal pyspdSolveModel %pyspdPricingModel%\n"
                "$setglobal pyspdSolveType RMIP\n"
                "$setglobal pyspdSolveSolver %pyspdPricingSolver%\n"
                "$include pyspd_pre_solve_snapshot.inc\n",
                "",
            ).replace("$include pyspd_post_solve_snapshot.inc\n", "")
        (programs / "pyspd_fixed_lp_solve.inc").write_text(fixed_lp_solve)
        (programs / "pyspd_matrix_export.inc").write_text(matrix_export)
        if capture_state_evidence:
            (programs / "pyspd_pre_solve_snapshot.inc").write_text(_PRE_SOLVE_SNAPSHOT)
            (programs / "pyspd_post_solve_snapshot.inc").write_text(
                _POST_SOLVE_SNAPSHOT
            )
        (programs / "convert.opt").write_text(_CONVERT_OPTIONS)
        if mip_solver == "SCIP":
            (programs / "scip.opt").write_text("numerics/feastol = 1e-7\n")
        if pricing_solver == "HiGHS":
            (programs / "highs.opt").write_text("\n".join(lp_options) + "\n")

    @staticmethod
    def _replace_global_setting(path: Path, name: str, value: str) -> None:
        text = path.read_text()
        pattern = re.compile(
            rf"^\$setglobal\s+{re.escape(name)}\s+(?P<value>\S+)",
            re.MULTILINE,
        )
        matches = tuple(pattern.finditer(text))
        if len(matches) != 1:
            raise SourcePatchError(
                f"{path} contained {len(matches)} settings named {name!r}; "
                "expected exactly one"
            )
        match = matches[0]
        start, end = match.span("value")
        path.write_text(text[:start] + value + text[end:])

    @staticmethod
    def _replace_exact(
        path: Path,
        old: str,
        new: str,
        expected_count: int,
    ) -> None:
        text = path.read_text()
        count = text.count(old)
        if count != expected_count:
            raise SourcePatchError(
                f"{path} contained {count} occurrences of {old!r}; "
                f"expected exactly {expected_count}"
            )
        path.write_text(text.replace(old, new))


@dataclass(frozen=True)
class VspdCase:
    source_tree: Path
    input_gdx: Path
    work_directory: Path
    gams_executable: Path
    profile: NativeGamsProfile
    configuration: VspdRunConfiguration | None = None

    @property
    def case_name(self) -> str:
        return self.input_gdx.stem


@dataclass(frozen=True)
class VspdRunResult:
    stage_directory: Path
    listing: Path
    evidence: Path
    parsed: ListingResult
    comparison: BaselineComparison | None
    node_prices: DpsNodePriceReport | None
    published_energy_prices: PublishedEnergyPriceReport | None
    matrix_validation: LinearMatrixValidation | None
    price_validation: IndependentPriceValidation | None
    report_inventory: ReportInventory
    state_evidence: StateEvidenceInventory | None

    @property
    def qualified(self) -> bool:
        checks = [
            self.parsed.all_optimal,
            self.comparison is None or self.comparison.passed,
            self.matrix_validation is None or self.matrix_validation.passed,
            self.price_validation is None or self.price_validation.passed,
        ]
        return all(checks)


@dataclass(frozen=True)
class ReportArtifact:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SolveStatePair:
    ordinal: int
    scenario: str
    model: str
    solve_type: str
    solver: str
    pre: ReportArtifact
    post: ReportArtifact
    matrix: ReportArtifact
    dictionary: ReportArtifact


@dataclass(frozen=True)
class StateEvidenceInventory:
    """Hash-bound preprocessing checkpoints and solve-state pairs."""

    checkpoints: tuple[ReportArtifact, ...]
    solve_pairs: tuple[SolveStatePair, ...]
    logical_sha256: str

    _checkpoint_names: ClassVar[tuple[str, ...]] = (
        "pyspd_checkpoint_period_selection.gdx",
        "pyspd_checkpoint_01_loaded.gdx",
        "pyspd_checkpoint_02_preprocessed.gdx",
    )
    _snapshot_name: ClassVar[re.Pattern[str]] = re.compile(
        r"^pyspd_solve_(?P<ordinal>[1-9][0-9]*)_"
        r"(?P<phase>pre|post|matrix|dict)\.gdx$"
    )

    @classmethod
    def build(
        cls,
        programs: Path,
        parsed: ListingResult,
    ) -> StateEvidenceInventory:
        checkpoints = tuple(
            cls._artifact(programs / name, programs) for name in cls._checkpoint_names
        )
        observed: dict[tuple[int, str], ReportArtifact] = {}
        for path in programs.glob("pyspd_solve_*.gdx"):
            match = cls._snapshot_name.fullmatch(path.name)
            if match is None:
                raise ValueError(f"unexpected solve-state snapshot name: {path.name}")
            key = (int(match.group("ordinal")), match.group("phase"))
            if key in observed:
                raise ValueError(f"duplicate solve-state snapshot: {path.name}")
            observed[key] = cls._artifact(path, programs)

        records = parsed.operational_records
        expected_keys = {
            (ordinal, phase)
            for ordinal in range(1, len(records) + 1)
            for phase in ("pre", "post", "matrix", "dict")
        }
        if set(observed) != expected_keys:
            raise ValueError(
                "solve-state evidence must contain one complete pre/post pair "
                f"for every operational solve; expected {sorted(expected_keys)!r}, "
                f"observed {sorted(observed)!r}"
            )
        pairs = tuple(
            SolveStatePair(
                ordinal=ordinal,
                scenario=record.scenario,
                model=record.model,
                solve_type=record.solve_type,
                solver=record.solver,
                pre=observed[(ordinal, "pre")],
                post=observed[(ordinal, "post")],
                matrix=observed[(ordinal, "matrix")],
                dictionary=observed[(ordinal, "dict")],
            )
            for ordinal, record in enumerate(records, start=1)
        )
        payload = {
            "checkpoints": [asdict(artifact) for artifact in checkpoints],
            "solve_pairs": [asdict(pair) for pair in pairs],
        }
        return cls(
            checkpoints=checkpoints,
            solve_pairs=pairs,
            logical_sha256=_logical_sha256(payload),
        )

    @staticmethod
    def _artifact(path: Path, programs: Path) -> ReportArtifact:
        if not path.is_file():
            raise ValueError(f"state evidence artifact is missing: {path}")
        return ReportArtifact(
            path=path.relative_to(programs).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=_sha256(path),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_count": len(self.checkpoints),
            "solve_pair_count": len(self.solve_pairs),
            "logical_sha256": self.logical_sha256,
            "checkpoints": [asdict(artifact) for artifact in self.checkpoints],
            "solve_pairs": [asdict(pair) for pair in self.solve_pairs],
        }


@dataclass(frozen=True)
class ReportInventory:
    artifacts: tuple[ReportArtifact, ...]
    logical_sha256: str

    @classmethod
    def build(cls, output_directory: Path) -> ReportInventory:
        if not output_directory.is_dir():
            raise VspdRunError(f"report directory is missing: {output_directory}")
        artifacts = tuple(
            ReportArtifact(
                path=path.relative_to(output_directory).as_posix(),
                size_bytes=path.stat().st_size,
                sha256=_sha256(path),
            )
            for path in sorted(
                (
                    candidate
                    for candidate in output_directory.rglob("*")
                    if candidate.is_file()
                ),
                key=lambda candidate: candidate.relative_to(
                    output_directory
                ).as_posix(),
            )
        )
        if not artifacts:
            raise VspdRunError(f"no report artifacts found in: {output_directory}")
        return cls(
            artifacts=artifacts,
            logical_sha256=_logical_sha256(
                [asdict(artifact) for artifact in artifacts]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_count": len(self.artifacts),
            "logical_sha256": self.logical_sha256,
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
        }


class VspdRunner:
    """Stage, execute, parse, and evidence one vSPD case."""

    _safe_name = re.compile(r"^[A-Za-z0-9_.-]+$")
    _setting = re.compile(
        r"^\$setglobal\s+(?P<name>runName|opMode)\s+(?P<value>\S+)",
        re.MULTILINE,
    )

    def __init__(
        self,
        parser: VspdListingParser | None = None,
        patcher: VspdSourcePatcher | None = None,
        price_parser: DpsNodePriceParser | None = None,
        published_price_parser: PublishedEnergyPriceParser | None = None,
    ) -> None:
        self.parser = parser or VspdListingParser()
        self.patcher = patcher or VspdSourcePatcher()
        self.price_parser = price_parser or DpsNodePriceParser()
        self.published_price_parser = (
            published_price_parser or PublishedEnergyPriceParser()
        )

    def run(
        self,
        case: VspdCase,
        baseline: ObjectiveBaseline | None = None,
        absolute_tolerance: float = 0.01,
        relative_tolerance: float = 1e-9,
    ) -> VspdRunResult:
        run_started = time.perf_counter()
        self._validate(case)
        stage = case.work_directory / "vspd"
        if stage.exists():
            raise VspdRunError(
                f"refusing to overwrite existing stage directory: {stage}"
            )
        case.work_directory.mkdir(parents=True, exist_ok=True)
        staging_started = time.perf_counter()
        self._stage_source_tree(case.source_tree, stage)

        programs = stage / "Programs"
        staged_input = stage / "Input" / case.input_gdx.name
        staged_input.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(case.input_gdx, staged_input)
        self.patcher.apply(programs, case.profile, case.configuration)
        (programs / "vSPDcase.inc").write_text(
            f"$setglobal  GDXname  {case.case_name}\n"
        )
        staging_seconds = time.perf_counter() - staging_started

        settings = self._read_settings(programs / "vSPDsettings.inc")
        run_name = settings["runName"]
        operation_mode = settings["opMode"]
        output = stage / "Output" / run_name
        (output / "Programs" / "Demand").mkdir(parents=True, exist_ok=True)
        (programs / "lst").mkdir(parents=True, exist_ok=True)

        commands = [
            ("model", ["vSPDmodel.gms", "s=vSPDmodel", "lo=3"]),
            ("report-setup", [self._report_setup(operation_mode), "lo=3"]),
            ("period", ["vSPDperiod.gms", "lo=3"]),
            (
                "solve",
                [
                    "vSPDsolve.gms",
                    "r=vSPDmodel",
                    "lo=3",
                    "ide=1",
                    "Errmsg=1",
                    "holdFixed=0",
                ],
            ),
        ]
        logs = case.work_directory / "logs"
        logs.mkdir()
        command_seconds: dict[str, float] = {}
        for name, arguments in commands:
            command_seconds[name] = self._execute(
                case.gams_executable, programs, arguments, logs / f"{name}.log"
            )

        validation_started = time.perf_counter()
        listing = programs / "vSPDsolve.lst"
        parsed = self.parser.parse_file(listing)
        node_price_path = output / f"{run_name}_NodePriceSensitivity.csv"
        node_prices = (
            self.price_parser.parse_file(node_price_path)
            if operation_mode == "DPS" and case.profile.supports_marginals
            else None
        )
        published_price_path = output / f"{run_name}_PublishedEnergyPrices_TP.csv"
        published_energy_prices = (
            self.published_price_parser.parse_file(published_price_path)
            if operation_mode in {"SPD", "AUD"} and case.profile.supports_marginals
            else None
        )
        comparison = (
            BaselineComparison.compare(
                actual=parsed.primary,
                expected=baseline,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            if baseline is not None
            else None
        )
        report_inventory = ReportInventory.build(output)
        state_evidence = (
            StateEvidenceInventory.build(programs, parsed)
            if case.profile.capture_state_evidence
            else None
        )
        matrix_validation: LinearMatrixValidation | None = None
        price_validation: IndependentPriceValidation | None = None
        canonical_payload: dict[str, Any] | None = None
        canonical_seconds = 0.0
        if case.profile.explicit_fixed_lp_pricing:
            canonical_started = time.perf_counter()
            canonical_payload, matrix_validation, price_validation = (
                self._canonical_evidence(
                    case,
                    programs,
                    node_prices,
                    published_energy_prices,
                    state_evidence,
                )
            )
            canonical_seconds = time.perf_counter() - canonical_started
        validation_seconds = time.perf_counter() - validation_started
        performance = {
            "clock": "time.perf_counter",
            "staging_seconds": staging_seconds,
            "gams_command_seconds": command_seconds,
            "gams_total_seconds": sum(command_seconds.values()),
            "validation_and_evidence_seconds": validation_seconds,
            "canonical_validation_seconds": canonical_seconds,
            "total_seconds_before_evidence_write": time.perf_counter() - run_started,
            "peak_child_rss_bytes": _peak_child_rss_bytes(),
            "hardware": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "logical_cpu_count": os.cpu_count(),
                "python": platform.python_version(),
            },
        }
        evidence = case.work_directory / "evidence.json"
        evidence.write_text(
            json.dumps(
                self._evidence(
                    case,
                    listing,
                    parsed,
                    comparison,
                    node_price_path if node_prices is not None else None,
                    node_prices,
                    published_price_path
                    if published_energy_prices is not None
                    else None,
                    published_energy_prices,
                    canonical_payload,
                    matrix_validation,
                    price_validation,
                    report_inventory,
                    state_evidence,
                    performance,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return VspdRunResult(
            stage_directory=stage,
            listing=listing,
            evidence=evidence,
            parsed=parsed,
            comparison=comparison,
            node_prices=node_prices,
            published_energy_prices=published_energy_prices,
            matrix_validation=matrix_validation,
            price_validation=price_validation,
            report_inventory=report_inventory,
            state_evidence=state_evidence,
        )

    @staticmethod
    def _canonical_evidence(
        case: VspdCase,
        programs: Path,
        node_prices: DpsNodePriceReport | None,
        published_energy_prices: PublishedEnergyPriceReport | None,
        state_evidence: StateEvidenceInventory | None,
    ) -> tuple[
        dict[str, Any],
        LinearMatrixValidation,
        IndependentPriceValidation,
    ]:
        if node_prices is None and published_energy_prices is None:
            raise VspdRunError(
                "canonical pricing evidence requires a supported price report"
            )
        sources = {
            "input": case.input_gdx,
            "pricing_solution": programs / "pyspd_pricing_solution.gdx",
            "pricing_matrix": programs / "pyspd_pricing_matrix.gdx",
            "pricing_dictionary": programs / "pyspd_pricing_dict.gdx",
        }
        if state_evidence is not None:
            for artifact in state_evidence.checkpoints:
                sources[artifact.path.removesuffix(".gdx")] = programs / artifact.path
            for pair in state_evidence.solve_pairs:
                sources[f"solve_{pair.ordinal:03d}_pre"] = programs / pair.pre.path
                sources[f"solve_{pair.ordinal:03d}_post"] = programs / pair.post.path
                sources[f"solve_{pair.ordinal:03d}_matrix"] = (
                    programs / pair.matrix.path
                )
                sources[f"solve_{pair.ordinal:03d}_dictionary"] = (
                    programs / pair.dictionary.path
                )
        missing = [str(path) for path in sources.values() if not path.is_file()]
        if missing:
            raise VspdRunError(f"canonical evidence files are missing: {missing}")
        destination = case.work_directory / "canonical"
        destination.mkdir()
        system_directory = case.gams_executable.parent
        canonicalizer = GdxCanonicalizer(system_directory)
        manifests: dict[str, Any] = {}
        for name, source in sources.items():
            manifest_path = destination / f"{name}.json"
            manifest = canonicalizer.write_manifest(source, manifest_path)
            manifests[name] = {
                "source_sha256": _sha256(source),
                "manifest": manifest_path.name,
                "manifest_sha256": _sha256(manifest_path),
                "logical_sha256": manifest.logical_sha256,
                "symbol_count": manifest.symbol_count,
                "uel_count": manifest.uel_count,
            }

        matrix_reader = ConvertMatrixReader(system_directory)
        dictionary_reader = ConvertDictionaryReader(system_directory)
        matrix = matrix_reader.read(sources["pricing_matrix"])
        dictionary = dictionary_reader.read(sources["pricing_dictionary"])
        semantic_matrix = dictionary.apply(matrix)
        matrix_validation = LinearMatrixValidator.validate(semantic_matrix)
        matrix_path = destination / "pricing_matrix_evidence.json"
        matrix_payload = {
            "sense": semantic_matrix.sense,
            "row_count": len(semantic_matrix.rows),
            "column_count": len(semantic_matrix.columns),
            "nonzero_count": semantic_matrix.nonzero_count,
            "scalar_logical_sha256": matrix.logical_sha256,
            "scalar_structural_sha256": matrix.structural_sha256,
            "semantic_logical_sha256": semantic_matrix.logical_sha256,
            "semantic_structural_sha256": semantic_matrix.structural_sha256,
            "dictionary_logical_sha256": dictionary.logical_sha256,
            "validation": matrix_validation.to_dict(),
        }
        matrix_path.write_text(
            json.dumps(matrix_payload, indent=2, sort_keys=True) + "\n"
        )

        solve_matrix_evidence: dict[str, Any] = {}
        if state_evidence is not None:
            for pair in state_evidence.solve_pairs:
                name = f"solve_{pair.ordinal:03d}"
                scalar = matrix_reader.read(sources[f"{name}_matrix"])
                names = dictionary_reader.read(sources[f"{name}_dictionary"])
                semantic = names.apply(scalar)
                validation = LinearMatrixValidator.validate(semantic)
                payload = {
                    "ordinal": pair.ordinal,
                    "model": pair.model,
                    "solve_type": pair.solve_type,
                    "sense": semantic.sense,
                    "row_count": len(semantic.rows),
                    "column_count": len(semantic.columns),
                    "nonzero_count": semantic.nonzero_count,
                    "scalar_logical_sha256": scalar.logical_sha256,
                    "scalar_structural_sha256": scalar.structural_sha256,
                    "semantic_logical_sha256": semantic.logical_sha256,
                    "semantic_structural_sha256": semantic.structural_sha256,
                    "dictionary_logical_sha256": names.logical_sha256,
                    "validation": validation.to_dict(),
                }
                path = destination / f"{name}_matrix_evidence.json"
                path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                solve_matrix_evidence[name] = {
                    "manifest": path.name,
                    "manifest_sha256": _sha256(path),
                    **payload,
                }

        if node_prices is not None:
            report_prices = {
                (record.date_time, record.scenario, record.node): record.price
                for record in node_prices.records
            }
            price_validation = GdxPriceValidator(system_directory).validate(
                sources["pricing_solution"],
                report_prices,
            )
        else:
            assert published_energy_prices is not None
            published_prices = {
                (record.date_time, record.node): record.price
                for record in published_energy_prices.records
            }
            price_validation = GdxPublishedPriceValidator(system_directory).validate(
                sources["pricing_solution"],
                published_prices,
            )
        price_path = destination / "price_validation.json"
        price_path.write_text(
            json.dumps(price_validation.to_dict(), indent=2, sort_keys=True) + "\n"
        )
        return (
            {
                "manifests": manifests,
                "matrix_evidence": {
                    "manifest": matrix_path.name,
                    "manifest_sha256": _sha256(matrix_path),
                    **matrix_payload,
                },
                "solve_matrix_evidence": solve_matrix_evidence,
                "price_validation": {
                    "manifest": price_path.name,
                    "manifest_sha256": _sha256(price_path),
                    "passed": price_validation.passed,
                    "active_scenario": price_validation.active_scenario,
                    "price_count": price_validation.price_count,
                    "price_transfer_count": price_validation.price_transfer_count,
                },
            },
            matrix_validation,
            price_validation,
        )

    def _validate(self, case: VspdCase) -> None:
        required = [
            case.source_tree / "Programs" / "vSPDmodel.gms",
            case.source_tree / "Programs" / "vSPDsolve.gms",
            case.source_tree / "Programs" / "vSPDperiod.gms",
            case.input_gdx,
            case.gams_executable,
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise VspdRunError(f"required files are missing: {missing}")
        if not self._safe_name.fullmatch(case.input_gdx.name):
            raise VspdRunError(f"unsafe GDX filename: {case.input_gdx.name!r}")

    @classmethod
    def _read_settings(cls, path: Path) -> dict[str, str]:
        settings = {
            match.group("name"): match.group("value")
            for match in cls._setting.finditer(path.read_text())
        }
        missing = {"runName", "opMode"} - settings.keys()
        if missing:
            raise VspdRunError(f"missing vSPD settings: {sorted(missing)}")
        return settings

    @staticmethod
    def _stage_source_tree(source: Path, destination: Path) -> None:
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(".git"),
        )

    @staticmethod
    def _report_setup(operation_mode: str) -> str:
        if operation_mode == "DPS":
            return "Demand/DPSreportSetup.gms"
        if operation_mode in {"SPD", "AUD"}:
            return "vSPDreportSetup.gms"
        raise VspdRunError(
            f"operation mode {operation_mode!r} has no qualified report setup"
        )

    @staticmethod
    def _execute(
        executable: Path,
        programs: Path,
        arguments: list[str],
        log: Path,
    ) -> float:
        started = time.perf_counter()
        completed = subprocess.run(
            [str(executable), *arguments],
            cwd=programs,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        log.write_text(completed.stdout)
        if completed.returncode != 0:
            raise VspdRunError(
                f"GAMS command failed with exit code {completed.returncode}; see {log}"
            )
        return time.perf_counter() - started

    @staticmethod
    def _evidence(
        case: VspdCase,
        listing: Path,
        parsed: ListingResult,
        comparison: BaselineComparison | None,
        node_price_path: Path | None,
        node_prices: DpsNodePriceReport | None,
        published_price_path: Path | None,
        published_energy_prices: PublishedEnergyPriceReport | None,
        canonical_payload: dict[str, Any] | None,
        matrix_validation: LinearMatrixValidation | None,
        price_validation: IndependentPriceValidation | None,
        report_inventory: ReportInventory,
        state_evidence: StateEvidenceInventory | None,
        performance: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "case": case.case_name,
            "profile": asdict(case.profile),
            "configuration_overlay": (
                {
                    **case.configuration.to_dict(),
                    "logical_sha256": case.configuration.logical_sha256,
                }
                if case.configuration is not None
                else None
            ),
            "input": {
                "name": case.input_gdx.name,
                "sha256": _sha256(case.input_gdx),
            },
            "listing": {
                "sha256": _sha256(listing),
                "logical_records_sha256": _logical_sha256(
                    [asdict(record) for record in parsed.records]
                ),
                "all_optimal": parsed.all_optimal,
                "primary_solve_count": len(parsed.primary),
                "cleanup_solve_count": len(parsed.cleanup),
                "pricing_solve_count": len(parsed.pricing),
                "matrix_export_count": len(parsed.exports),
                "profile_matches": parsed.matches_profile(case.profile),
            },
            "records": [asdict(record) for record in parsed.records],
            "comparison": comparison.to_dict() if comparison is not None else None,
            "node_prices": (
                {
                    "path": node_price_path.name,
                    "sha256": _sha256(node_price_path),
                    "logical_records_sha256": _logical_sha256(
                        [asdict(record) for record in node_prices.records]
                    ),
                    "record_count": len(node_prices.records),
                    "scenario_count": node_prices.scenario_count,
                    "node_count": node_prices.node_count,
                    "minimum": node_prices.minimum_price,
                    "maximum": node_prices.maximum_price,
                }
                if node_price_path is not None and node_prices is not None
                else None
            ),
            "published_energy_prices": (
                {
                    "path": published_price_path.name,
                    "sha256": _sha256(published_price_path),
                    "record_count": len(published_energy_prices.records),
                    "logical_records_sha256": _logical_sha256(
                        [asdict(record) for record in published_energy_prices.records]
                    ),
                }
                if published_price_path is not None
                and published_energy_prices is not None
                else None
            ),
            "canonical": canonical_payload,
            "validation": {
                "matrix_passed": (
                    matrix_validation.passed if matrix_validation is not None else None
                ),
                "independent_prices_passed": (
                    price_validation.passed if price_validation is not None else None
                ),
            },
            "reports": report_inventory.to_dict(),
            "state_evidence": (
                state_evidence.to_dict() if state_evidence is not None else None
            ),
            "performance": performance,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _peak_child_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024
