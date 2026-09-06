"""Run from a temporary harness against an installed wheel, never src/pyspd."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

# Only synthetic fixture helpers are copied beside this script by the harness.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pyspd
from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.orchestration import (
    DailyCase,
    DailyRunner,
    PreparedCase,
    ScheduleType,
)
from pyspd.reporting import ReportBundle
from tests.reserve.conftest import make_reserve_case


def main() -> None:
    work = Path.cwd()
    package_path = Path(pyspd.__file__).resolve()
    assert package_path.is_relative_to(Path(sys.prefix).resolve()), package_path
    assert pyspd.__version__ == importlib.metadata.version("pyspd")
    lock = package_path.parent / "_build/uv.lock"
    assert lock.is_file()
    source = work / "synthetic-case.txt"
    source.write_bytes(b"PySPD synthetic two-island reserve qualification\n")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    app = PyspdApplication()
    configuration = ApplicationConfiguration(
        formulation_id="vspd-v5.0.6-reserve",
        input_path=source,
        output_directory=work / "reports",
        source_sha256=source_hash,
        gams_system_directory=work,
    )
    case = make_reserve_case()
    assert case.network is not None
    specification = DailyCase(
        "C1", "T1", "TP1", 101, ScheduleType.RTD, 5.0, 300.0, 0, source_hash
    )
    prepared = PreparedCase(specification, case, case.network.node_load)
    result = DailyRunner(
        app.case_executor(configuration),
        postprocessor=app.price_postprocessor(configuration),
    ).run(app.daily_configuration(configuration), (prepared,))
    assert result.state.value == "complete"
    bundle = app.render_report_bundle(configuration, result)
    assert (
        bundle.provenance.dependency_lock_sha256
        == hashlib.sha256(lock.read_bytes()).hexdigest()
    )
    manifest = bundle.write(configuration.output_directory)
    restored = ReportBundle.read(configuration.output_directory)
    assert restored == bundle
    repeated = restored.write(work / "roundtrip")
    assert repeated.logical_sha256 == manifest.logical_sha256
    assert len(manifest.files) == 12
    assert {row["status_code"] for row in restored.tables["summary"].rows} == {"1"}
    assert restored.tables["node"].rows
    assert restored.tables["constraint"].rows
    gdx_verified = False
    if len(sys.argv) > 1:
        import gams.transfer as gt

        from pyspd.data import GdxAdapter

        system = Path(sys.argv[1])
        container = gt.Container(system_directory=str(system))
        labels = gt.Set(container, "labels", records=["A", "B"])
        gt.Parameter(container, "load", domain=[labels], records=[["A", 10], ["B", 20]])
        path = work / "synthetic.gdx"
        container.write(str(path))
        symbols = GdxAdapter.read(path, system_directory=system)
        assert symbols.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        gdx_verified = True
    payload = {
        "package_path": str(package_path),
        "version": pyspd.__version__,
        "state": result.state.value,
        "report_manifest_sha256": manifest.logical_sha256,
        "build_lock_sha256": bundle.provenance.dependency_lock_sha256,
        "report_table_count": len(manifest.files),
        "gdx_roundtrip": gdx_verified,
        "validation_scope": "synthetic reserve SCIP/HiGHS solve and report roundtrip",
        "installed_distributions": dict(
            sorted(
                (dist.metadata["Name"], dist.version)
                for dist in importlib.metadata.distributions()
            )
        ),
    }
    (work / "smoke-result.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
