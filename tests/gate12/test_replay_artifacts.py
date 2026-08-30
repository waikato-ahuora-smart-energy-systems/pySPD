"""Probity tests for canonical incremental replay artifacts."""

from __future__ import annotations

import json

import pytest

from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.incremental_replay import (
    IncrementalAvailableWork,
    IncrementalReplayWorkItem,
)
from tools.gate12.pyspd_surfaces import CanonicalCaseSurfaces
from tools.gate12.replay_artifacts import (
    CanonicalReplayBundle,
    CanonicalReplayBundleStore,
    ExactCanonicalDirectoryParityProcessor,
    IncrementalReplayBundleCoordinator,
)


def _work_item() -> IncrementalReplayWorkItem:
    return IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        discovery_checkpoint_sha256="2" * 64,
        case_ids=("warmup", "affected-1", "affected-2"),
        affected_case_ids=("affected-1", "affected-2"),
    )


def _cases(*, changed: str | None = None):
    return tuple(
        CanonicalCaseSurfaces(
            case_id=case_id,
            trading_date="20221106",
            surfaces={
                surface: json.dumps(
                    {
                        "case": case_id,
                        "surface": surface,
                        "value": 2 if surface == changed else 1,
                    },
                    sort_keys=True,
                ).encode()
                + b"\n"
                for surface in REQUIRED_E2E_SURFACES
            },
        )
        for case_id in ("affected-1", "affected-2")
    )


def _write(root, profile: str, cases) -> CanonicalReplayBundle:
    work_item = _work_item()
    bundle = CanonicalReplayBundle.create(
        engine_profile=profile,
        work_item=work_item,
        cases=cases,
    )
    CanonicalReplayBundleStore(root).write(bundle=bundle, cases=cases)
    return bundle


def test_bundle_store_round_trips_and_verifies_every_surface(tmp_path) -> None:
    cases = _cases()
    expected = _write(tmp_path / "bundles", "test-engine-v1", cases)

    actual, loaded_cases = CanonicalReplayBundleStore(tmp_path / "bundles").load(
        "20221106"
    )

    assert actual == expected
    assert loaded_cases == cases
    surface = (
        tmp_path / "bundles" / "20221106" / "cases" / "affected-1" / "node-price.json"
    )
    surface.write_bytes(b"tampered\n")
    with pytest.raises(EvidenceContractError, match="surface hash mismatch"):
        CanonicalReplayBundleStore(tmp_path / "bundles").load("20221106")


def test_exact_processor_accepts_identical_complete_bundles(tmp_path) -> None:
    cases = _cases()
    reference = _write(tmp_path / "reference", "gams-v502", cases)
    candidate = _write(tmp_path / "candidate", "pyspd-v1", cases)
    processor = ExactCanonicalDirectoryParityProcessor(
        reference_root=tmp_path / "reference",
        candidate_root=tmp_path / "candidate",
    )

    result = processor.process(
        work_item=_work_item(),
        source=tmp_path / "input.gdx",
        system_directory=tmp_path / "gams",
    )

    assert result.passed
    assert result.unresolved_material_count == 0
    assert result.reference_artifact_sha256 == reference.logical_sha256
    assert result.candidate_artifact_sha256 == candidate.logical_sha256


def test_exact_processor_exposes_each_changed_surface(tmp_path) -> None:
    _write(tmp_path / "reference", "gams-v502", _cases())
    _write(tmp_path / "candidate", "pyspd-v1", _cases(changed="node-price"))
    processor = ExactCanonicalDirectoryParityProcessor(
        reference_root=tmp_path / "reference",
        candidate_root=tmp_path / "candidate",
    )

    result = processor.process(
        work_item=_work_item(),
        source=tmp_path / "input.gdx",
        system_directory=tmp_path / "gams",
    )

    assert not result.passed
    assert result.unresolved_material_count == 2
    assert all(not case.passed for case in result.cases)
    assert all(
        case.reference_surface_sha256["node-price"]
        != case.candidate_surface_sha256["node-price"]
        for case in result.cases
    )


def test_bundle_rejects_case_order_or_work_item_drift(tmp_path) -> None:
    cases = tuple(reversed(_cases()))
    with pytest.raises(EvidenceContractError, match="case order"):
        CanonicalReplayBundle.create(
            engine_profile="test-engine-v1",
            work_item=_work_item(),
            cases=cases,
        )

    cases = _cases()
    _write(tmp_path / "bundles", "test-engine-v1", cases)
    changed = IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        discovery_checkpoint_sha256="3" * 64,
        case_ids=("warmup", "affected-1", "affected-2"),
        affected_case_ids=("affected-1", "affected-2"),
    )
    bundle, _ = CanonicalReplayBundleStore(tmp_path / "bundles").load("20221106")
    with pytest.raises(EvidenceContractError, match="does not match work item"):
        bundle.validate_for(changed)


def test_bundle_store_rejects_missing_surface(tmp_path) -> None:
    cases = _cases()
    _write(tmp_path / "bundles", "test-engine-v1", cases)
    missing = (
        tmp_path / "bundles" / "20221106" / "cases" / "affected-2" / "report-field.json"
    )
    missing.unlink()

    with pytest.raises(EvidenceContractError, match="surface is unavailable"):
        CanonicalReplayBundleStore(tmp_path / "bundles").load("20221106")


class FakeFeed:
    def __init__(self, source, work_items) -> None:
        self.source = source
        self.work_items = work_items
        self.system_directory = source.parent

    def scan(self):
        return (
            tuple(
                IncrementalAvailableWork(work_item, self.source)
                for work_item in self.work_items
            ),
            "20221109",
        )


class FakeBundleProducer:
    profile = "fake-candidate-v1"

    def __init__(self, root) -> None:
        self.store = CanonicalReplayBundleStore(root)
        self.calls = []

    def produce(self, *, work_item, source, system_directory):
        del source, system_directory
        self.calls.append(work_item.trading_date)
        target = self.store.root / work_item.trading_date
        if target.is_dir():
            bundle, _ = self.store.load(work_item.trading_date)
            return bundle
        cases = tuple(
            CanonicalCaseSurfaces(
                case_id=case_id,
                trading_date=work_item.trading_date,
                surfaces={surface: b"{}\n" for surface in REQUIRED_E2E_SURFACES},
            )
            for case_id in work_item.affected_case_ids
        )
        bundle = CanonicalReplayBundle.create(
            engine_profile=self.profile,
            work_item=work_item,
            cases=cases,
        )
        self.store.write(bundle=bundle, cases=cases)
        return bundle


def test_bundle_coordinator_materializes_available_dates_once(tmp_path) -> None:
    first = _work_item()
    second = IncrementalReplayWorkItem.create(
        trading_date="20221107",
        source_sha256="3" * 64,
        discovery_checkpoint_sha256="4" * 64,
        case_ids=("warmup-2", "affected-3"),
        affected_case_ids=("affected-3",),
    )
    source = tmp_path / "input.gdx"
    source.write_bytes(b"unused")
    feed = FakeFeed(source, (first, second))
    producer = FakeBundleProducer(tmp_path / "candidate")
    coordinator = IncrementalReplayBundleCoordinator(
        feed=feed,  # type: ignore[arg-type]
        producer=producer,
    )

    initial = coordinator.run_available(maximum_new_dates=1)
    resumed = coordinator.run_available()

    assert initial.available_date_count == 2
    assert initial.bundle_count == 1
    assert initial.produced_date_count == 1
    assert initial.affected_case_count == 3
    assert initial.waiting_for_trading_date == "20221109"
    assert initial.deferred_bundle_trading_date == "20221107"
    assert resumed.produced_date_count == 1
    assert resumed.deferred_bundle_trading_date is None
    assert producer.calls == ["20221106", "20221106", "20221107"]
