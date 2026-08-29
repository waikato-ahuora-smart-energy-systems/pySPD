"""Class-based preprocessing façade for SPD v16 sources."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pyspd.architecture import PreprocessorStep as ArchitecturePreprocessorStep
from pyspd.contracts import CaseData
from pyspd.preprocess.base import (
    Artifact,
    PreprocessingError,
    PreprocessingPipeline,
    PreprocessingResult,
    PreprocessingSettings,
    PreprocessingStep,
    SparseParameter,
)
from pyspd.preprocess.compatibility import CompatibilityStep
from pyspd.preprocess.constraints import ConstraintRiskStep
from pyspd.preprocess.input import CaseInput
from pyspd.preprocess.losses import LossCurveStep
from pyspd.preprocess.offers import OfferBidLoadStep
from pyspd.preprocess.topology import TopologyStep
from pyspd.v16.compatibility import SPD16_FORMULATION_ID, Spd16CompatibilityPolicy
from pyspd.v16.data import Spd16Case

SPD16_SOURCE_PROFILE_ID = "spd-v16.0"


class Spd16ConstraintRiskStep(ConstraintRiskStep):
    """Replace only the changed zero-input bad-price default."""

    name = "constraints_risk_scarcity_v16"

    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        output = dict(super().apply(case_data, artifacts, settings))
        bad_price = output["bad_price_factor"]
        if not isinstance(bad_price, SparseParameter):
            raise TypeError("bad_price_factor")
        raw = CaseInput(case_data).component("i_dateTimeParameter", "badPriceFactor")
        output["bad_price_factor"] = SparseParameter(
            "bad_price_factor",
            bad_price.dimensions,
            {
                key: raw.get(key, 0.0) if raw.get(key, 0.0) != 0.0 else 3.0
                for key in bad_price.values
            },
        )
        return output


class Spd16SourcePreprocessor(ArchitecturePreprocessorStep):
    """Run shared preprocessing steps with explicit v16 replacements."""

    supported_formulations = frozenset({SPD16_SOURCE_PROFILE_ID})

    def __init__(
        self,
        settings: PreprocessingSettings | None = None,
        steps: Sequence[PreprocessingStep] | None = None,
    ) -> None:
        self.settings = settings or PreprocessingSettings()
        self.pipeline = PreprocessingPipeline(
            tuple(steps)
            if steps is not None
            else (
                CompatibilityStep(),
                TopologyStep(),
                LossCurveStep(),
                OfferBidLoadStep(),
                Spd16ConstraintRiskStep(),
            )
        )

    def transform(self, case_data: CaseData) -> PreprocessingResult:
        if case_data.formulation_id not in self.supported_formulations:
            raise PreprocessingError(
                f"unsupported preprocessing formulation: {case_data.formulation_id}"
            )
        source = CaseInput(case_data)
        Spd16CompatibilityPolicy().validate(SPD16_FORMULATION_ID, source.gdx_date())
        if not source.has_symbol("i_busUnitAndKey3Match"):
            raise PreprocessingError("SPD v16 source requires i_busUnitAndKey3Match")
        return self.pipeline.run(case_data, self.settings)


class Spd16ModelPreprocessor(ArchitecturePreprocessorStep):
    """Transform canonical v16 input directly into an immutable model case."""

    supported_formulations = frozenset({SPD16_FORMULATION_ID})

    def transform(self, case_data: object) -> Spd16Case:
        if isinstance(case_data, Spd16Case):
            return case_data
        if not isinstance(case_data, CaseData):
            raise TypeError("SPD v16 preprocessing requires CaseData")
        result = Spd16SourcePreprocessor(
            PreprocessingSettings(apply_rtd_load_reconstruction=True)
        ).transform(case_data)
        return Spd16Case.from_sources(result, case_data)
