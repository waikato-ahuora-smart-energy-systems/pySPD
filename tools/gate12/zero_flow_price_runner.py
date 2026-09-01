"""GDX-backed runner for the independent zero-flow price certificate."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore
from tools.gate12.zero_flow_price_convention import (
    PublicationContribution,
    ZeroFlowCaseInputs,
    ZeroFlowPriceConventionResult,
    ZeroFlowPriceConventionValidator,
    _logical_sha256,
)

_SOURCE_SYMBOLS = (
    "i_dateTimeBranchDefn",
    "i_dateTimeBranchParameter",
    "i_dateTimeOfferNode",
    "i_dateTimeBidNode",
    "i_dateTimeBusElectricalIsland",
)
_RESULT_SYMBOLS = (
    "case2dt2tp",
    "casefileseconds",
    "nodeBus",
    "nodeBusAllocationFactor",
    "offer",
    "bus",
    "pyspd_gate12_repaired_bus_price",
    "o_nodePrice_TP",
    "o_busGeneration_TP",
    "o_busLoad_TP",
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _surface_mapping(payload: bytes, *, surface: str) -> dict[tuple[str, ...], float]:
    try:
        rows = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceContractError(
            f"REQ-G12-ZERO-FLOW: unreadable {surface} surface"
        ) from error
    if not isinstance(rows, list):
        raise EvidenceContractError(f"REQ-G12-ZERO-FLOW: {surface} must be a mapping")
    output: dict[tuple[str, ...], float] = {}
    for row in rows:
        try:
            key = tuple(row["identity"])
            value = float.fromhex(row["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise EvidenceContractError(
                f"REQ-G12-ZERO-FLOW: invalid {surface} row"
            ) from error
        if key in output:
            raise EvidenceContractError(
                f"REQ-G12-ZERO-FLOW: duplicate {surface} identity"
            )
        output[key] = value
    return output


def _published_energy(payload: bytes) -> dict[tuple[str, str], float]:
    try:
        document = json.loads(payload)
        return {
            tuple(row["identity"]): float.fromhex(row["value"])
            for row in document["energy"]
        }
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise EvidenceContractError(
            "REQ-G12-ZERO-FLOW: invalid published energy surface"
        ) from error


def _reported_branch_flow(payload: bytes) -> dict[str, float]:
    try:
        document = json.loads(payload)
        rows = document["branch"]["rows"]
        return {
            str(row["branch"]).split("|")[-1]: float(row["flow_mw"]) for row in rows
        }
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise EvidenceContractError(
            "REQ-G12-ZERO-FLOW: invalid candidate branch-flow report"
        ) from error


def _report_bus_price_targets(reference: bytes, candidate: bytes) -> frozenset[str]:
    """Return buses whose full candidate falls outside the Authority display bin."""

    try:
        expected_document = json.loads(reference)
        actual_document = json.loads(candidate)
        table_name = next(
            name for name in expected_document if name.endswith("_BusResults_TP")
        )
        expected = {
            (row["CaseID"], row["DateTime"], row["Bus"]): Decimal(row["Price ($/MWh)"])
            for row in expected_document[table_name]["rows"]
        }
        actual = {
            (row["case_id"], row["date_time"], row["bus"]): Decimal(
                row["repaired_price_nzd_per_mwh"]
            )
            for row in actual_document["bus"]["rows"]
        }
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        StopIteration,
        TypeError,
    ) as error:
        raise EvidenceContractError(
            "REQ-G12-ZERO-FLOW: invalid bus report precision evidence"
        ) from error
    targets = set()
    for key in set(expected) & set(actual):
        exponent = expected[key].as_tuple().exponent
        if not isinstance(exponent, int):  # pragma: no cover - finite Decimal
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: invalid Authority bus-price precision"
            )
        half_unit = Decimal(5).scaleb(exponent - 1)
        if abs(actual[key] - expected[key]) > half_unit:
            targets.add(key[2])
    return frozenset(targets)


class _GdxEvidence:
    """Selective, memory-bounded projection of the two governed GDX files."""

    def __init__(
        self, *, source_path: Path, result_path: Path, system_directory: Path
    ) -> None:
        try:
            from gams import transfer as gt
        except ImportError as error:  # pragma: no cover - dependency boundary
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: GAMS transfer dependency is unavailable"
            ) from error
        source = gt.Container(system_directory=str(system_directory))
        result = gt.Container(system_directory=str(system_directory))
        try:
            source.read(str(source_path), symbols=list(_SOURCE_SYMBOLS))
            result.read(str(result_path), symbols=list(_RESULT_SYMBOLS))
        except Exception as error:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: governed GDX evidence cannot be loaded"
            ) from error

        def rows(container: Any, name: str) -> Any:
            frame = container[name].records
            if frame is None:
                raise EvidenceContractError(
                    f"REQ-G12-ZERO-FLOW: GDX symbol {name} has no records"
                )
            return frame

        self.case_period = {
            (str(row.ca), str(row.dt)): str(row.tp)
            for row in rows(result, "case2dt2tp").itertuples(index=False)
        }
        self.case_seconds = {
            (str(row.ca), str(row.tp)): float(row.value)
            for row in rows(result, "casefileseconds").itertuples(index=False)
        }
        self.buses = {
            (str(row.ca), str(row.dt), str(row.b))
            for row in rows(result, "bus").itertuples(index=False)
        }
        self.node_buses: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        for row in rows(result, "nodeBus").itertuples(index=False):
            self.node_buses[(str(row.ca), str(row.dt), str(row.n))].add(str(row.b))
        self.allocations = {
            (str(row.ca), str(row.dt), str(row.n), str(row.b)): float(row.value)
            for row in rows(result, "nodeBusAllocationFactor").itertuples(index=False)
        }
        self.active_offers = {
            (str(row.ca), str(row.dt), str(row.o))
            for row in rows(result, "offer").itertuples(index=False)
        }
        self.bus_price = self._numeric(
            rows(result, "pyspd_gate12_repaired_bus_price"), "b"
        )
        self.node_price = self._numeric(rows(result, "o_nodePrice_TP"), "n")
        self.bus_generation = self._numeric(rows(result, "o_busGeneration_TP"), "b")
        self.bus_load = self._numeric(rows(result, "o_busLoad_TP"), "b")

        case_ids = {case for case, _date_time in self.case_period}
        self.parameters = {
            (str(row.ca), str(row.dt), str(row.br), str(row.brPar)): float(row.value)
            for row in rows(source, "i_dateTimeBranchParameter").itertuples(index=False)
            if str(row.ca) in case_ids
        }
        self.definitions = tuple(
            (str(row.ca), str(row.dt), str(row.br), str(row.b1), str(row.b2))
            for row in rows(source, "i_dateTimeBranchDefn").itertuples(index=False)
            if str(row.ca) in case_ids
        )
        self.offer_node = {
            (str(row.ca), str(row.dt), str(row.o)): str(row.n)
            for row in rows(source, "i_dateTimeOfferNode").itertuples(index=False)
            if str(row.ca) in case_ids
        }
        self.bid_nodes = {
            (str(row.ca), str(row.dt), str(row.n))
            for row in rows(source, "i_dateTimeBidNode").itertuples(index=False)
            if str(row.ca) in case_ids
        }
        self.electrical = {
            (str(row.ca), str(row.dt), str(row.b)): float(row.value)
            for row in rows(source, "i_dateTimeBusElectricalIsland").itertuples(
                index=False
            )
            if str(row.ca) in case_ids
        }
        self._definitions_by_case: dict[tuple[str, str], list[tuple[str, str, str]]] = (
            defaultdict(list)
        )
        for case, date_time, branch, from_bus, to_bus in self.definitions:
            self._definitions_by_case[(case, date_time)].append(
                (branch, from_bus, to_bus)
            )

    @staticmethod
    def _numeric(frame: Any, identity: str) -> dict[tuple[str, str, str], float]:
        return {
            (str(row.ca), str(row.dt), str(getattr(row, identity))): float(row.value)
            for row in frame.itertuples(index=False)
        }

    def case_inputs(
        self,
        case_id: str,
        date_time: str,
        *,
        branch_flow: Mapping[str, float] | None,
    ) -> ZeroFlowCaseInputs:
        prefix = (case_id, date_time)
        branches: dict[str, tuple[str, str]] = {}
        factors: dict[tuple[str, str], float] = {}
        for branch, from_bus, to_bus in self._definitions_by_case[prefix]:
            base = (*prefix, branch)
            if (
                self.parameters.get((*base, "isOpen"), 0.0) != 0.0
                or self.parameters.get((*base, "forwardCap"), 0.0) == 0.0
                or self.parameters.get((*base, "backwardCap"), 0.0) == 0.0
                or self.parameters.get((*base, "HVDCbranch"), 0.0) != 0.0
                or (*prefix, from_bus) not in self.buses
                or (*prefix, to_bus) not in self.buses
            ):
                continue
            branches[branch] = (from_bus, to_bus)
            for direction, capacity_name in (
                ("forward", "forwardCap"),
                ("backward", "backwardCap"),
            ):
                capacity = self.parameters[(*base, capacity_name)]
                resistance = self.parameters.get((*base, "resistance"), 0.0)
                count = int(self.parameters.get((*base, "numLossTranches"), 0.0))
                coefficient = {
                    0: 0.0,
                    1: 1.0,
                    3: 0.75 * 0.3101,
                    6: 0.75 * 0.14495,
                }.get(count)
                if coefficient is None:
                    raise EvidenceContractError(
                        "REQ-G12-ZERO-FLOW: unsupported source loss-tranche count"
                    )
                factors[(branch, direction)] = (
                    0.01 * coefficient * resistance * capacity
                )
        node_buses = {
            node: frozenset(buses)
            for (case, time, node), buses in self.node_buses.items()
            if (case, time) == prefix
        }
        allocations = {
            (node, bus): value
            for (case, time, node, bus), value in self.allocations.items()
            if (case, time) == prefix
        }
        active_offer_nodes = frozenset(
            self.offer_node[offer]
            for offer in self.active_offers
            if offer[:2] == prefix and offer in self.offer_node
        )
        return ZeroFlowCaseInputs(
            case_id=case_id,
            date_time=date_time,
            branches=branches,
            first_loss_factors=factors,
            electrical_buses=frozenset(
                bus
                for (case, time, bus), value in self.electrical.items()
                if (case, time) == prefix and value != 0.0
            ),
            bus_generation={
                bus: value
                for (case, time, bus), value in self.bus_generation.items()
                if (case, time) == prefix
            },
            bus_load={
                bus: value
                for (case, time, bus), value in self.bus_load.items()
                if (case, time) == prefix
            },
            branch_flow=branch_flow,
            node_buses=node_buses,
            node_bus_allocation=allocations,
            offer_nodes=active_offer_nodes,
            bid_nodes=frozenset(
                node for case, time, node in self.bid_nodes if (case, time) == prefix
            ),
        )

    def case_bus_prices(self, case_id: str, date_time: str) -> dict[str, float]:
        return {
            bus: value
            for (case, time, bus), value in self.bus_price.items()
            if (case, time) == (case_id, date_time)
        }

    def case_node_prices(self, case_id: str, date_time: str) -> dict[str, float]:
        return {
            node: value
            for (case, time, node), value in self.node_price.items()
            if (case, time) == (case_id, date_time)
        }


class ZeroFlowPriceConventionRunner:
    """Certify affected cases and rebuild every material energy publication."""

    def __init__(
        self,
        *,
        source_path: Path,
        reference_result_gdx: Path,
        system_directory: Path,
        reference_root: Path,
        candidate_root: Path,
    ) -> None:
        self.source_path = source_path.resolve()
        self.reference_result_gdx = reference_result_gdx.resolve()
        self.system_directory = system_directory.resolve()
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.validator = ZeroFlowPriceConventionValidator()

    def run(self, trading_date: str) -> ZeroFlowPriceConventionResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        source_sha256 = _file_sha256(self.source_path)
        if (
            source_sha256 != reference.source_sha256
            or reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: replay and source provenance do not match"
            )
        evidence = _GdxEvidence(
            source_path=self.source_path,
            result_path=self.reference_result_gdx,
            system_directory=self.system_directory,
        )
        reference_by_id = {case.case_id: case for case in reference_cases}
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        cases = []
        for case_id in reference.affected_case_ids:
            expected = reference_by_id[case_id]
            actual = candidate_by_id[case_id]
            reference_bus_full = _surface_mapping(
                expected.surfaces["repaired-bus-price"],
                surface="repaired-bus-price",
            )
            candidate_bus_full = _surface_mapping(
                actual.surfaces["repaired-bus-price"],
                surface="repaired-bus-price",
            )
            reference_node_full = _surface_mapping(
                expected.surfaces["node-price"], surface="node-price"
            )
            candidate_node_full = _surface_mapping(
                actual.surfaces["node-price"], surface="node-price"
            )
            date_times = {key[1] for key in reference_bus_full}
            if len(date_times) != 1:
                raise EvidenceContractError(
                    "REQ-G12-ZERO-FLOW: affected case datetime is ambiguous"
                )
            date_time = next(iter(date_times))
            inputs = evidence.case_inputs(
                case_id,
                date_time,
                branch_flow=_reported_branch_flow(actual.surfaces["report-field"]),
            )
            cases.append(
                self.validator.compare_case(
                    inputs=inputs,
                    reference_bus={
                        key[2]: value for key, value in reference_bus_full.items()
                    },
                    candidate_bus={
                        key[2]: value for key, value in candidate_bus_full.items()
                    },
                    reference_node={
                        key[2]: value for key, value in reference_node_full.items()
                    },
                    candidate_node={
                        key[2]: value for key, value in candidate_node_full.items()
                    },
                    additional_bus_identities=_report_bus_price_targets(
                        expected.surfaces["report-field"],
                        actual.surfaces["report-field"],
                    ),
                )
            )

        publication_targets: dict[tuple[str, str], tuple[float, float]] = {}
        for case_id in reference.affected_case_ids:
            expected_publications = _published_energy(
                reference_by_id[case_id].surfaces["rounded-published-output"]
            )
            actual_publications = _published_energy(
                candidate_by_id[case_id].surfaces["rounded-published-output"]
            )
            for key in set(expected_publications) & set(actual_publications):
                # Canonical publications are rounded to five decimals.  Include
                # every difference outside one half of that displayed unit,
                # even when it remains below the broader semantic price tolerance.
                if (
                    abs(actual_publications[key] - expected_publications[key])
                    > 0.5 * 10.0**-5
                ):
                    previous = publication_targets.setdefault(
                        key, (expected_publications[key], actual_publications[key])
                    )
                    if previous != (
                        expected_publications[key],
                        actual_publications[key],
                    ):
                        raise EvidenceContractError(
                            "REQ-G12-ZERO-FLOW: inconsistent repeated publication"
                        )

        publications = []
        for (period, node), (reference_value, candidate_value) in sorted(
            publication_targets.items()
        ):
            contributions = []
            for (case_id, date_time), case_period in evidence.case_period.items():
                if case_period != period:
                    continue
                seconds = evidence.case_seconds.get((case_id, period), 0.0)
                if seconds <= 0.0:
                    continue
                canonical_node = self._canonical_node_price(
                    evidence=evidence,
                    case_id=case_id,
                    date_time=date_time,
                    node=node,
                )
                contributions.append(
                    PublicationContribution(case_id, date_time, seconds, canonical_node)
                )
            publications.append(
                self.validator.compare_publication(
                    trading_period=period,
                    node=node,
                    reference=reference_value,
                    candidate=candidate_value,
                    contributions=tuple(contributions),
                    decimals=5,
                )
            )
        topology_sha256 = _logical_sha256(
            {
                "source_sha256": source_sha256,
                "source_symbols": list(_SOURCE_SYMBOLS),
                "result_symbols": list(_RESULT_SYMBOLS),
                "loss_coefficients": {
                    "one": 1.0,
                    "three": 0.75 * 0.3101,
                    "six": 0.75 * 0.14495,
                    "scale": 0.01,
                },
            }
        )
        return ZeroFlowPriceConventionResult.create(
            trading_date=trading_date,
            source_sha256=source_sha256,
            reference_result_gdx_sha256=_file_sha256(self.reference_result_gdx),
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            topology_sha256=topology_sha256,
            cases=tuple(cases),
            publications=tuple(publications),
        )

    def _canonical_node_price(
        self,
        *,
        evidence: _GdxEvidence,
        case_id: str,
        date_time: str,
        node: str,
    ) -> float:
        inputs = evidence.case_inputs(case_id, date_time, branch_flow=None)
        reference_bus = evidence.case_bus_prices(case_id, date_time)
        allocations = {
            bus: value
            for (item_node, bus), value in inputs.node_bus_allocation.items()
            if item_node == node
        }
        if not allocations:
            raise EvidenceContractError(
                "REQ-G12-ZERO-FLOW: publication node has no source allocation"
            )
        canonical = dict(reference_bus)
        incident: dict[str, list[str]] = defaultdict(list)
        for branch, (from_bus, to_bus) in inputs.branches.items():
            incident[from_bus].append(branch)
            incident[to_bus].append(branch)
        for bus in allocations:
            branches = incident.get(bus, ())
            if len(branches) != 1 or bus not in inputs.electrical_buses:
                continue
            if (
                abs(inputs.bus_generation.get(bus, 0.0))
                > self.validator.injection_tolerance
                or abs(inputs.bus_load.get(bus, 0.0))
                > self.validator.injection_tolerance
            ):
                continue
            leaf_nodes = {
                item_node
                for item_node, buses in inputs.node_buses.items()
                if bus in buses
            }
            if leaf_nodes & (inputs.offer_nodes | inputs.bid_nodes):
                continue
            branch = branches[0]
            from_bus, to_bus = inputs.branches[branch]
            if bus == to_bus:
                parent, inward, outward = from_bus, "forward", "backward"
            else:
                parent, inward, outward = to_bus, "backward", "forward"
            inward_factor = inputs.first_loss_factors.get((branch, inward), 0.0)
            outward_factor = inputs.first_loss_factors.get((branch, outward), 0.0)
            if inward_factor <= 0.0 or outward_factor <= 0.0:
                continue
            expected_load = reference_bus[parent] / (1.0 - inward_factor)
            expected_export = reference_bus[parent] * (1.0 - outward_factor)
            if (
                min(
                    abs(reference_bus[bus] - expected_load),
                    abs(reference_bus[bus] - expected_export),
                )
                > self.validator.analytic_tolerance
            ):
                raise EvidenceContractError(
                    "REQ-G12-ZERO-FLOW: historical bus is not on a valid kink side"
                )
            canonical[bus] = expected_load
        return sum(weight * canonical[bus] for bus, weight in allocations.items())
