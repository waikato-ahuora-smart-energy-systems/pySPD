"""Immutable preprocessing artifacts, dependency assembly, and hashing."""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from pyspd.contracts import CaseData

type Key = tuple[str, ...]


class PreprocessingError(ValueError):
    """A preprocessing input, dependency, or invariant is invalid."""


class Artifact(ABC):
    name: str
    dimensions: tuple[str, ...]

    @property
    @abstractmethod
    def logical_sha256(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def logical_payload(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SparseSet(Artifact):
    name: str
    dimensions: tuple[str, ...]
    members: frozenset[Key]

    def __post_init__(self) -> None:
        dimensions = tuple(self.dimensions)
        members = frozenset(tuple(key) for key in self.members)
        if any(len(key) != len(dimensions) for key in members):
            raise PreprocessingError(f"dimension mismatch in set {self.name}")
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "members", members)

    def __contains__(self, key: Key) -> bool:
        return key in self.members

    def logical_payload(self) -> dict[str, Any]:
        return {
            "kind": "set",
            "name": self.name,
            "dimensions": list(self.dimensions),
            "members": [list(key) for key in sorted(self.members)],
        }

    @property
    def logical_sha256(self) -> str:
        return _logical_sha256(self.logical_payload())


@dataclass(frozen=True, slots=True)
class SparseParameter(Artifact):
    name: str
    dimensions: tuple[str, ...]
    values: Mapping[Key, float] = field(repr=False)

    def __post_init__(self) -> None:
        dimensions = tuple(self.dimensions)
        values = {tuple(key): float(value) for key, value in self.values.items()}
        if any(len(key) != len(dimensions) for key in values):
            raise PreprocessingError(f"dimension mismatch in parameter {self.name}")
        if any(not math.isfinite(value) for value in values.values()):
            raise PreprocessingError(f"non-finite value in parameter {self.name}")
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "values", MappingProxyType(values))

    def get(self, key: Key, default: float = 0.0) -> float:
        return self.values.get(key, default)

    def logical_payload(self) -> dict[str, Any]:
        return {
            "kind": "parameter",
            "name": self.name,
            "dimensions": list(self.dimensions),
            "values": [
                {"key": list(key), "value": value.hex()}
                for key, value in sorted(self.values.items())
            ],
        }

    @property
    def logical_sha256(self) -> str:
        return _logical_sha256(self.logical_payload())


@dataclass(frozen=True, slots=True)
class PreprocessingSettings:
    daily_mode: bool = True
    use_ac_loss_model: bool = True
    use_hvdc_loss_model: bool = True
    use_reserve_model: bool = True
    apply_rtd_load_reconstruction: bool = False


@dataclass(frozen=True, slots=True)
class Checkpoint:
    step: str
    artifact_names: tuple[str, ...]
    logical_sha256: str


@dataclass(frozen=True, slots=True)
class PreprocessingResult:
    formulation_id: str
    case_id: str
    artifacts: Mapping[str, Artifact]
    checkpoints: tuple[Checkpoint, ...]
    build_order: tuple[str, ...]
    structural_signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))

    def set(self, name: str) -> SparseSet:
        artifact = self.artifacts[name]
        if not isinstance(artifact, SparseSet):
            raise TypeError(f"{name} is not a sparse set")
        return artifact

    def parameter(self, name: str) -> SparseParameter:
        artifact = self.artifacts[name]
        if not isinstance(artifact, SparseParameter):
            raise TypeError(f"{name} is not a sparse parameter")
        return artifact


class PreprocessingStep(ABC):
    name: str
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()

    @abstractmethod
    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        raise NotImplementedError


class PreprocessingPipeline:
    def __init__(self, steps: Sequence[PreprocessingStep]) -> None:
        self.steps = tuple(steps)

    def run(
        self,
        case_data: CaseData,
        settings: PreprocessingSettings | None = None,
    ) -> PreprocessingResult:
        settings = settings or PreprocessingSettings()
        ordered = self._ordered_steps()
        artifacts: dict[str, Artifact] = {}
        checkpoints: list[Checkpoint] = []
        for step in ordered:
            output = dict(step.apply(case_data, MappingProxyType(artifacts), settings))
            if set(output) != set(step.provides):
                raise PreprocessingError(
                    f"{step.name} returned {sorted(output)}, expected {sorted(step.provides)}"
                )
            duplicate = set(output) & set(artifacts)
            if duplicate:
                raise PreprocessingError(
                    f"duplicate preprocessing artifact: {sorted(duplicate)}"
                )
            artifacts.update(output)
            checkpoint_payload = {
                "step": step.name,
                "artifacts": [
                    artifacts[name].logical_payload() for name in sorted(output)
                ],
            }
            checkpoints.append(
                Checkpoint(
                    step.name,
                    tuple(sorted(output)),
                    _logical_sha256(checkpoint_payload),
                )
            )
        build_order = tuple(step.name for step in ordered)
        signature = _logical_sha256(
            {
                "formulation_id": case_data.formulation_id,
                "steps": [
                    {
                        "class": f"{type(step).__module__}.{type(step).__qualname__}",
                        "name": step.name,
                        "requires": sorted(step.requires),
                        "provides": sorted(step.provides),
                    }
                    for step in ordered
                ],
                "settings": {
                    "daily_mode": settings.daily_mode,
                    "use_ac_loss_model": settings.use_ac_loss_model,
                    "use_hvdc_loss_model": settings.use_hvdc_loss_model,
                    "use_reserve_model": settings.use_reserve_model,
                    "apply_rtd_load_reconstruction": settings.apply_rtd_load_reconstruction,
                },
            }
        )
        return PreprocessingResult(
            case_data.formulation_id,
            case_data.identifier.case_id,
            artifacts,
            tuple(checkpoints),
            build_order,
            signature,
        )

    def _ordered_steps(self) -> tuple[PreprocessingStep, ...]:
        owners: dict[str, PreprocessingStep] = {}
        for step in self.steps:
            for artifact in step.provides:
                if artifact in owners:
                    raise PreprocessingError(
                        f"duplicate provider for {artifact}: "
                        f"{owners[artifact].name}, {step.name}"
                    )
                owners[artifact] = step
        for step in self.steps:
            missing = step.requires - set(owners)
            if missing:
                raise PreprocessingError(
                    f"{step.name} has missing providers: {sorted(missing)}"
                )
        pending = list(self.steps)
        resolved: set[str] = set()
        ordered: list[PreprocessingStep] = []
        while pending:
            ready = sorted(
                (step for step in pending if step.requires <= resolved),
                key=lambda step: step.name,
            )
            if not ready:
                raise PreprocessingError(
                    f"preprocessing dependency cycle: {[step.name for step in pending]}"
                )
            for step in ready:
                pending.remove(step)
                ordered.append(step)
                resolved.update(step.provides)
        return tuple(ordered)


def _logical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
