"""vSPD 5.0.6 AC/HVDC loss-segment and breakpoint preprocessing."""

from __future__ import annotations

from collections.abc import Mapping

from pyspd.contracts import CaseData
from pyspd.preprocess.base import (
    Artifact,
    PreprocessingError,
    PreprocessingSettings,
    PreprocessingStep,
    SparseParameter,
    SparseSet,
)
from pyspd.preprocess.input import CaseInput

LOSS_COEFFICIENT_A = 0.3101
LOSS_COEFFICIENT_C = 0.14495
LOSS_COEFFICIENT_D = 0.32247
LOSS_COEFFICIENT_E = 0.46742
LOSS_COEFFICIENT_F = 0.82247
MAX_FLOW_SEGMENT = 10000.0
FLOW_DIRECTIONS = ("forward", "backward")
LOSS_SEGMENTS = tuple(f"ls{index}" for index in range(1, 14))


class LossCurveStep(PreprocessingStep):
    name = "loss_curves"
    requires = frozenset({"branch", "ac_branch", "hvdc_link"})
    provides = frozenset(
        {
            "branch_capacity",
            "branch_resistance",
            "branch_susceptance",
            "branch_fixed_loss",
            "branch_loss_blocks",
            "loss_segment_mw",
            "loss_segment_factor",
            "valid_loss_segment",
            "loss_branch",
            "ac_branch_loss_mw",
            "ac_branch_loss_factor",
            "hvdc_breakpoint_flow",
            "hvdc_breakpoint_loss",
        }
    )

    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        source = CaseInput(case_data)
        branches = _set(artifacts, "branch")
        ac = _set(artifacts, "ac_branch")
        hvdc = _set(artifacts, "hvdc_link")
        forward = source.component("i_dateTimeBranchParameter", "forwardCap")
        backward = source.component("i_dateTimeBranchParameter", "backwardCap")
        resistance_input = source.component("i_dateTimeBranchParameter", "resistance")
        susceptance_input = source.component("i_dateTimeBranchParameter", "susceptance")
        fixed_input = source.component("i_dateTimeBranchParameter", "fixedLosses")
        blocks_input = source.component("i_dateTimeBranchParameter", "numLossTranches")

        capacity = {
            (*key, direction): values.get(key, 0.0)
            for key in branches
            for direction, values in (("forward", forward), ("backward", backward))
        }
        resistance = {
            key: resistance_input.get(key, 0.0)
            * (
                settings.use_hvdc_loss_model
                if key in hvdc
                else settings.use_ac_loss_model
            )
            for key in branches
        }
        susceptance = {key: -100.0 * susceptance_input.get(key, 0.0) for key in ac}
        block_counts = {key: int(blocks_input.get(key, 0.0)) for key in branches}
        unsupported = sorted(
            (key, count)
            for key, count in block_counts.items()
            if count not in {0, 1, 3, 6}
        )
        if unsupported:
            raise PreprocessingError(
                f"unsupported branch loss tranche count: {unsupported[:3]}"
            )
        fixed_loss = {
            key: (
                fixed_input.get(key, 0.0)
                if key in hvdc or block_counts[key] > 1
                else 0.0
            )
            * (
                settings.use_hvdc_loss_model
                if key in hvdc
                else settings.use_ac_loss_model
            )
            for key in branches
        }

        segment_mw: dict[tuple[str, ...], float] = {}
        segment_factor: dict[tuple[str, ...], float] = {}
        for key in sorted(branches):
            for direction in FLOW_DIRECTIONS:
                cap = capacity[(*key, direction)]
                count = block_counts[key]
                points, factors = _loss_points(count, cap, resistance[key])
                if key in hvdc and direction == "backward":
                    points = [0.0] * len(points)
                    factors = [0.0] * len(factors)
                for index, value in enumerate(points, start=1):
                    segment_mw[(*key, f"ls{index}", direction)] = value
                for index, value in enumerate(factors, start=1):
                    segment_factor[(*key, f"ls{index}", direction)] = value

        valid: set[tuple[str, ...]] = set()
        for key in branches:
            for direction in FLOW_DIRECTIONS:
                for index, segment in enumerate(LOSS_SEGMENTS, start=1):
                    identity = (*key, segment, direction)
                    if (
                        index == 1
                        or segment_mw.get(identity, 0.0) != 0.0
                        or segment_factor.get(identity, 0.0) != 0.0
                    ):
                        valid.add(identity)
                count = block_counts[key]
                if key in hvdc and count <= 1:
                    valid.add((*key, "ls2", direction))
                elif key in hvdc and count > 1:
                    extra = (*key, f"ls{count + 1}", direction)
                    total = sum(
                        segment_mw.get((*key, segment, direction), 0.0)
                        + segment_factor.get((*key, segment, direction), 0.0)
                        for segment in LOSS_SEGMENTS
                    )
                    if total > 0.0:
                        valid.add(extra)

        loss_branches = frozenset(
            key
            for key in branches
            if any(
                segment_factor.get((*key, segment, direction), 0.0) != 0.0
                for segment in LOSS_SEGMENTS
                for direction in FLOW_DIRECTIONS
            )
        )
        ac_width: dict[tuple[str, ...], float] = {}
        ac_factor: dict[tuple[str, ...], float] = {}
        for key in ac:
            for direction in FLOW_DIRECTIONS:
                previous = 0.0
                for segment in LOSS_SEGMENTS:
                    identity = (*key, segment, direction)
                    if identity not in valid:
                        continue
                    point = segment_mw.get(identity, 0.0)
                    ac_width[identity] = point if segment == "ls1" else point - previous
                    ac_factor[identity] = segment_factor.get(identity, 0.0)
                    previous = point

        hvdc_flow: dict[tuple[str, ...], float] = {}
        hvdc_loss: dict[tuple[str, ...], float] = {}
        for key in hvdc:
            for direction in FLOW_DIRECTIONS:
                cumulative = 0.0
                previous_point = 0.0
                for index, segment in enumerate(LOSS_SEGMENTS, start=1):
                    identity = (*key, segment, direction)
                    if identity not in valid:
                        continue
                    if index == 1:
                        hvdc_flow[identity] = 0.0
                        hvdc_loss[identity] = 0.0
                        continue
                    prior_segment = f"ls{index - 1}"
                    point = segment_mw.get((*key, prior_segment, direction), 0.0)
                    factor = segment_factor.get((*key, prior_segment, direction), 0.0)
                    cumulative += factor * (point - previous_point)
                    hvdc_flow[identity] = point
                    hvdc_loss[identity] = cumulative
                    previous_point = point

        branch_dimensions = ("case", "datetime", "branch")
        curve_dimensions = (*branch_dimensions, "segment", "direction")
        return {
            "branch_capacity": SparseParameter(
                "branch_capacity", (*branch_dimensions, "direction"), capacity
            ),
            "branch_resistance": SparseParameter(
                "branch_resistance", branch_dimensions, resistance
            ),
            "branch_susceptance": SparseParameter(
                "branch_susceptance", branch_dimensions, susceptance
            ),
            "branch_fixed_loss": SparseParameter(
                "branch_fixed_loss", branch_dimensions, fixed_loss
            ),
            "branch_loss_blocks": SparseParameter(
                "branch_loss_blocks", branch_dimensions, block_counts
            ),
            "loss_segment_mw": SparseParameter(
                "loss_segment_mw", curve_dimensions, segment_mw
            ),
            "loss_segment_factor": SparseParameter(
                "loss_segment_factor", curve_dimensions, segment_factor
            ),
            "valid_loss_segment": SparseSet(
                "valid_loss_segment", curve_dimensions, frozenset(valid)
            ),
            "loss_branch": SparseSet("loss_branch", branch_dimensions, loss_branches),
            "ac_branch_loss_mw": SparseParameter(
                "ac_branch_loss_mw", curve_dimensions, ac_width
            ),
            "ac_branch_loss_factor": SparseParameter(
                "ac_branch_loss_factor", curve_dimensions, ac_factor
            ),
            "hvdc_breakpoint_flow": SparseParameter(
                "hvdc_breakpoint_flow", curve_dimensions, hvdc_flow
            ),
            "hvdc_breakpoint_loss": SparseParameter(
                "hvdc_breakpoint_loss", curve_dimensions, hvdc_loss
            ),
        }


def _loss_points(
    count: int, capacity: float, resistance: float
) -> tuple[list[float], list[float]]:
    if count == 0:
        return [capacity], [0.0]
    if count == 1:
        return [MAX_FLOW_SEGMENT], [0.01 * resistance * capacity]
    if count == 3:
        return (
            [
                LOSS_COEFFICIENT_A * capacity,
                (1.0 - LOSS_COEFFICIENT_A) * capacity,
                MAX_FLOW_SEGMENT,
            ],
            [
                0.01 * 0.75 * LOSS_COEFFICIENT_A * resistance * capacity,
                0.01 * resistance * capacity,
                0.01 * (2.0 - 0.75 * LOSS_COEFFICIENT_A) * resistance * capacity,
            ],
        )
    return (
        [
            LOSS_COEFFICIENT_C * capacity,
            LOSS_COEFFICIENT_D * capacity,
            0.5 * capacity,
            (1.0 - LOSS_COEFFICIENT_D) * capacity,
            (1.0 - LOSS_COEFFICIENT_C) * capacity,
            MAX_FLOW_SEGMENT,
        ],
        [
            0.01 * 0.75 * LOSS_COEFFICIENT_C * resistance * capacity,
            0.01 * LOSS_COEFFICIENT_E * resistance * capacity,
            0.01 * LOSS_COEFFICIENT_F * resistance * capacity,
            0.01 * (2.0 - LOSS_COEFFICIENT_F) * resistance * capacity,
            0.01 * (2.0 - LOSS_COEFFICIENT_E) * resistance * capacity,
            0.01 * (2.0 - 0.75 * LOSS_COEFFICIENT_C) * resistance * capacity,
        ],
    )


def _set(artifacts: Mapping[str, Artifact], name: str) -> frozenset[tuple[str, ...]]:
    artifact = artifacts[name]
    if not isinstance(artifact, SparseSet):
        raise TypeError(name)
    return artifact.members
