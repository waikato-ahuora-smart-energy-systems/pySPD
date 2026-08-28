"""Fail-closed execution and objective comparison for pinned vSPD sources.

The runner stages a source checkout before changing any settings. The pinned
checkout and input fixture therefore remain immutable evidence. CPLEX is the
normative oracle profile; SCIP is explicitly a smoke profile because it does
not provide the marginals required for vSPD price reporting.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

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
  ;
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

%pyspdPricingModel%.Optfile = 0;
%pyspdPricingModel%.reslim = LPTimeLimit;
%pyspdPricingModel%.iterlim = LPIterationLimit;
solve %pyspdPricingModel% using rmip maximizing NETBENEFIT;
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
    solver_status_code: int
    solver_status: str
    model_status_code: int
    model_status: str
    objective: float

    @property
    def optimal(self) -> bool:
        return self.solver_status_code == 1 and self.model_status_code == 1


@dataclass(frozen=True)
class ListingResult:
    records: tuple[SolveRecord, ...]

    @property
    def primary(self) -> tuple[SolveRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.model == PRIMARY_MODEL and record.solve_type == "MIP"
        )

    @property
    def cleanup(self) -> tuple[SolveRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.model == CLEANUP_MODEL and record.solve_type == "MIP"
        )

    @property
    def pricing(self) -> tuple[SolveRecord, ...]:
        return tuple(record for record in self.records if record.solve_type == "RMIP")

    @property
    def all_optimal(self) -> bool:
        return bool(self.records) and all(record.optimal for record in self.records)


class VspdListingParser:
    """Extract scenario-aware solve records from a GAMS vSPD listing."""

    _loop = re.compile(r"^LOOPS\s+drs\s+(?P<scenario>[^\n]+)$", re.MULTILINE)
    _report = re.compile(
        r"Solution Report\s+SOLVE\s+(?P<model>\S+)\s+Using\s+"
        r"(?P<solve_type>\S+).*?"
        r"\*\*\*\* SOLVER STATUS\s+(?P<solver_code>\d+)\s+"
        r"(?P<solver_status>[^\n]+).*?"
        r"\*\*\*\* MODEL STATUS\s+(?P<model_code>\d+)\s+"
        r"(?P<model_status>[^\n]+).*?"
        r"\*\*\*\* OBJECTIVE VALUE\s+(?P<objective>[-+0-9.Ee]+)",
        re.DOTALL,
    )

    def parse_file(self, path: Path) -> ListingResult:
        return self.parse_text(path.read_text(errors="replace"))

    def parse_text(self, text: str) -> ListingResult:
        loops = tuple(self._loop.finditer(text))
        records: list[SolveRecord] = []
        for report in self._report.finditer(text):
            preceding = [loop for loop in loops if loop.start() < report.start()]
            scenario = preceding[-1].group("scenario").strip() if preceding else "base"
            records.append(
                SolveRecord(
                    scenario=scenario,
                    model=report.group("model"),
                    solve_type=report.group("solve_type"),
                    solver_status_code=int(report.group("solver_code")),
                    solver_status=report.group("solver_status").strip(),
                    model_status_code=int(report.group("model_code")),
                    model_status=report.group("model_status").strip(),
                    objective=float(report.group("objective")),
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
                raise PriceReportError(f"duplicate node-price key at row {line_number}: {key!r}")
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
class NativeGamsProfile:
    name: str
    mip_solver: str
    lp_solver: str
    use_option_files: bool
    normative: bool
    supports_marginals: bool
    explicit_fixed_lp_pricing: bool


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
        )


class ScipHighsPricingProfile(NativeGamsProfile):
    """SCIP primary MIP followed by an explicit HiGHS fixed-discrete RMIP."""

    def __init__(self) -> None:
        super().__init__(
            name="gams-scip-highs-pricing",
            mip_solver="SCIP",
            lp_solver="HiGHS",
            use_option_files=False,
            normative=False,
            supports_marginals=True,
            explicit_fixed_lp_pricing=True,
        )


class VspdSourcePatcher:
    """Apply a minimal solver overlay and reject unexpected source revisions."""

    def apply(self, programs: Path, profile: NativeGamsProfile) -> None:
        settings = programs / "vSPDsettings.inc"
        solve = programs / "vSPDsolve.gms"
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
            self._apply_fixed_lp_pricing(programs, solve, profile.lp_solver)

    def _apply_fixed_lp_pricing(
        self,
        programs: Path,
        solve: Path,
        pricing_solver: str,
    ) -> None:
        self._replace_exact(
            solve,
            "option mip = %Solver% ;",
            f"option mip = %Solver% ;\noption rmip = {pricing_solver} ;",
            expected_count=1,
        )
        self._replace_exact(
            solve,
            "\nScalars\n  modelSolved",
            "\n$include pyspd_pricing_declarations.inc\n\nScalars\n  modelSolved",
            expected_count=1,
        )
        self._replace_exact(
            solve,
            "solve vSPD_NMIR using mip maximizing NETBENEFIT ;",
            "solve vSPD_NMIR using mip maximizing NETBENEFIT ;\n"
            "$setglobal pyspdPricingModel vSPD_NMIR\n"
            "$include pyspd_fixed_lp_solve.inc",
            expected_count=2,
        )
        self._replace_exact(
            solve,
            "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;",
            "solve vSPD_BranchFlowMIP using mip maximizing NETBENEFIT ;\n"
            "$setglobal pyspdPricingModel vSPD_BranchFlowMIP\n"
            "$include pyspd_fixed_lp_solve.inc",
            expected_count=1,
        )
        (programs / "pyspd_pricing_declarations.inc").write_text(
            _PRICING_DECLARATIONS
        )
        (programs / "pyspd_fixed_lp_solve.inc").write_text(_FIXED_LP_SOLVE)

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
    ) -> None:
        self.parser = parser or VspdListingParser()
        self.patcher = patcher or VspdSourcePatcher()
        self.price_parser = price_parser or DpsNodePriceParser()

    def run(
        self,
        case: VspdCase,
        baseline: ObjectiveBaseline | None = None,
        absolute_tolerance: float = 0.01,
        relative_tolerance: float = 1e-9,
    ) -> VspdRunResult:
        self._validate(case)
        stage = case.work_directory / "vspd"
        if stage.exists():
            raise VspdRunError(f"refusing to overwrite existing stage directory: {stage}")
        case.work_directory.mkdir(parents=True, exist_ok=True)
        shutil.copytree(case.source_tree, stage)

        programs = stage / "Programs"
        staged_input = stage / "Input" / case.input_gdx.name
        staged_input.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(case.input_gdx, staged_input)
        self.patcher.apply(programs, case.profile)
        (programs / "vSPDcase.inc").write_text(
            f"$setglobal  GDXname  {case.case_name}\n"
        )

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
        for name, arguments in commands:
            self._execute(case.gams_executable, programs, arguments, logs / f"{name}.log")

        listing = programs / "vSPDsolve.lst"
        parsed = self.parser.parse_file(listing)
        node_price_path = output / f"{run_name}_NodePriceSensitivity.csv"
        node_prices = (
            self.price_parser.parse_file(node_price_path)
            if operation_mode == "DPS" and case.profile.supports_marginals
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
        settings = {match.group("name"): match.group("value") for match in cls._setting.finditer(path.read_text())}
        missing = {"runName", "opMode"} - settings.keys()
        if missing:
            raise VspdRunError(f"missing vSPD settings: {sorted(missing)}")
        return settings

    @staticmethod
    def _report_setup(operation_mode: str) -> str:
        if operation_mode == "DPS":
            return "Demand/DPSreportSetup.gms"
        if operation_mode == "SPD":
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
    ) -> None:
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

    @staticmethod
    def _evidence(
        case: VspdCase,
        listing: Path,
        parsed: ListingResult,
        comparison: BaselineComparison | None,
        node_price_path: Path | None,
        node_prices: DpsNodePriceReport | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "case": case.case_name,
            "profile": asdict(case.profile),
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
