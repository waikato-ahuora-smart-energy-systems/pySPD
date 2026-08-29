"""Immutable normalized data for Gate 6 HVDC and discrete behavior."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from types import MappingProxyType

from pyspd.contracts import CaseData
from pyspd.network.data import NetworkCase
from pyspd.preprocess import PreprocessingResult
from pyspd.preprocess.input import CaseInput, nonzero

type Key = tuple[str, ...]

HVDC_FORMULATION_ID = "vspd-v5.0.6-hvdc"


class SosRepresentation(StrEnum):
    PORTABLE = "portable-binary"
    NATIVE = "native-sos2"


class HvdcDataError(ValueError):
    """Normalized HVDC data violates a model invariant."""


def _proxy[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class HvdcData:
    links: frozenset[Key]
    sending_bus: frozenset[Key]
    receiving_bus: frozenset[Key]
    link_bus: frozenset[Key]
    breakpoints: frozenset[Key]
    breakpoint_order: Mapping[Key, float]
    breakpoint_flow: Mapping[Key, float]
    breakpoint_loss: Mapping[Key, float]
    lambda_weight: Mapping[Key, float]
    capacity: Mapping[Key, float]
    discrete_bid_blocks: frozenset[Key] = frozenset()
    link_direction: Mapping[Key, str] = field(default_factory=dict)
    enforce_sos2: bool = False
    enforce_flow_direction: bool = False
    sos_representation: SosRepresentation = SosRepresentation.PORTABLE
    circulation_tolerance: float = 0.005
    nonphysical_loss_tolerance: float = 0.005
    use_hvdc_branch_limits: bool = True

    def __post_init__(self) -> None:
        for name in (
            "links",
            "sending_bus",
            "receiving_bus",
            "link_bus",
            "breakpoints",
            "discrete_bid_blocks",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        for name in (
            "breakpoint_order",
            "breakpoint_flow",
            "breakpoint_loss",
            "lambda_weight",
            "capacity",
            "link_direction",
        ):
            object.__setattr__(self, name, _proxy(getattr(self, name)))
        object.__setattr__(
            self, "sos_representation", SosRepresentation(self.sos_representation)
        )
        self._validate()

    def _validate(self) -> None:
        if {key[:3] for key in self.breakpoints} != set(self.links):
            raise HvdcDataError("every HVDC link requires at least one breakpoint")
        for name in (
            "breakpoint_order",
            "breakpoint_flow",
            "breakpoint_loss",
            "lambda_weight",
        ):
            if set(getattr(self, name)) != set(self.breakpoints):
                raise HvdcDataError(f"{name} does not cover HVDC breakpoints")
        if set(self.capacity) != set(self.links):
            raise HvdcDataError("capacity does not cover HVDC links")
        if set(self.link_direction) != set(self.links):
            raise HvdcDataError("direction does not cover HVDC links")
        if any(value < 0.0 for value in self.capacity.values()):
            raise HvdcDataError("HVDC capacity must be nonnegative")
        if any(value <= 0.0 for value in self.lambda_weight.values()):
            raise HvdcDataError("lambda weights must be positive")
        numeric = (
            self.breakpoint_order,
            self.breakpoint_flow,
            self.breakpoint_loss,
            self.lambda_weight,
            self.capacity,
        )
        if any(
            not math.isfinite(float(value))
            for mapping in numeric
            for value in mapping.values()
        ):
            raise HvdcDataError("all HVDC numeric inputs must be finite")
        for link in self.links:
            ordered = sorted(
                (self.breakpoint_order[key], key)
                for key in self.breakpoints
                if key[:3] == link
            )
            if len({order for order, _key in ordered}) != len(ordered):
                raise HvdcDataError("HVDC breakpoint order must be unique per link")
            flows = [self.breakpoint_flow[key] for _order, key in ordered]
            losses = [self.breakpoint_loss[key] for _order, key in ordered]
            if flows != sorted(flows) or losses != sorted(losses):
                raise HvdcDataError("HVDC breakpoint curves must be nondecreasing")
        if self.circulation_tolerance < 0.0 or self.nonphysical_loss_tolerance < 0.0:
            raise HvdcDataError("detector tolerances must be nonnegative")

    def with_mip_enforcement(self) -> HvdcData:
        return replace(self, enforce_sos2=True, enforce_flow_direction=True)

    @classmethod
    def from_sources(
        cls, result: PreprocessingResult, case_data: CaseData
    ) -> HvdcData:
        source = CaseInput(case_data)
        links = result.set("hvdc_link").members
        valid = frozenset(
            key
            for key in result.set("valid_loss_segment").members
            if key[:3] in links
        )
        breakpoints = frozenset(key[:4] for key in valid)
        flow_input = result.parameter("hvdc_breakpoint_flow")
        loss_input = result.parameter("hvdc_breakpoint_loss")
        segment_order = {
            segment: float(index)
            for index, segment in enumerate(
                sorted({key[3] for key in breakpoints}, key=_segment_number), start=1
            )
        }
        branch_from = result.set("branch_from_bus").members
        branch_to = result.set("branch_to_bus").members
        sending = frozenset(key for key in branch_from if key[:3] in links)
        receiving = frozenset(key for key in branch_to if key[:3] in links)
        directions: dict[Key, str] = {}
        for link in links:
            from_bus = next(key[3] for key in sending if key[:3] == link)
            to_bus = next(key[3] for key in receiving if key[:3] == link)
            directions[link] = (
                "forward" if (from_bus, to_bus) < (to_bus, from_bus) else "backward"
            )
        discrete_bids = {
            key
            for key in result.set("demand_bid_block").members
            if nonzero(
                source.component("i_dateTimeBidParameter", "discrete").get(
                    key[:3], 0.0
                )
            )
        }
        return cls(
            links=links,
            sending_bus=sending,
            receiving_bus=receiving,
            link_bus=frozenset(sending | receiving),
            breakpoints=breakpoints,
            breakpoint_order={key: segment_order[key[3]] for key in breakpoints},
            breakpoint_flow={
                key: sum(
                    flow_input.get((*key, direction))
                    for direction in ("forward", "backward")
                    if (*key, direction) in valid
                )
                for key in breakpoints
            },
            breakpoint_loss={
                key: sum(
                    loss_input.get((*key, direction))
                    for direction in ("forward", "backward")
                    if (*key, direction) in valid
                )
                for key in breakpoints
            },
            lambda_weight={
                key: float(
                    sum(
                        (*key, direction) in valid
                        for direction in ("forward", "backward")
                    )
                )
                for key in breakpoints
            },
            capacity={
                link: result.parameter("branch_capacity").get((*link, "forward"))
                for link in links
            },
            discrete_bid_blocks=frozenset(discrete_bids),
            link_direction=directions,
            circulation_tolerance=result.parameter("spd_loss_tolerance").get(()),
            nonphysical_loss_tolerance=result.parameter("spd_loss_tolerance").get(
                ()
            ),
        )


@dataclass(frozen=True, slots=True)
class HvdcCase(NetworkCase):
    hvdc: HvdcData | None = None
    formulation_id: str = field(default=HVDC_FORMULATION_ID, init=False, repr=False)

    def __post_init__(self) -> None:
        super(HvdcCase, self).__post_init__()
        if self.hvdc is None:
            raise HvdcDataError("HvdcCase requires HvdcData")
        assert self.network is not None
        if not self.hvdc.links <= self.network.branches:
            raise HvdcDataError("HVDC link lies outside the active branch domain")
        if not self.hvdc.discrete_bid_blocks <= self.bid_blocks:
            raise HvdcDataError("discrete bid block lies outside the bid domain")

    @classmethod
    def from_sources(
        cls, result: PreprocessingResult, case_data: CaseData
    ) -> HvdcCase:
        network = NetworkCase.from_sources(result, case_data)
        values = {
            item.name: getattr(network, item.name)
            for item in fields(NetworkCase)
            if item.init
        }
        return cls(**values, hvdc=HvdcData.from_sources(result, case_data))


def _segment_number(value: str) -> int:
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else 0
