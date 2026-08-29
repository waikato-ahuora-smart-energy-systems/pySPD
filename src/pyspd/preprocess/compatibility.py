"""Explicit effective-date rules and deterministic override operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType

from pyspd.contracts import CaseData
from pyspd.preprocess.base import (
    Artifact,
    Key,
    PreprocessingError,
    PreprocessingSettings,
    PreprocessingStep,
    SparseParameter,
)
from pyspd.preprocess.input import CaseInput


@dataclass(frozen=True, slots=True)
class CompatibilityProfile:
    input_date: date
    spd_loss_tolerance: float
    directional_risk_available: bool
    legacy_prss_shared_nfr: bool
    fir_uses_bipole_transition: bool

    @classmethod
    def vspd506(cls, input_date: date) -> CompatibilityProfile:
        return cls(
            input_date=input_date,
            spd_loss_tolerance=0.005 if input_date <= date(2023, 4, 27) else 0.00005,
            directional_risk_available=input_date >= date(2025, 3, 17),
            legacy_prss_shared_nfr=input_date <= date(2023, 4, 27),
            fir_uses_bipole_transition=input_date >= date(2019, 3, 28),
        )


class OverrideMethod(StrEnum):
    SCALE = "scale"
    INCREMENT = "increment"
    VALUE = "value"


@dataclass(frozen=True, slots=True)
class OverrideOperation:
    target: str
    selector: tuple[str | None, ...]
    method: OverrideMethod
    value: float
    precedence: int

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise PreprocessingError("override target must not be empty")

    def applies(self, key: Key) -> bool:
        return len(key) == len(self.selector) and all(
            selected is None or selected == found
            for selected, found in zip(self.selector, key, strict=True)
        )


@dataclass(frozen=True, slots=True)
class OverrideRecord:
    target: str
    key: Key
    method: OverrideMethod
    operand: float
    precedence: int
    before: float
    after: float


@dataclass(frozen=True, slots=True)
class OverrideResult:
    values: Mapping[Key, float]
    provenance: tuple[OverrideRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


def apply_overrides(
    target: str,
    values: dict[Key, float],
    operations: tuple[OverrideOperation, ...],
) -> dict[Key, float]:
    return dict(apply_overrides_with_provenance(target, values, operations).values)


def apply_overrides_with_provenance(
    target: str,
    values: Mapping[Key, float],
    operations: tuple[OverrideOperation, ...],
) -> OverrideResult:
    result = dict(values)
    provenance: list[OverrideRecord] = []
    for operation in sorted(operations, key=lambda item: item.precedence):
        if operation.target != target:
            continue
        matched = [key for key in result if operation.applies(key)]
        for key in matched:
            before = result[key]
            if operation.method is OverrideMethod.SCALE:
                result[key] *= operation.value
            elif operation.method is OverrideMethod.INCREMENT:
                result[key] += operation.value
            else:
                result[key] = operation.value
            provenance.append(
                OverrideRecord(
                    operation.target,
                    key,
                    operation.method,
                    operation.value,
                    operation.precedence,
                    before,
                    result[key],
                )
            )
    return OverrideResult(result, tuple(provenance))


class CompatibilityStep(PreprocessingStep):
    """Materialize every v5.0.6 date-boundary decision as an artifact."""

    name = "compatibility"
    provides = frozenset(
        {
            "input_gdx_gregorian_date",
            "spd_loss_tolerance",
            "directional_risk_available",
            "legacy_prss_shared_nfr",
            "fir_uses_bipole_transition",
            "directional_risk_factor",
        }
    )

    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        source = CaseInput(case_data)
        profile = CompatibilityProfile.vspd506(source.gdx_date())
        directional = (
            source.optional_numeric("i_dateTimeRiskGroupBranch")
            if profile.directional_risk_available
            else {}
        )
        scalar = ()
        return {
            "input_gdx_gregorian_date": SparseParameter(
                "input_gdx_gregorian_date",
                (),
                {scalar: float(profile.input_date.toordinal())},
            ),
            "spd_loss_tolerance": SparseParameter(
                "spd_loss_tolerance", (), {scalar: profile.spd_loss_tolerance}
            ),
            "directional_risk_available": SparseParameter(
                "directional_risk_available",
                (),
                {scalar: float(profile.directional_risk_available)},
            ),
            "legacy_prss_shared_nfr": SparseParameter(
                "legacy_prss_shared_nfr",
                (),
                {scalar: float(profile.legacy_prss_shared_nfr)},
            ),
            "fir_uses_bipole_transition": SparseParameter(
                "fir_uses_bipole_transition",
                (),
                {scalar: float(profile.fir_uses_bipole_transition)},
            ),
            "directional_risk_factor": SparseParameter(
                "directional_risk_factor",
                ("case", "datetime", "risk_group", "branch", "risk_class"),
                directional,
            ),
        }
