"""Capability-aware Gate 6 LP/MPS and diagnostic-copy workflows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

import pyomo.environ as pyo

from pyspd.architecture import BuiltModel


class PricingOutcome(Protocol):
    @property
    def primary_model(self) -> BuiltModel: ...

    @property
    def pricing_model(self) -> BuiltModel: ...

    @property
    def fixed_discrete(self) -> Mapping[str, float]: ...


class DiagnosticCapabilityError(RuntimeError):
    """A requested solver diagnostic is not supported by the selected backend."""


@dataclass(frozen=True, slots=True)
class DiagnosticBundle:
    directory: Path
    files: dict[str, Path]
    sha256: dict[str, str]
    iis_supported: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))
        object.__setattr__(self, "sha256", MappingProxyType(dict(self.sha256)))


@dataclass(frozen=True, slots=True)
class PricingModelAudit:
    primary_algebra_sha256: str
    pricing_algebra_sha256: str
    primary_state_sha256: str
    pricing_state_sha256: str
    primary_discrete_count: int
    pricing_discrete_count: int
    primary_sos_count: int
    pricing_sos_count: int
    fixed_name_count: int
    complete_fix_set: bool
    approved_algebra_unchanged: bool
    passed: bool


class HvdcDiagnosticExporter:
    """Export reproducible problem copies without mutating the solved model."""

    IIS_CAPABILITIES = MappingProxyType(
        {
            "gams-scip": False,
            "highs": False,
            "cplex": True,
            "gurobi": True,
        }
    )

    def export(
        self,
        built_model: BuiltModel,
        directory: Path,
        *,
        backend: str,
    ) -> DiagnosticBundle:
        directory = directory.resolve()
        directory.mkdir(parents=True, exist_ok=True)
        lp_path = directory / "model.lp"
        mps_path = directory / "model.mps"
        built_model.model.write(
            str(lp_path),
            format="lp",
            io_options={"symbolic_solver_labels": True},
        )
        built_model.model.write(
            str(mps_path),
            format="mps",
            io_options={"symbolic_solver_labels": True},
        )
        files = {"lp": lp_path, "mps": mps_path}
        return DiagnosticBundle(
            directory,
            files,
            {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in files.items()
            },
            self.IIS_CAPABILITIES.get(backend, False),
        )

    def require_iis(self, backend: str) -> None:
        if not self.IIS_CAPABILITIES.get(backend, False):
            raise DiagnosticCapabilityError(
                f"IIS extraction is unavailable for backend {backend!r}; "
                "LP/MPS diagnostic copies remain available"
            )


def active_discrete_count(model: pyo.ConcreteModel) -> int:
    return sum(
        variable.is_binary() or variable.is_integer()
        for variable in model.component_data_objects(pyo.Var, active=True)
        if not variable.fixed
    )


def audit_pricing_model(outcome: PricingOutcome) -> PricingModelAudit:
    """Fingerprint and prove the allowed MIP-to-RMIP model transition."""

    primary = outcome.primary_model.model
    pricing = outcome.pricing_model.model
    fixed = dict(outcome.fixed_discrete)
    primary_discrete_names = {
        variable.name
        for variable in primary.component_data_objects(pyo.Var, active=True)
        if variable.is_binary() or variable.is_integer()
    }
    pricing_discrete = active_discrete_count(pricing)
    primary_sos = sum(
        1 for _ in primary.component_data_objects(pyo.SOSConstraint, active=True)
    )
    pricing_sos = sum(
        1 for _ in pricing.component_data_objects(pyo.SOSConstraint, active=True)
    )
    primary_algebra = _algebra_sha256(primary)
    pricing_algebra = _algebra_sha256(pricing)
    complete = primary_discrete_names == set(fixed)
    unchanged = primary_algebra == pricing_algebra
    passed = complete and pricing_discrete == 0 and pricing_sos == 0 and unchanged
    return PricingModelAudit(
        primary_algebra,
        pricing_algebra,
        _state_sha256(primary),
        _state_sha256(pricing),
        len(primary_discrete_names),
        pricing_discrete,
        primary_sos,
        pricing_sos,
        len(fixed),
        complete,
        unchanged,
        passed,
    )


def _algebra_sha256(model: pyo.ConcreteModel) -> str:
    payload = [
        (
            constraint.name,
            str(constraint.lower),
            str(constraint.body),
            str(constraint.upper),
        )
        for constraint in model.component_data_objects(pyo.Constraint, active=True)
    ]
    return _sha256(payload)


def _state_sha256(model: pyo.ConcreteModel) -> str:
    payload = [
        (
            variable.name,
            variable.domain.name,
            variable.fixed,
            None if not variable.fixed else float(pyo.value(variable)),
        )
        for variable in model.component_data_objects(pyo.Var, active=True)
    ]
    return _sha256(payload)


def _sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
