"""Class-based formulation composition and extension contracts."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar

import pyomo.environ as pyo


class AssemblyError(ValueError):
    """The declared formulation graph cannot be assembled safely."""


@dataclass(frozen=True, slots=True)
class BuildContext:
    model: pyo.ConcreteModel
    case_data: Any
    artifacts: ModelArtifacts


class ModelArtifacts:
    """Owner-checked typed handle registry for shared model artifacts."""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._owners: dict[str, str] = {}
        self._sealed = False

    def register(self, owner: str, name: str, value: Any) -> None:
        if self._sealed:
            raise AssemblyError("artifact registry is sealed")
        if name in self._values:
            raise AssemblyError(
                f"artifact {name!r} already owned by {self._owners[name]!r}"
            )
        self._values[name] = value
        self._owners[name] = owner

    def seal(self) -> None:
        self._sealed = True

    def __getitem__(self, name: str) -> Any:
        return self._values[name]

    @property
    def values(self) -> Mapping[str, Any]:
        return MappingProxyType(self._values)

    @property
    def owners(self) -> Mapping[str, str]:
        return MappingProxyType(self._owners)


class VersionedExtension(ABC):
    supported_formulations: ClassVar[frozenset[str]] = frozenset()


class ModelComponent(VersionedExtension):
    name: ClassVar[str]
    requires: ClassVar[frozenset[str]] = frozenset()
    provides: ClassVar[frozenset[str]] = frozenset()

    @abstractmethod
    def build(self, context: BuildContext) -> Mapping[str, Any]:
        """Build one cohesive subsystem and return its provided handles."""


class PreprocessorStep(VersionedExtension):
    @abstractmethod
    def transform(self, case_data: Any) -> Any:
        """Return a new immutable case-data value."""


class SolvePolicy(VersionedExtension):
    @abstractmethod
    def solve(self, built_model: BuiltModel) -> Any:
        """Execute the declared solve state machine."""


class PricingEngine(VersionedExtension):
    @abstractmethod
    def price(self, built_model: BuiltModel, solve_result: Any) -> Any:
        """Produce explicitly qualified prices."""


class ResultSchema(VersionedExtension):
    @abstractmethod
    def collect(self, built_model: BuiltModel, solve_result: Any) -> Any:
        """Collect typed results from registered handles."""


class ReportRenderer(VersionedExtension):
    @abstractmethod
    def render(self, results: Any) -> Any:
        """Render results without mutating the model or source data."""


@dataclass(frozen=True, slots=True)
class Formulation:
    formulation_id: str
    components: tuple[type[ModelComponent], ...]
    preprocessors: tuple[type[PreprocessorStep], ...]
    solve_policy: type[SolvePolicy]
    pricing_engine: type[PricingEngine]
    result_schema: type[ResultSchema]
    report_renderer: type[ReportRenderer]


@dataclass(frozen=True, slots=True)
class BuiltModel:
    model: pyo.ConcreteModel
    artifacts: ModelArtifacts
    formulation: Formulation
    case_data: Any
    build_order: tuple[str, ...]
    structural_signature: str


class ModelAssembler:
    def assemble(self, formulation: Formulation, case_data: Any) -> BuiltModel:
        self._validate_versions(formulation)
        component_types = tuple(formulation.components)
        names = [component.name for component in component_types]
        if len(set(names)) != len(names):
            raise AssemblyError("duplicate component name")

        providers: dict[str, type[ModelComponent]] = {}
        for component in component_types:
            for artifact in component.provides:
                if artifact in providers:
                    raise AssemblyError(
                        f"duplicate owner for artifact {artifact!r}: "
                        f"{providers[artifact].name!r} and {component.name!r}"
                    )
                providers[artifact] = component
        for component in component_types:
            for requirement in component.requires:
                if requirement not in providers:
                    raise AssemblyError(
                        f"missing provider for {requirement!r} required by "
                        f"{component.name!r}"
                    )

        remaining = set(component_types)
        provided: set[str] = set()
        ordered: list[type[ModelComponent]] = []
        while remaining:
            ready = sorted(
                (
                    component
                    for component in remaining
                    if component.requires <= provided
                ),
                key=lambda component: component.name,
            )
            if not ready:
                cycle_names = ", ".join(
                    sorted(component.name for component in remaining)
                )
                raise AssemblyError(f"component dependency cycle: {cycle_names}")
            for component in ready:
                ordered.append(component)
                provided.update(component.provides)
                remaining.remove(component)

        transformed = case_data
        for preprocessor_type in formulation.preprocessors:
            transformed = preprocessor_type().transform(transformed)

        model = pyo.ConcreteModel(name=formulation.formulation_id)
        artifacts = ModelArtifacts()
        context = BuildContext(model=model, case_data=transformed, artifacts=artifacts)
        for component_type in ordered:
            values = dict(component_type().build(context))
            if set(values) != set(component_type.provides):
                raise AssemblyError(
                    f"component {component_type.name!r} returned "
                    f"{sorted(values)!r}; declared {sorted(component_type.provides)!r}"
                )
            for name, value in values.items():
                artifacts.register(component_type.name, name, value)
        artifacts.seal()
        build_order = tuple(component.name for component in ordered)
        structural_payload = {
            "formulation_id": formulation.formulation_id,
            "build_order": list(build_order),
            "components": [
                {
                    "class": f"{component.__module__}.{component.__qualname__}",
                    "name": component.name,
                    "requires": sorted(component.requires),
                    "provides": sorted(component.provides),
                }
                for component in ordered
            ],
            "extensions": [
                f"{extension.__module__}.{extension.__qualname__}"
                for extension in (
                    *formulation.preprocessors,
                    formulation.solve_policy,
                    formulation.pricing_engine,
                    formulation.result_schema,
                    formulation.report_renderer,
                )
            ],
            "artifact_owners": dict(artifacts.owners),
            "model_structure": _model_structure(model),
        }
        structural_signature = hashlib.sha256(
            json.dumps(
                structural_payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return BuiltModel(
            model=model,
            artifacts=artifacts,
            formulation=formulation,
            case_data=transformed,
            build_order=build_order,
            structural_signature=structural_signature,
        )

    @staticmethod
    def _validate_versions(formulation: Formulation) -> None:
        extensions: tuple[type[VersionedExtension], ...] = (
            *formulation.components,
            *formulation.preprocessors,
            formulation.solve_policy,
            formulation.pricing_engine,
            formulation.result_schema,
            formulation.report_renderer,
        )
        for extension in extensions:
            if formulation.formulation_id not in extension.supported_formulations:
                raise AssemblyError(
                    f"{extension.__name__} does not support "
                    f"{formulation.formulation_id}"
                )


class FormulationRegistry:
    def __init__(self) -> None:
        self._formulations: dict[str, Formulation] = {}

    def register(self, formulation: Formulation) -> None:
        if formulation.formulation_id in self._formulations:
            raise AssemblyError(
                f"duplicate formulation: {formulation.formulation_id!r}"
            )
        self._formulations[formulation.formulation_id] = formulation

    def resolve(self, formulation_id: str) -> Formulation:
        try:
            return self._formulations[formulation_id]
        except KeyError as error:
            raise AssemblyError(f"unknown formulation: {formulation_id!r}") from error


class RebuildDecision(StrEnum):
    """Safe action for a previously assembled model instance."""

    REUSE = "reuse"
    REBUILD = "rebuild"


@dataclass(frozen=True, slots=True)
class RebuildComparison:
    decision: RebuildDecision
    reason: str
    invalidate: frozenset[str]


class StructuralRebuildPolicy:
    """Fail closed on structural changes and invalidate all reusable solve state."""

    _STALE_STATE = frozenset(
        {"primal", "dual", "basis", "fixed_discrete", "solution_loader"}
    )

    def compare(self, previous: BuiltModel, candidate: BuiltModel) -> RebuildComparison:
        if previous.structural_signature != candidate.structural_signature:
            return RebuildComparison(
                RebuildDecision.REBUILD,
                "active model structure changed",
                self._STALE_STATE,
            )
        return RebuildComparison(
            RebuildDecision.REUSE,
            "semantic structure is unchanged; update values and invalidate solve state",
            self._STALE_STATE,
        )


def _model_structure(model: pyo.ConcreteModel) -> Mapping[str, object]:
    """Return a value-independent signature of domains, rows, SOS, and ownership."""

    variables: list[dict[str, object]] = []
    for component in model.component_objects(pyo.Var, active=True, descend_into=True):
        variable_entries: list[dict[str, object]] = []
        for index in component:
            item = component[index]
            domain = (
                "binary"
                if item.is_binary()
                else "integer"
                if item.is_integer()
                else "continuous"
            )
            variable_entries.append(
                {"index": _index_token(index), "domain": domain}
            )
        variables.append(
            {
                "name": component.name,
                "entries": sorted(
                    variable_entries, key=lambda x: str(x["index"])
                ),
            }
        )

    constraints: list[dict[str, object]] = []
    for component in model.component_objects(
        pyo.Constraint, active=True, descend_into=True
    ):
        constraint_entries: list[dict[str, object]] = []
        for index in component:
            item = component[index]
            if not item.active:
                continue
            constraint_entries.append(
                {
                    "index": _index_token(index),
                    "equality": bool(item.equality),
                    "has_lower": item.lower is not None,
                    "has_upper": item.upper is not None,
                }
            )
        constraints.append(
            {
                "name": component.name,
                "entries": sorted(
                    constraint_entries, key=lambda x: str(x["index"])
                ),
            }
        )

    sos: list[dict[str, object]] = []
    for component in model.component_objects(
        pyo.SOSConstraint, active=True, descend_into=True
    ):
        sos_entries = [
            _index_token(index) for index in component if component[index].active
        ]
        sos.append({"name": component.name, "entries": sorted(sos_entries, key=str)})

    objectives = [
        {"name": component.name, "sense": int(component.sense)}
        for component in model.component_objects(
            pyo.Objective, active=True, descend_into=True
        )
    ]
    return {
        "variables": sorted(variables, key=lambda x: str(x["name"])),
        "constraints": sorted(constraints, key=lambda x: str(x["name"])),
        "sos": sorted(sos, key=lambda x: str(x["name"])),
        "objectives": sorted(objectives, key=lambda x: str(x["name"])),
    }


def _index_token(index: object) -> list[str]:
    values = index if isinstance(index, tuple) else (index,)
    return [str(value) for value in values]
