"""Independent invariant checks over immutable preprocessing artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pyspd.preprocess.base import PreprocessingResult


@dataclass(frozen=True, slots=True)
class InvariantCheck:
    name: str
    observations: int
    violations: tuple[str, ...]
    maximum_error: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.violations


@dataclass(frozen=True, slots=True)
class InvariantReport:
    checks: tuple[InvariantCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def logical_sha256(self) -> str:
        payload = [
            {
                "name": check.name,
                "observations": check.observations,
                "violations": list(check.violations),
                "maximum_error": check.maximum_error.hex(),
            }
            for check in self.checks
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def validate_preprocessing_invariants(
    result: PreprocessingResult,
    *,
    tolerance: float = 1e-12,
) -> InvariantReport:
    """Recompute structural/numeric closure without consulting step internals."""
    checks: list[InvariantCheck] = []

    nodes = result.set("node").members
    node_bus = result.set("node_bus").members
    node_island = result.set("node_island").members
    missing_bus = tuple(
        repr(node)
        for node in sorted(nodes)
        if not any(mapping[:3] == node for mapping in node_bus)
    )
    missing_island = tuple(
        repr(node)
        for node in sorted(nodes)
        if not any(mapping[:3] == node for mapping in node_island)
    )
    checks.append(
        InvariantCheck(
            "node-domain-closure",
            len(nodes),
            (*missing_bus, *missing_island),
        )
    )

    allocation = result.parameter("bus_node_allocation_factor").values
    buses = result.set("bus").members
    errors: list[float] = []
    allocation_violations: list[str] = []
    for bus in sorted(buses):
        values = [value for key, value in allocation.items() if key[:3] == bus]
        if not values:
            continue
        error = abs(sum(values) - 1.0)
        errors.append(error)
        if error > tolerance:
            allocation_violations.append(f"{bus!r}:sum={sum(values)!r}")
    checks.append(
        InvariantCheck(
            "bus-allocation-normalization",
            len(errors),
            tuple(allocation_violations),
            max(errors, default=0.0),
        )
    )

    branch_definitions = result.set("branch_bus_definition").members
    branches = result.set("branch").members
    active_violations = tuple(
        repr(branch)
        for branch in sorted(branches)
        if not any(definition[:3] == branch for definition in branch_definitions)
    )
    checks.append(
        InvariantCheck(
            "active-branch-endpoint-closure", len(branches), active_violations
        )
    )

    valid_segments = result.set("valid_loss_segment").members
    widths = result.parameter("ac_branch_loss_mw").values
    negative_widths = tuple(
        f"{key!r}:{value!r}"
        for key, value in sorted(widths.items())
        if key in valid_segments and value < -tolerance
    )
    checks.append(
        InvariantCheck("loss-curve-monotonicity", len(widths), negative_widths)
    )

    offer_blocks = result.set("generation_offer_block").members
    positive_offers = result.set("positive_energy_offer").members
    projected_offers = frozenset(key[:3] for key in offer_blocks)
    offer_projection_errors = tuple(
        [
            f"missing-positive-offer:{key!r}"
            for key in sorted(projected_offers - positive_offers)
        ]
        + [
            f"extra-positive-offer:{key!r}"
            for key in sorted(positive_offers - projected_offers)
        ]
    )
    bids = result.set("bid").members
    bid_blocks = result.set("demand_bid_block").members
    invalid_bid_blocks = tuple(
        repr(key) for key in sorted(bid_blocks) if key[:3] not in bids
    )
    checks.append(
        InvariantCheck(
            "participant-block-consistency",
            len(offer_blocks) + len(bid_blocks),
            (*offer_projection_errors, *invalid_bid_blocks),
        )
    )

    checkpoints = result.checkpoints
    duplicate_checkpoints = tuple(
        checkpoint.step
        for checkpoint in checkpoints
        if sum(other.step == checkpoint.step for other in checkpoints) != 1
    )
    checks.append(
        InvariantCheck(
            "checkpoint-name-uniqueness", len(checkpoints), duplicate_checkpoints
        )
    )
    return InvariantReport(tuple(checks))
