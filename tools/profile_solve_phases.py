"""Profile PySPD preparation, model assembly, SCIP, and HiGHS phases."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.architecture import ModelAssembler
from pyspd.hvdc.formulation import HvdcSolveOutcome
from pyspd.orchestration import DailyRunner, PreparedCase, ReserveCaseExecutor
from pyspd.orchestration.types import DailyRunResult, SolveObservation
from pyspd.reserve import RESERVE_FORMULATION_ID, IndependentReserveValidator
from pyspd.solver import HighsBackend, NativeScipBackend
from tools.benchmark_warm_start import _all_solves_optimal, _result_sha256
from tools.gate12.execution_provenance import python_execution_sha256


@dataclass(slots=True)
class CasePhaseTiming:
    case_id: str
    total_seconds: float = 0.0
    assembly_seconds: list[float] = field(default_factory=list)
    clone_seconds: list[float] = field(default_factory=list)
    scip_seconds: list[float] = field(default_factory=list)
    highs_seconds: list[float] = field(default_factory=list)

    @property
    def attributed_seconds(self) -> float:
        return sum(
            self.assembly_seconds
            + self.clone_seconds
            + self.scip_seconds
            + self.highs_seconds
        )


class PhaseRecorder:
    """Record nested solve phases without altering production contracts."""

    def __init__(self) -> None:
        self.active: CasePhaseTiming | None = None
        self.cases: list[CasePhaseTiming] = []

    def begin(self, case_id: str) -> CasePhaseTiming:
        if self.active is not None:
            raise RuntimeError("phase recorder already has an active case")
        self.active = CasePhaseTiming(case_id)
        return self.active

    def finish(self) -> None:
        if self.active is None:
            raise RuntimeError("phase recorder has no active case")
        self.cases.append(self.active)
        self.active = None

    def record(self, name: str, seconds: float) -> None:
        if self.active is None:
            raise RuntimeError(f"{name} occurred outside an active case")
        getattr(self.active, f"{name}_seconds").append(seconds)


class ProfiledExecutor:
    """Wrap the qualified executor with per-case phase accounting."""

    def __init__(self, recorder: PhaseRecorder) -> None:
        self.delegate = ReserveCaseExecutor()
        self.recorder = recorder

    def solve(self, prepared: PreparedCase) -> SolveObservation:
        timing = self.recorder.begin(prepared.specification.case_id)
        started = time.perf_counter()
        try:
            return self.delegate.solve(prepared)
        finally:
            timing.total_seconds = time.perf_counter() - started
            self.recorder.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--case-count", type=int, default=8)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.case_count <= 0:
        parser.error("case-count must be positive")

    source_sha256 = _file_sha256(args.input)
    app = PyspdApplication()
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=args.input,
        output_directory=args.output.parent / "unused-report-output",
        source_sha256=source_sha256,
        gams_system_directory=args.system_directory,
    )
    prepared_started = time.perf_counter()
    cases = tuple(
        islice(app.iter_prepared_cases(configuration), args.case_count)
    )
    preparation_seconds = time.perf_counter() - prepared_started
    if len(cases) != args.case_count:
        parser.error(f"requested {args.case_count} cases, found {len(cases)}")

    recorder = PhaseRecorder()
    executor = ProfiledExecutor(recorder)
    assembler = ModelAssembler.assemble
    cloner = ModelAssembler.clone
    scip = NativeScipBackend.solve_mip
    highs = HighsBackend.solve

    def timed_assemble(instance: Any, *call_args: Any, **call_kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return assembler(instance, *call_args, **call_kwargs)
        finally:
            recorder.record("assembly", time.perf_counter() - started)

    def timed_scip(instance: Any, *call_args: Any, **call_kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return scip(instance, *call_args, **call_kwargs)
        finally:
            recorder.record("scip", time.perf_counter() - started)

    def timed_clone(instance: Any, *call_args: Any, **call_kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return cloner(instance, *call_args, **call_kwargs)
        finally:
            recorder.record("clone", time.perf_counter() - started)

    def timed_highs(instance: Any, *call_args: Any, **call_kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return highs(instance, *call_args, **call_kwargs)
        finally:
            recorder.record("highs", time.perf_counter() - started)

    solve_started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(patch.object(ModelAssembler, "assemble", timed_assemble))
        stack.enter_context(patch.object(ModelAssembler, "clone", timed_clone))
        stack.enter_context(patch.object(NativeScipBackend, "solve_mip", timed_scip))
        stack.enter_context(patch.object(HighsBackend, "solve", timed_highs))
        result = DailyRunner(executor).run(
            app.daily_configuration(configuration), cases
        )
    runner_seconds = time.perf_counter() - solve_started

    validation = _validate(result)
    totals = {
        "model_assembly_seconds": sum(
            sum(item.assembly_seconds) for item in recorder.cases
        ),
        "model_clone_seconds": sum(
            sum(item.clone_seconds) for item in recorder.cases
        ),
        "scip_seconds": sum(sum(item.scip_seconds) for item in recorder.cases),
        "highs_seconds": sum(sum(item.highs_seconds) for item in recorder.cases),
        "executor_seconds": sum(item.total_seconds for item in recorder.cases),
    }
    totals["executor_unattributed_seconds"] = totals["executor_seconds"] - sum(
        totals[name]
        for name in (
            "model_assembly_seconds",
            "model_clone_seconds",
            "scip_seconds",
            "highs_seconds",
        )
    )
    totals["daily_runner_overhead_seconds"] = (
        runner_seconds - totals["executor_seconds"]
    )
    end_to_end_seconds = preparation_seconds + runner_seconds
    unsigned = {
        "schema_version": 1,
        "profile": "pyspd-solve-phase-profile-v1",
        "source_name": args.input.name,
        "source_sha256": source_sha256,
        "environment": f"{platform.system()}-{platform.machine()}",
        "execution_sha256": python_execution_sha256(),
        "benchmark_sha256": _file_sha256(Path(__file__)),
        "case_count": len(cases),
        "case_ids": [item.specification.case_id for item in cases],
        "preparation_seconds": preparation_seconds,
        "runner_seconds": runner_seconds,
        "end_to_end_seconds": end_to_end_seconds,
        "peak_resident_bytes": _peak_resident_bytes(),
        "totals": totals,
        "end_to_end_percent": {
            name: 100.0 * seconds / end_to_end_seconds
            for name, seconds in {
                "preparation": preparation_seconds,
                "model_assembly": totals["model_assembly_seconds"],
                "model_clone": totals["model_clone_seconds"],
                "scip": totals["scip_seconds"],
                "highs": totals["highs_seconds"],
                "executor_unattributed": totals["executor_unattributed_seconds"],
                "daily_runner_overhead": totals["daily_runner_overhead_seconds"],
            }.items()
        },
        "cases": [
            {
                "case_id": item.case_id,
                "total_seconds": item.total_seconds,
                "assembly_seconds": item.assembly_seconds,
                "clone_seconds": item.clone_seconds,
                "scip_seconds": item.scip_seconds,
                "highs_seconds": item.highs_seconds,
                "unattributed_seconds": item.total_seconds
                - item.attributed_seconds,
            }
            for item in recorder.cases
        ],
        "validation": validation,
    }
    payload = {**unsigned, "logical_sha256": _logical_sha256(unsigned)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "end_to_end_seconds": end_to_end_seconds,
                "end_to_end_percent": payload["end_to_end_percent"],
                "validation": validation,
                "logical_sha256": payload["logical_sha256"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _validate(result: DailyRunResult) -> dict[str, Any]:
    validations = [
        IndependentReserveValidator().validate(case.accepted.solve_payload)
        for case in result.cases
        if case.accepted is not None
        and isinstance(case.accepted.solve_payload, HvdcSolveOutcome)
    ]
    return {
        "all_solves_optimal": _all_solves_optimal(result),
        "independent_validation_passed": len(validations) == len(result.cases)
        and all(item.passed for item in validations),
        "maximum_validation_residual": max(
            (
                max(item.residuals.values(), default=0.0)
                for item in validations
            ),
            default=0.0,
        ),
        "result_sha256": _result_sha256(result),
    }


def _peak_resident_bytes() -> int:
    resident = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return resident if platform.system() == "Darwin" else resident * 1024


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


if __name__ == "__main__":
    main()
