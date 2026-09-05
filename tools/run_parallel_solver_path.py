"""Run one solver profile through the governed multiprocessing coordinator."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any

from pyspd.application import (
    PORTABLE_SOLVER_PROFILE,
    SUPPORTED_SOLVER_PROFILES,
    ApplicationConfiguration,
    PyspdApplication,
)
from pyspd.data import SUPPORTED_INPUT_SCHEMAS, V5_INPUT_SCHEMA
from pyspd.orchestration import (
    CaseBoundary,
    CaseShard,
    ContiguousCaseShardPlanner,
    DynamicCaseJobPlanner,
    ProcessShardCoordinator,
)
from pyspd.reserve import RESERVE_FORMULATION_ID


@dataclass(frozen=True, slots=True)
class SolverPathShardRequest:
    input_path: str
    system_directory: str
    output_directory: str
    base_start_ordinal: int
    profile: str
    input_schema: str
    case_ids: tuple[str, ...]
    maximum_case_attempts: int
    validation_tolerance: float


@dataclass(frozen=True, slots=True)
class SolverPathShardArtifact:
    shard_index: int
    benchmark_path: str
    records_path: str
    log_path: str
    wall_seconds: float
    solve_seconds: float
    case_count: int
    records_sha256: str


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", required=True, type=int)
    parser.add_argument(
        "--scheduling",
        choices=("dynamic", "static"),
        default="dynamic",
        help="dynamic assigns small jobs to the next idle worker",
    )
    parser.add_argument(
        "--cases-per-job",
        type=int,
        default=1,
        help="case count per dynamic job (default: 1)",
    )
    parser.add_argument("--expected-case-count", type=int)
    parser.add_argument("--case-ids", nargs="+", default=[])
    parser.add_argument("--start-ordinal", type=int, default=0)
    parser.add_argument("--maximum-cases", type=int)
    parser.add_argument("--maximum-case-attempts", type=int, default=2)
    parser.add_argument("--validation-tolerance", type=float, default=1e-4)
    parser.add_argument(
        "--profile",
        choices=sorted(SUPPORTED_SOLVER_PROFILES),
        default=PORTABLE_SOLVER_PROFILE,
    )
    parser.add_argument(
        "--input-schema",
        choices=sorted(SUPPORTED_INPUT_SCHEMAS),
        default=V5_INPUT_SCHEMA,
    )
    parser.add_argument("--reference-records", type=Path)
    args = parser.parse_args()
    if args.start_ordinal < 0:
        parser.error("--start-ordinal must be non-negative")
    if args.maximum_cases is not None and args.maximum_cases <= 0:
        parser.error("--maximum-cases must be positive")
    if args.expected_case_count is not None and args.expected_case_count <= 0:
        parser.error("--expected-case-count must be positive")
    if args.maximum_case_attempts <= 0:
        parser.error("--maximum-case-attempts must be positive")
    if args.cases_per_job <= 0:
        parser.error("--cases-per-job must be positive")

    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"parallel output already exists: {output}")
    shard_directory = output.with_name(f"{output.stem}-shards")
    shard_directory.mkdir(parents=True, exist_ok=False)
    source = args.input.resolve()
    source_sha256 = _file_sha256(source)
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=source,
        output_directory=shard_directory / "unused",
        source_sha256=source_sha256,
        gams_system_directory=args.system_directory,
        solver_profile=args.profile,
        input_schema=args.input_schema,
        case_ids=tuple(args.case_ids),
    )

    total_started = time.perf_counter()
    preparation_started = total_started
    prepared = tuple(
        PyspdApplication().iter_prepared_cases(
            configuration,
            start_ordinal=args.start_ordinal,
            maximum_cases=args.maximum_cases,
        )
    )
    boundaries = tuple(
        CaseBoundary(
            case_id=case.specification.case_id,
            ordinal=index,
            predecessor_independent=any(case.generation_start.values()),
        )
        for index, case in enumerate(prepared)
    )
    preparation_seconds = time.perf_counter() - preparation_started
    del prepared
    gc.collect()
    if args.expected_case_count is not None and len(boundaries) != args.expected_case_count:
        raise ValueError(
            f"expected {args.expected_case_count} cases, selected {len(boundaries)}"
        )
    if args.scheduling == "dynamic":
        plan = DynamicCaseJobPlanner().plan(
            boundaries,
            workers=args.workers,
            cases_per_job=args.cases_per_job,
        )
    else:
        plan = ContiguousCaseShardPlanner().plan(boundaries, workers=args.workers)

    request = SolverPathShardRequest(
        input_path=str(source),
        system_directory=str(args.system_directory.resolve()),
        output_directory=str(shard_directory),
        base_start_ordinal=args.start_ordinal,
        profile=args.profile,
        input_schema=args.input_schema,
        case_ids=tuple(args.case_ids),
        maximum_case_attempts=args.maximum_case_attempts,
        validation_tolerance=args.validation_tolerance,
    )
    execution_started = time.perf_counter()
    artifacts = ProcessShardCoordinator().run(
        plan, partial(_execute_solver_path_shard, request)
    )
    execution_seconds = time.perf_counter() - execution_started

    merge_started = time.perf_counter()
    command = [
        sys.executable,
        "-m",
        "tools.merge_solver_path_shards",
    ]
    for artifact in artifacts:
        command.extend(("--shard", artifact.benchmark_path))
    command.extend(("--output", str(output)))
    if args.reference_records is not None:
        command.extend(("--reference-records", str(args.reference_records.resolve())))
    merged = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    if merged.returncode:
        raise RuntimeError(
            f"parallel shard merge failed ({merged.returncode}): "
            f"{merged.stderr or merged.stdout}"
        )
    merge_seconds = time.perf_counter() - merge_started

    payload: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
    payload["parallel_execution"] = {
        "profile": "pyspd-process-job-coordinator-v2",
        "scheduling": args.scheduling,
        "cases_per_job": (
            args.cases_per_job if args.scheduling == "dynamic" else None
        ),
        "requested_workers": plan.requested_workers,
        "worker_count": plan.worker_count,
        "job_count": plan.job_count,
        "total_case_count": plan.total_case_count,
        "preparation_seconds": preparation_seconds,
        "execution_seconds": execution_seconds,
        "merge_seconds": merge_seconds,
        "total_wall_seconds": time.perf_counter() - total_started,
        "shards": [
            {
                **asdict(shard),
                "artifact": asdict(artifact),
            }
            for shard, artifact in zip(plan.shards, artifacts, strict=True)
        ],
    }
    unsigned = {key: value for key, value in payload.items() if key != "logical_sha256"}
    payload["logical_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    run = payload["runs"][0]
    print(
        json.dumps(
            {
                "output": str(output),
                "worker_count": plan.worker_count,
                "case_count": run["case_count"],
                "all_solves_optimal": run["all_solves_optimal"],
                "independent_validation_passed": run[
                    "independent_validation_passed"
                ],
                "execution_seconds": execution_seconds,
                "total_wall_seconds": payload["parallel_execution"][
                    "total_wall_seconds"
                ],
                "records_sha256": run["records_sha256"],
            },
            sort_keys=True,
        )
    )


def _execute_solver_path_shard(
    request: SolverPathShardRequest, shard: CaseShard
) -> SolverPathShardArtifact:
    output_directory = Path(request.output_directory)
    benchmark = output_directory / f"shard-{shard.index + 1:02d}.json"
    log = output_directory / f"shard-{shard.index + 1:02d}.log"
    command = [
        sys.executable,
        "-m",
        "tools.benchmark_solver_paths",
        request.input_path,
        "--system-directory",
        request.system_directory,
        "--output",
        str(benchmark),
        "--expected-case-count",
        str(shard.case_count),
        "--start-ordinal",
        str(request.base_start_ordinal + shard.start_ordinal),
        "--maximum-cases",
        str(shard.case_count),
        "--maximum-case-attempts",
        str(request.maximum_case_attempts),
        "--validation-tolerance",
        repr(request.validation_tolerance),
        "--profiles",
        request.profile,
        "--input-schema",
        request.input_schema,
    ]
    if request.case_ids:
        command.extend(("--case-ids", *request.case_ids))
    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(
            f"solver process exited {completed.returncode}; inspect {log}"
        )
    payload = json.loads(benchmark.read_text(encoding="utf-8"))
    if len(payload.get("runs", ())) != 1:
        raise RuntimeError(f"shard {shard.index} produced an invalid benchmark")
    run = payload["runs"][0]
    if not run.get("completed") or int(run.get("case_count", -1)) != shard.case_count:
        raise RuntimeError(f"shard {shard.index} did not complete its declared range")
    return SolverPathShardArtifact(
        shard_index=shard.index,
        benchmark_path=str(benchmark),
        records_path=str(run["records_path"]),
        log_path=str(log),
        wall_seconds=float(run["wall_seconds"]),
        solve_seconds=float(run["solve_seconds"]),
        case_count=int(run["case_count"]),
        records_sha256=str(run["records_sha256"]),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
