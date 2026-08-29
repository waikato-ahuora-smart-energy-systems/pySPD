"""Composed, class-based preprocessing profile for pinned vSPD 5.0.6."""

from __future__ import annotations

from collections.abc import Sequence

from pyspd.architecture import PreprocessorStep as ArchitecturePreprocessorStep
from pyspd.contracts import CaseData
from pyspd.preprocess.base import (
    PreprocessingError,
    PreprocessingPipeline,
    PreprocessingResult,
    PreprocessingSettings,
    PreprocessingStep,
)
from pyspd.preprocess.compatibility import CompatibilityStep
from pyspd.preprocess.constraints import ConstraintRiskStep
from pyspd.preprocess.losses import LossCurveStep
from pyspd.preprocess.offers import OfferBidLoadStep
from pyspd.preprocess.topology import TopologyStep


class Vspd506Preprocessor(ArchitecturePreprocessorStep):
    """Deterministic preprocessing façade with independently replaceable steps."""

    supported_formulations = frozenset({"vspd-v5.0.6"})

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
                ConstraintRiskStep(),
            )
        )

    def transform(self, case_data: CaseData) -> PreprocessingResult:
        if case_data.formulation_id not in self.supported_formulations:
            raise PreprocessingError(
                f"unsupported preprocessing formulation: {case_data.formulation_id}"
            )
        return self.pipeline.run(case_data, self.settings)
