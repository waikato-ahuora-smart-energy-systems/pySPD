"""Independent certificates for one-sided zero-flow AC-loss prices.

The production pricing engine and this validator deliberately do not share
implementation code.  The validator reconstructs the two one-sided
derivatives from source topology and loss factors, proves passivity/zero flow,
projects certified bus deltas through node allocation, and can independently
rebuild a weighted rounded publication.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from tools.gate12.evidence import EvidenceContractError

type Bus = str
type Branch = str
type Node = str

ZERO_FLOW_PRICE_CONVENTION_PROFILE = (
    "gams-pyspd-zero-flow-load-derivative-publication-v1"
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _proxy[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class ZeroFlowCaseInputs:
    """Minimal independently loaded evidence needed for one canonical case."""

    case_id: str
    date_time: str
    branches: Mapping[Branch, tuple[Bus, Bus]]
    first_loss_factors: Mapping[tuple[Branch, str], float]
    electrical_buses: frozenset[Bus]
    bus_generation: Mapping[Bus, float]
    bus_load: Mapping[Bus, float]
    branch_flow: Mapping[Branch, float] | None
    node_buses: Mapping[Node, frozenset[Bus]]
    node_bus_allocation: Mapping[tuple[Node, Bus], float]
    offer_nodes: frozenset[Node]
    bid_nodes: frozenset[Node]
    receiving_end_loss_proportion: float = 1.0

    def __post_init__(self) -> None:
        if not self.case_id or not self.date_time or not self.branches:
            raise ValueError("case, datetime, and active AC branches are required")
        if not 0.0 <= self.receiving_end_loss_proportion <= 1.0:
            raise ValueError("receiving-end loss proportion must lie in [0, 1]")
        directions = {direction for _branch, direction in self.first_loss_factors}
        if directions - {"forward", "backward"}:
            raise ValueError("loss-factor direction is invalid")
        numeric = (
            *self.first_loss_factors.values(),
            *self.bus_generation.values(),
            *self.bus_load.values(),
            *(() if self.branch_flow is None else self.branch_flow.values()),
            *self.node_bus_allocation.values(),
        )
        if any(not math.isfinite(float(value)) for value in numeric):
            raise ValueError("zero-flow evidence must be finite")
        object.__setattr__(self, "branches", _proxy(self.branches))
        object.__setattr__(self, "first_loss_factors", _proxy(self.first_loss_factors))
        object.__setattr__(self, "electrical_buses", frozenset(self.electrical_buses))
        object.__setattr__(self, "bus_generation", _proxy(self.bus_generation))
        object.__setattr__(self, "bus_load", _proxy(self.bus_load))
        if self.branch_flow is not None:
            object.__setattr__(self, "branch_flow", _proxy(self.branch_flow))
        object.__setattr__(
            self,
            "node_buses",
            MappingProxyType(
                {node: frozenset(buses) for node, buses in self.node_buses.items()}
            ),
        )
        object.__setattr__(
            self, "node_bus_allocation", _proxy(self.node_bus_allocation)
        )
        object.__setattr__(self, "offer_nodes", frozenset(self.offer_nodes))
        object.__setattr__(self, "bid_nodes", frozenset(self.bid_nodes))


@dataclass(frozen=True, slots=True)
class ZeroFlowBusObservation:
    """Analytic disposition of one material bus-price difference."""

    bus: Bus
    branch: Branch
    parent_bus: Bus
    inward_direction: str
    first_inward_loss_factor: float
    first_outward_loss_factor: float
    reference_price: float
    candidate_price: float
    expected_load_derivative: float
    expected_export_derivative: float
    candidate_residual: float
    reference_residual: float
    reference_side: str
    zero_flow_evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "bus": self.bus,
            "branch": self.branch,
            "parent_bus": self.parent_bus,
            "inward_direction": self.inward_direction,
            "first_inward_loss_factor": self.first_inward_loss_factor.hex(),
            "first_outward_loss_factor": self.first_outward_loss_factor.hex(),
            "reference_price": self.reference_price.hex(),
            "candidate_price": self.candidate_price.hex(),
            "expected_load_derivative": self.expected_load_derivative.hex(),
            "expected_export_derivative": self.expected_export_derivative.hex(),
            "candidate_residual": self.candidate_residual.hex(),
            "reference_residual": self.reference_residual.hex(),
            "reference_side": self.reference_side,
            "zero_flow_evidence": self.zero_flow_evidence,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ZeroFlowBusObservation:
        if not isinstance(payload, dict):
            raise EvidenceContractError("REQ-G12-ZERO-FLOW: invalid bus observation")
        try:
            return cls(
                bus=payload["bus"],
                branch=payload["branch"],
                parent_bus=payload["parent_bus"],
                inward_direction=payload["inward_direction"],
                first_inward_loss_factor=float.fromhex(
                    payload["first_inward_loss_factor"]
                ),
                first_outward_loss_factor=float.fromhex(
                    payload["first_outward_loss_factor"]
                ),
                reference_price=float.fromhex(payload["reference_price"]),
                candidate_price=float.fromhex(payload["candidate_price"]),
                expected_load_derivative=float.fromhex(
                    payload["expected_load_derivative"]
                ),
                expected_export_derivative=float.fromhex(
                    payload["expected_export_derivative"]
                ),
                candidate_residual=float.fromhex(payload["candidate_residual"]),
                reference_residual=float.fromhex(payload["reference_residual"]),
                reference_side=payload["reference_side"],
                zero_flow_evidence=payload["zero_flow_evidence"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: invalid bus observation"
            ) from error


@dataclass(frozen=True, slots=True)
class ZeroFlowCaseCertificate:
    """Complete fail-closed disposition for material bus and node differences."""

    case_id: str
    date_time: str
    observations: tuple[ZeroFlowBusObservation, ...]
    material_bus_identities: tuple[Bus, ...]
    certified_node_identities: tuple[Node, ...]
    unresolved_bus_reasons: Mapping[Bus, str]
    unresolved_node_reasons: Mapping[Node, str]
    maximum_node_projection_residual: float
    price_tolerance: float
    analytic_tolerance: float
    projection_tolerance: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "unresolved_bus_reasons", _proxy(self.unresolved_bus_reasons)
        )
        object.__setattr__(
            self, "unresolved_node_reasons", _proxy(self.unresolved_node_reasons)
        )

    @property
    def certified_bus_identities(self) -> tuple[Bus, ...]:
        return tuple(observation.bus for observation in self.observations)

    @property
    def passed(self) -> bool:
        return (
            not self.unresolved_bus_reasons
            and not self.unresolved_node_reasons
            and set(self.material_bus_identities) == set(self.certified_bus_identities)
            and self.maximum_node_projection_residual <= self.projection_tolerance
        )

    def certifies_bus(self, bus: str) -> bool:
        return self.passed and bus in self.certified_bus_identities

    def certifies_node(self, node: str) -> bool:
        return self.passed and node in self.certified_node_identities

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "date_time": self.date_time,
            "passed": self.passed,
            "material_bus_identities": list(self.material_bus_identities),
            "certified_node_identities": list(self.certified_node_identities),
            "unresolved_bus_reasons": dict(self.unresolved_bus_reasons),
            "unresolved_node_reasons": dict(self.unresolved_node_reasons),
            "maximum_node_projection_residual": (
                self.maximum_node_projection_residual.hex()
            ),
            "price_tolerance": self.price_tolerance.hex(),
            "analytic_tolerance": self.analytic_tolerance.hex(),
            "projection_tolerance": self.projection_tolerance.hex(),
            "observations": [item.to_dict() for item in self.observations],
        }

    @classmethod
    def from_dict(cls, payload: object) -> ZeroFlowCaseCertificate:
        if not isinstance(payload, dict):
            raise EvidenceContractError("REQ-G12-ZERO-FLOW: invalid case certificate")
        try:
            result = cls(
                case_id=payload["case_id"],
                date_time=payload["date_time"],
                observations=tuple(
                    ZeroFlowBusObservation.from_dict(item)
                    for item in payload["observations"]
                ),
                material_bus_identities=tuple(payload["material_bus_identities"]),
                certified_node_identities=tuple(payload["certified_node_identities"]),
                unresolved_bus_reasons=payload["unresolved_bus_reasons"],
                unresolved_node_reasons=payload["unresolved_node_reasons"],
                maximum_node_projection_residual=float.fromhex(
                    payload["maximum_node_projection_residual"]
                ),
                price_tolerance=float.fromhex(payload["price_tolerance"]),
                analytic_tolerance=float.fromhex(payload["analytic_tolerance"]),
                projection_tolerance=float.fromhex(payload["projection_tolerance"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: invalid case certificate"
            ) from error
        if payload.get("passed") is not result.passed:
            raise EvidenceContractError("REQ-G12-ZERO-FLOW: case disposition mismatch")
        return result


@dataclass(frozen=True, slots=True)
class PublicationContribution:
    """One canonical case's independently reconstructed node-price weight."""

    case_id: str
    date_time: str
    seconds: float
    canonical_node_price: float

    def __post_init__(self) -> None:
        if (
            not self.case_id
            or not self.date_time
            or not math.isfinite(self.seconds)
            or self.seconds < 0.0
            or not math.isfinite(self.canonical_node_price)
        ):
            raise ValueError("publication contribution is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "date_time": self.date_time,
            "seconds": self.seconds.hex(),
            "canonical_node_price": self.canonical_node_price.hex(),
        }


@dataclass(frozen=True, slots=True)
class ZeroFlowPublicationCertificate:
    """Independent weighted reconstruction of one rounded published price."""

    trading_period: str
    node: str
    reference: float
    candidate: float
    reconstructed_candidate: float
    total_seconds: float
    contribution_count: int
    decimals: int
    tolerance: float
    contributions_sha256: str

    @property
    def absolute_residual(self) -> float:
        return abs(self.candidate - self.reconstructed_candidate)

    @property
    def passed(self) -> bool:
        return self.absolute_residual <= self.tolerance

    def to_dict(self) -> dict[str, object]:
        return {
            "trading_period": self.trading_period,
            "node": self.node,
            "passed": self.passed,
            "reference": self.reference.hex(),
            "candidate": self.candidate.hex(),
            "reconstructed_candidate": self.reconstructed_candidate.hex(),
            "absolute_residual": self.absolute_residual.hex(),
            "total_seconds": self.total_seconds.hex(),
            "contribution_count": self.contribution_count,
            "decimals": self.decimals,
            "tolerance": self.tolerance.hex(),
            "contributions_sha256": self.contributions_sha256,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ZeroFlowPublicationCertificate:
        if not isinstance(payload, dict):
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: invalid publication certificate"
            )
        try:
            result = cls(
                trading_period=payload["trading_period"],
                node=payload["node"],
                reference=float.fromhex(payload["reference"]),
                candidate=float.fromhex(payload["candidate"]),
                reconstructed_candidate=float.fromhex(
                    payload["reconstructed_candidate"]
                ),
                total_seconds=float.fromhex(payload["total_seconds"]),
                contribution_count=payload["contribution_count"],
                decimals=payload["decimals"],
                tolerance=float.fromhex(payload["tolerance"]),
                contributions_sha256=payload["contributions_sha256"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: invalid publication certificate"
            ) from error
        if (
            payload.get("passed") is not result.passed
            or payload.get("absolute_residual") != result.absolute_residual.hex()
        ):
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: publication disposition mismatch"
            )
        return result


@dataclass(frozen=True, slots=True)
class ZeroFlowPriceConventionResult:
    """Hash-bound daily zero-flow and publication convention certificate."""

    trading_date: str
    source_sha256: str
    reference_result_gdx_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    topology_sha256: str
    cases: tuple[ZeroFlowCaseCertificate, ...]
    publications: tuple[ZeroFlowPublicationCertificate, ...]
    logical_sha256: str

    @property
    def passed(self) -> bool:
        return (
            bool(self.cases)
            and all(case.passed for case in self.cases)
            and all(publication.passed for publication in self.publications)
        )

    def certifies_bus(self, case_id: str, bus: str) -> bool:
        return any(
            case.case_id == case_id and case.certifies_bus(bus) for case in self.cases
        )

    def certifies_node(self, case_id: str, node: str) -> bool:
        return any(
            case.case_id == case_id and case.certifies_node(node) for case in self.cases
        )

    def certifies_publication(self, period: str, node: str) -> bool:
        return any(
            item.trading_period == period and item.node == node and item.passed
            for item in self.publications
        )

    @classmethod
    def create(
        cls,
        *,
        trading_date: str,
        source_sha256: str,
        reference_result_gdx_sha256: str,
        reference_bundle_sha256: str,
        candidate_bundle_sha256: str,
        topology_sha256: str,
        cases: tuple[ZeroFlowCaseCertificate, ...],
        publications: tuple[ZeroFlowPublicationCertificate, ...],
    ) -> ZeroFlowPriceConventionResult:
        unsigned = {
            "schema_version": 1,
            "profile": ZERO_FLOW_PRICE_CONVENTION_PROFILE,
            "trading_date": trading_date,
            "source_sha256": source_sha256,
            "reference_result_gdx_sha256": reference_result_gdx_sha256,
            "reference_bundle_sha256": reference_bundle_sha256,
            "candidate_bundle_sha256": candidate_bundle_sha256,
            "topology_sha256": topology_sha256,
            "passed": bool(cases)
            and all(case.passed for case in cases)
            and all(item.passed for item in publications),
            "cases": [case.to_dict() for case in cases],
            "publications": [item.to_dict() for item in publications],
        }
        result = cls(
            trading_date=trading_date,
            source_sha256=source_sha256,
            reference_result_gdx_sha256=reference_result_gdx_sha256,
            reference_bundle_sha256=reference_bundle_sha256,
            candidate_bundle_sha256=candidate_bundle_sha256,
            topology_sha256=topology_sha256,
            cases=cases,
            publications=publications,
            logical_sha256=_logical_sha256(unsigned),
        )
        result.validate()
        return result

    @classmethod
    def from_dict(cls, payload: object) -> ZeroFlowPriceConventionResult:
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or payload.get("profile") != ZERO_FLOW_PRICE_CONVENTION_PROFILE
            or not isinstance(payload.get("cases"), list)
            or not isinstance(payload.get("publications"), list)
        ):
            raise EvidenceContractError("REQ-G12-ZERO-FLOW: unexpected result schema")
        result = cls(
            trading_date=payload["trading_date"],
            source_sha256=payload["source_sha256"],
            reference_result_gdx_sha256=payload["reference_result_gdx_sha256"],
            reference_bundle_sha256=payload["reference_bundle_sha256"],
            candidate_bundle_sha256=payload["candidate_bundle_sha256"],
            topology_sha256=payload["topology_sha256"],
            cases=tuple(
                ZeroFlowCaseCertificate.from_dict(item) for item in payload["cases"]
            ),
            publications=tuple(
                ZeroFlowPublicationCertificate.from_dict(item)
                for item in payload["publications"]
            ),
            logical_sha256=payload["logical_sha256"],
        )
        result.validate()
        if payload.get("passed") is not result.passed:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: result disposition mismatch"
            )
        return result

    def validate(self) -> None:
        if (
            not re.fullmatch(r"[0-9]{8}", self.trading_date)
            or any(
                not _SHA256.fullmatch(value)
                for value in (
                    self.source_sha256,
                    self.reference_result_gdx_sha256,
                    self.reference_bundle_sha256,
                    self.candidate_bundle_sha256,
                    self.topology_sha256,
                    self.logical_sha256,
                )
            )
            or not self.cases
            or len({case.case_id for case in self.cases}) != len(self.cases)
            or self.logical_sha256 != _logical_sha256(self.to_dict(include_hash=False))
        ):
            raise EvidenceContractError("REQ-G12-ZERO-FLOW: invalid result")

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": ZERO_FLOW_PRICE_CONVENTION_PROFILE,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "reference_result_gdx_sha256": self.reference_result_gdx_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "topology_sha256": self.topology_sha256,
            "passed": self.passed,
            "cases": [case.to_dict() for case in self.cases],
            "publications": [item.to_dict() for item in self.publications],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class ZeroFlowPriceConventionResultStore:
    """Persist and strictly reload one immutable convention certificate."""

    def write(self, result: ZeroFlowPriceConventionResult, target: Path) -> Path:
        result.validate()
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: certificate output already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def load(self, path: Path) -> ZeroFlowPriceConventionResult:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: unreadable certificate"
            ) from error
        return ZeroFlowPriceConventionResult.from_dict(payload)


class ZeroFlowPriceConventionValidator:
    """Certify the documented load-side derivative without using model code."""

    def __init__(
        self,
        *,
        price_tolerance: float = 1e-4,
        analytic_tolerance: float = 1e-9,
        flow_tolerance: float = 1e-9,
        injection_tolerance: float = 1e-9,
        projection_tolerance: float = 1e-10,
    ) -> None:
        values = (
            price_tolerance,
            analytic_tolerance,
            flow_tolerance,
            injection_tolerance,
            projection_tolerance,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("zero-flow certificate tolerances must be finite")
        self.price_tolerance = price_tolerance
        self.analytic_tolerance = analytic_tolerance
        self.flow_tolerance = flow_tolerance
        self.injection_tolerance = injection_tolerance
        self.projection_tolerance = projection_tolerance

    def compare_case(
        self,
        *,
        inputs: ZeroFlowCaseInputs,
        reference_bus: Mapping[Bus, float],
        candidate_bus: Mapping[Bus, float],
        reference_node: Mapping[Node, float],
        candidate_node: Mapping[Node, float],
        additional_bus_identities: frozenset[Bus] = frozenset(),
    ) -> ZeroFlowCaseCertificate:
        self._validate_price_maps(
            reference_bus, candidate_bus, reference_node, candidate_node
        )
        incident: dict[Bus, list[Branch]] = defaultdict(list)
        for branch, (from_bus, to_bus) in inputs.branches.items():
            incident[from_bus].append(branch)
            incident[to_bus].append(branch)

        unknown_additional = additional_bus_identities - set(reference_bus)
        if unknown_additional:
            raise ValueError("additional bus identity is absent from the price map")
        material_buses = tuple(
            sorted(
                {
                    bus
                    for bus in reference_bus
                    if abs(candidate_bus[bus] - reference_bus[bus])
                    > self.price_tolerance
                }
                | set(additional_bus_identities)
            )
        )
        observations: list[ZeroFlowBusObservation] = []
        unresolved_bus: dict[Bus, str] = {}
        for bus in material_buses:
            observation, reason = self._bus_observation(
                inputs=inputs,
                incident=incident,
                bus=bus,
                reference_bus=reference_bus,
                candidate_bus=candidate_bus,
            )
            if observation is None:
                assert reason is not None
                unresolved_bus[bus] = reason
            else:
                observations.append(observation)

        # A zero-loss leaf can inherit its price from another material bus.
        # Accept that chain only when it eventually reaches a non-material
        # anchor; otherwise a cycle could certify itself without evidence.
        observation_by_bus = {item.bus: item for item in observations}
        material_set = set(material_buses)

        def anchored(bus: Bus, visiting: frozenset[Bus] = frozenset()) -> bool:
            if bus in visiting:
                return False
            observation = observation_by_bus.get(bus)
            if observation is None:
                return False
            if observation.parent_bus not in material_set:
                return True
            return anchored(observation.parent_bus, visiting | {bus})

        anchored_observations: list[ZeroFlowBusObservation] = []
        for item in observations:
            if anchored(item.bus):
                anchored_observations.append(item)
            else:
                unresolved_bus[item.bus] = "unanchored-zero-flow-component"
        observations = anchored_observations

        certified_buses = {observation.bus for observation in observations}
        bus_delta = {
            bus: candidate_bus[bus] - reference_bus[bus] for bus in reference_bus
        }
        material_nodes = tuple(
            sorted(
                node
                for node in reference_node
                if abs(candidate_node[node] - reference_node[node])
                > self.price_tolerance
            )
        )
        certified_nodes: list[Node] = []
        unresolved_node: dict[Node, str] = {}
        maximum_projection_residual = 0.0
        for node in material_nodes:
            allocations = {
                bus: weight
                for (item_node, bus), weight in inputs.node_bus_allocation.items()
                if item_node == node
            }
            if not allocations:
                unresolved_node[node] = "missing-node-bus-allocation"
                continue
            material_allocated = {
                bus
                for bus, weight in allocations.items()
                if abs(weight * bus_delta.get(bus, 0.0)) > self.price_tolerance
            }
            if not material_allocated <= certified_buses:
                unresolved_node[node] = "uncertified-material-bus-contribution"
                continue
            projected = sum(
                weight * bus_delta.get(bus, 0.0) for bus, weight in allocations.items()
            )
            observed = candidate_node[node] - reference_node[node]
            residual = abs(projected - observed)
            maximum_projection_residual = max(maximum_projection_residual, residual)
            if residual > self.projection_tolerance:
                unresolved_node[node] = "node-allocation-projection-mismatch"
                continue
            certified_nodes.append(node)

        return ZeroFlowCaseCertificate(
            case_id=inputs.case_id,
            date_time=inputs.date_time,
            observations=tuple(observations),
            material_bus_identities=material_buses,
            certified_node_identities=tuple(certified_nodes),
            unresolved_bus_reasons=unresolved_bus,
            unresolved_node_reasons=unresolved_node,
            maximum_node_projection_residual=maximum_projection_residual,
            price_tolerance=self.price_tolerance,
            analytic_tolerance=self.analytic_tolerance,
            projection_tolerance=self.projection_tolerance,
        )

    def _bus_observation(
        self,
        *,
        inputs: ZeroFlowCaseInputs,
        incident: Mapping[Bus, list[Branch]],
        bus: Bus,
        reference_bus: Mapping[Bus, float],
        candidate_bus: Mapping[Bus, float],
    ) -> tuple[ZeroFlowBusObservation | None, str | None]:
        branches = tuple(sorted(incident.get(bus, ())))
        if not branches:
            return None, "missing-incident-branch"
        if bus not in inputs.electrical_buses:
            return None, "electrically-disconnected-leaf"
        if (
            abs(inputs.bus_generation.get(bus, 0.0)) > self.injection_tolerance
            or abs(inputs.bus_load.get(bus, 0.0)) > self.injection_tolerance
        ):
            return None, "nonzero-leaf-injection"

        if inputs.branch_flow is not None:
            if any(branch not in inputs.branch_flow for branch in branches):
                return None, "missing-branch-flow-evidence"
            if any(
                abs(inputs.branch_flow[branch]) > self.flow_tolerance
                for branch in branches
            ):
                return None, "nonzero-branch-flow"
            zero_flow_evidence = "reported-branch-flow"
        elif len(branches) == 1:
            zero_flow_evidence = "zero-injection-leaf-balance"
        else:
            return None, "missing-component-flow-evidence"

        branch = self._passive_boundary_branch(inputs, branches)
        if branch is None:
            return None, "not-single-loss-boundary-component"

        from_bus, to_bus = inputs.branches[branch]
        if bus == to_bus:
            parent = from_bus
            inward = "forward"
            outward = "backward"
        elif bus == from_bus:
            parent = to_bus
            inward = "backward"
            outward = "forward"
        else:  # pragma: no cover - impossible after incident construction
            return None, "branch-topology-mismatch"
        if parent not in reference_bus or parent not in candidate_bus:
            return None, "missing-parent-price"
        inward_factor = inputs.first_loss_factors.get((branch, inward), 0.0)
        outward_factor = inputs.first_loss_factors.get((branch, outward), 0.0)
        if inward_factor < 0.0 or outward_factor < 0.0:
            return None, "invalid-negative-first-loss-factor"
        if (inward_factor == 0.0) != (outward_factor == 0.0):
            return None, "incomplete-first-loss-factor"

        share = inputs.receiving_end_loss_proportion
        load_denominator = 1.0 - share * inward_factor
        export_denominator = 1.0 + (1.0 - share) * outward_factor
        if load_denominator <= 0.0 or export_denominator <= 0.0:
            return None, "invalid-one-sided-loss-derivative"
        expected_candidate_load = (
            candidate_bus[parent]
            * (1.0 + (1.0 - share) * inward_factor)
            / load_denominator
        )
        expected_reference_load = (
            reference_bus[parent]
            * (1.0 + (1.0 - share) * inward_factor)
            / load_denominator
        )
        expected_reference_export = (
            reference_bus[parent] * (1.0 - share * outward_factor) / export_denominator
        )
        candidate_residual = abs(candidate_bus[bus] - expected_candidate_load)
        if candidate_residual > self.analytic_tolerance:
            return None, "candidate-not-load-derivative"
        load_residual = abs(reference_bus[bus] - expected_reference_load)
        export_residual = abs(reference_bus[bus] - expected_reference_export)
        if min(load_residual, export_residual) > self.analytic_tolerance:
            return None, "reference-not-kink-derivative"
        reference_side = "load" if load_residual <= export_residual else "export"
        return (
            ZeroFlowBusObservation(
                bus=bus,
                branch=branch,
                parent_bus=parent,
                inward_direction=inward,
                first_inward_loss_factor=inward_factor,
                first_outward_loss_factor=outward_factor,
                reference_price=reference_bus[bus],
                candidate_price=candidate_bus[bus],
                expected_load_derivative=expected_candidate_load,
                expected_export_derivative=expected_reference_export,
                candidate_residual=candidate_residual,
                reference_residual=min(load_residual, export_residual),
                reference_side=reference_side,
                zero_flow_evidence=zero_flow_evidence,
            ),
            None,
        )

    def canonical_load_price(
        self,
        *,
        inputs: ZeroFlowCaseInputs,
        reference_bus: Mapping[Bus, float],
        bus: Bus,
    ) -> float:
        """Reconstruct one load-side price through an anchored passive tree."""

        incident: dict[Bus, list[Branch]] = defaultdict(list)
        for branch, (from_bus, to_bus) in inputs.branches.items():
            incident[from_bus].append(branch)
            incident[to_bus].append(branch)
        memo: dict[Bus, float] = {}

        def visit(item: Bus, visiting: frozenset[Bus]) -> float:
            if item in memo:
                return memo[item]
            if item in visiting:
                raise EvidenceContractError(
                    "REQ-G12-ZERO-FLOW: unanchored passive component"
                )
            branches = tuple(sorted(incident.get(item, ())))
            if (
                not branches
                or item not in inputs.electrical_buses
                or abs(inputs.bus_generation.get(item, 0.0))
                > self.injection_tolerance
                or abs(inputs.bus_load.get(item, 0.0)) > self.injection_tolerance
                or inputs.branch_flow is not None
                and (
                    any(branch not in inputs.branch_flow for branch in branches)
                    or any(
                        abs(inputs.branch_flow[branch]) > self.flow_tolerance
                        for branch in branches
                    )
                )
            ):
                return reference_bus[item]
            branch = self._passive_boundary_branch(inputs, branches)
            if branch is None:
                return reference_bus[item]
            from_bus, to_bus = inputs.branches[branch]
            if item == to_bus:
                parent, inward, outward = from_bus, "forward", "backward"
            else:
                parent, inward, outward = to_bus, "backward", "forward"
            inward_factor = inputs.first_loss_factors.get((branch, inward), 0.0)
            outward_factor = inputs.first_loss_factors.get((branch, outward), 0.0)
            share = inputs.receiving_end_loss_proportion
            load_denominator = 1.0 - share * inward_factor
            export_denominator = 1.0 + (1.0 - share) * outward_factor
            if (
                inward_factor < 0.0
                or outward_factor < 0.0
                or (inward_factor == 0.0) != (outward_factor == 0.0)
                or load_denominator <= 0.0
                or export_denominator <= 0.0
            ):
                return reference_bus[item]
            expected_load = (
                reference_bus[parent] * (1.0 + (1.0 - share) * inward_factor)
                / load_denominator
            )
            expected_export = (
                reference_bus[parent] * (1.0 - share * outward_factor)
                / export_denominator
            )
            if min(
                abs(reference_bus[item] - expected_load),
                abs(reference_bus[item] - expected_export),
            ) > self.analytic_tolerance:
                raise EvidenceContractError(
                    "REQ-G12-ZERO-FLOW: historical bus is not on a valid kink side"
                )
            # A positive-loss edge is the independently observed kink
            # boundary.  Only zero-loss transformer links recurse; this both
            # propagates the load-side convention through a passive tree and
            # rejects an unanchored zero-loss cycle.
            parent_price = (
                reference_bus[parent]
                if inward_factor > 0.0 or outward_factor > 0.0
                else visit(parent, visiting | {item})
            )
            value = (
                parent_price * (1.0 + (1.0 - share) * inward_factor)
                / load_denominator
            )
            memo[item] = value
            return value

        return visit(bus, frozenset())

    @staticmethod
    def _passive_boundary_branch(
        inputs: ZeroFlowCaseInputs, branches: tuple[Branch, ...]
    ) -> Branch | None:
        if len(branches) == 1:
            return branches[0]
        positive = [
            branch
            for branch in branches
            if inputs.first_loss_factors.get((branch, "forward"), 0.0) > 0.0
            or inputs.first_loss_factors.get((branch, "backward"), 0.0) > 0.0
        ]
        zero_loss = [
            branch
            for branch in branches
            if inputs.first_loss_factors.get((branch, "forward"), 0.0) == 0.0
            and inputs.first_loss_factors.get((branch, "backward"), 0.0) == 0.0
        ]
        if len(positive) == 1 and len(zero_loss) == len(branches) - 1:
            return positive[0]
        return None

    def compare_publication(
        self,
        *,
        trading_period: str,
        node: str,
        reference: float,
        candidate: float,
        contributions: tuple[PublicationContribution, ...],
        decimals: int,
    ) -> ZeroFlowPublicationCertificate:
        if (
            not trading_period
            or not node
            or not isinstance(decimals, int)
            or isinstance(decimals, bool)
            or decimals < 0
            or any(not math.isfinite(value) for value in (reference, candidate))
        ):
            raise ValueError("published price evidence is invalid")
        total_seconds = sum(item.seconds for item in contributions)
        if not contributions or total_seconds <= 0.0:
            raise ValueError("positive publication weight is required")
        reconstructed = round(
            sum(item.seconds * item.canonical_node_price for item in contributions)
            / total_seconds,
            decimals,
        )
        tolerance = max(0.5 * 10.0 ** (-decimals), self.price_tolerance)
        contributions_sha256 = _logical_sha256(
            [item.to_dict() for item in contributions]
        )
        return ZeroFlowPublicationCertificate(
            trading_period=trading_period,
            node=node,
            reference=reference,
            candidate=candidate,
            reconstructed_candidate=reconstructed,
            total_seconds=total_seconds,
            contribution_count=len(contributions),
            decimals=decimals,
            tolerance=tolerance,
            contributions_sha256=contributions_sha256,
        )

    @staticmethod
    def _validate_price_maps(
        reference_bus: Mapping[Bus, float],
        candidate_bus: Mapping[Bus, float],
        reference_node: Mapping[Node, float],
        candidate_node: Mapping[Node, float],
    ) -> None:
        if (
            not reference_bus
            or set(reference_bus) != set(candidate_bus)
            or not reference_node
            or set(reference_node) != set(candidate_node)
        ):
            raise ValueError("reference and candidate price identities must match")
        if any(
            not math.isfinite(float(value))
            for mapping in (
                reference_bus,
                candidate_bus,
                reference_node,
                candidate_node,
            )
            for value in mapping.values()
        ):
            raise ValueError("prices must be finite")
