from pathlib import Path

from pyspd.evidence import EvidenceManifest
from tools.build_evidence_archives import RepositoryEvidencePlan


def test_repository_plan_separates_all_large_evidence_families() -> None:
    root = Path(__file__).parents[2]
    plans = RepositoryEvidencePlan(root).plans()

    assert tuple(plan.artifact_id for plan in plans) == (
        "cplex-reference-v1",
        "cplex-consecutive-v1",
        "odd-day-reference-v1",
        "gate12-solver-paths-v1",
    )
    assert all(path.suffix == ".json" for path in plans[-1].source_paths)

    manifest = EvidenceManifest.from_json(root / "evidence/manifest-v1.json")
    assert manifest.artifact("gate12-solver-paths-v1").file_count == 94
