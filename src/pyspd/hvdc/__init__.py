"""Gate 6 HVDC and fixed-MIP pricing public API."""

from pyspd.hvdc.data import (
    HVDC_FORMULATION_ID,
    HvdcCase,
    HvdcData,
    HvdcDataError,
    SosRepresentation,
)
from pyspd.hvdc.diagnostics import (
    DiagnosticBundle,
    DiagnosticCapabilityError,
    HvdcDiagnosticExporter,
    PricingModelAudit,
    active_discrete_count,
    audit_pricing_model,
)
from pyspd.hvdc.formulation import (
    HvdcPreprocessor,
    HvdcPricingEngine,
    HvdcReportRenderer,
    HvdcResults,
    HvdcResultSchema,
    HvdcSolveOutcome,
    HvdcSolvePolicy,
    SolutionSnapshot,
    WarmStartAudit,
    WarmStartSnapshot,
    detect_nonphysical_hvdc,
    hvdc_formulation,
)
from pyspd.hvdc.validation import (
    FixedMipPriceCheck,
    HvdcValidationReport,
    IndependentHvdcValidator,
    portable_and_native_sos_curves_equivalent,
    validate_fixed_mip_price_finite_difference,
)

__all__ = [
    "HVDC_FORMULATION_ID",
    "DiagnosticBundle",
    "DiagnosticCapabilityError",
    "FixedMipPriceCheck",
    "HvdcCase",
    "HvdcData",
    "HvdcDataError",
    "HvdcDiagnosticExporter",
    "HvdcPreprocessor",
    "HvdcPricingEngine",
    "HvdcReportRenderer",
    "HvdcResultSchema",
    "HvdcResults",
    "HvdcSolveOutcome",
    "HvdcSolvePolicy",
    "HvdcValidationReport",
    "IndependentHvdcValidator",
    "PricingModelAudit",
    "SolutionSnapshot",
    "SosRepresentation",
    "WarmStartAudit",
    "WarmStartSnapshot",
    "active_discrete_count",
    "audit_pricing_model",
    "detect_nonphysical_hvdc",
    "hvdc_formulation",
    "portable_and_native_sos_curves_equivalent",
    "validate_fixed_mip_price_finite_difference",
]
