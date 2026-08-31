"""Pure nodal, bus, island, and active-branch preprocessing."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from pyspd.contracts import CaseData
from pyspd.preprocess.base import (
    Artifact,
    PreprocessingSettings,
    PreprocessingStep,
    SparseParameter,
    SparseSet,
)
from pyspd.preprocess.input import CaseInput, nonzero


class TopologyStep(PreprocessingStep):
    name = "topology"
    provides = frozenset(
        {
            "case_datetime",
            "case_datetime_period",
            "node",
            "bus",
            "node_bus",
            "bus_island",
            "node_island",
            "total_bus_allocation",
            "bus_node_allocation_factor",
            "branch",
            "report_branch",
            "branch_bus_definition",
            "branch_from_bus",
            "branch_to_bus",
            "branch_bus_connect",
            "ac_branch",
            "hvdc_link",
        }
    )

    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        source = CaseInput(case_data)
        case_period = source.members("i_dateTimeTradePeriodMap")
        case_datetime = frozenset(key[:2] for key in case_period)
        node_bus = source.members("i_dateTimeNodeBus")
        bus_island = source.members("i_dateTimeBusIsland")
        nodes = frozenset(key[:3] for key in node_bus)
        buses = frozenset(key[:3] for key in bus_island)

        islands_by_bus: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        for case, datetime, bus, island in bus_island:
            islands_by_bus[(case, datetime, bus)].add(island)
        node_island = frozenset(
            (case, datetime, node, island)
            for case, datetime, node, bus in node_bus
            for island in islands_by_bus[(case, datetime, bus)]
        )

        allocation = source.numeric("i_dateTimeNodeBusAllocationFactor")
        totals: dict[tuple[str, ...], float] = defaultdict(float)
        for (case, datetime, _node, bus), value in allocation.items():
            if (case, datetime, bus) in buses:
                totals[(case, datetime, bus)] += value
        bus_node_factor: dict[tuple[str, ...], float] = {
            (case, datetime, bus, node): value / totals[(case, datetime, bus)]
            for (case, datetime, node, bus), value in allocation.items()
            if totals.get((case, datetime, bus), 0.0) > 0.0
        }

        definitions = source.members("i_dateTimeBranchDefn")
        is_open = source.component("i_dateTimeBranchParameter", "isOpen")
        forward = source.component("i_dateTimeBranchParameter", "forwardCap")
        backward = source.component("i_dateTimeBranchParameter", "backwardCap")
        is_hvdc = source.component("i_dateTimeBranchParameter", "HVDCbranch")
        active_branches: set[tuple[str, str, str]] = set()
        for case, datetime, branch, from_bus, to_bus in definitions:
            key = (case, datetime, branch)
            connected = (case, datetime, from_bus) in buses and (
                case,
                datetime,
                to_bus,
            ) in buses
            regular = (
                not nonzero(is_open.get(key, 0.0))
                and nonzero(forward.get(key, 0.0))
                and nonzero(backward.get(key, 0.0))
                and connected
            )
            hvdc_forward_only = (
                not nonzero(is_open.get(key, 0.0))
                and nonzero(forward.get(key, 0.0))
                and nonzero(is_hvdc.get(key, 0.0))
                and connected
            )
            if regular or hvdc_forward_only:
                active_branches.add(key)
        branch_definitions = frozenset(
            key for key in definitions if key[:3] in active_branches
        )
        branch_from = frozenset(
            (case, datetime, branch, from_bus)
            for case, datetime, branch, from_bus, _to_bus in branch_definitions
        )
        branch_to = frozenset(
            (case, datetime, branch, to_bus)
            for case, datetime, branch, _from_bus, to_bus in branch_definitions
        )
        branch_connect = frozenset(
            (*key[:3], bus) for key in branch_definitions for bus in key[3:]
        )
        hvdc = frozenset(
            key for key in active_branches if nonzero(is_hvdc.get(key, 0.0))
        )
        ac = frozenset(active_branches - hvdc)

        return {
            "case_datetime": SparseSet(
                "case_datetime", ("case", "datetime"), case_datetime
            ),
            "case_datetime_period": SparseSet(
                "case_datetime_period",
                ("case", "datetime", "period"),
                case_period,
            ),
            "node": SparseSet("node", ("case", "datetime", "node"), nodes),
            "bus": SparseSet("bus", ("case", "datetime", "bus"), buses),
            "node_bus": SparseSet(
                "node_bus", ("case", "datetime", "node", "bus"), node_bus
            ),
            "bus_island": SparseSet(
                "bus_island", ("case", "datetime", "bus", "island"), bus_island
            ),
            "node_island": SparseSet(
                "node_island",
                ("case", "datetime", "node", "island"),
                node_island,
            ),
            "total_bus_allocation": SparseParameter(
                "total_bus_allocation", ("case", "datetime", "bus"), totals
            ),
            "bus_node_allocation_factor": SparseParameter(
                "bus_node_allocation_factor",
                ("case", "datetime", "bus", "node"),
                bus_node_factor,
            ),
            "branch": SparseSet(
                "branch", ("case", "datetime", "branch"), frozenset(active_branches)
            ),
            "report_branch": SparseSet(
                "report_branch",
                ("case", "datetime", "branch"),
                frozenset(key[:3] for key in definitions),
            ),
            "branch_bus_definition": SparseSet(
                "branch_bus_definition",
                ("case", "datetime", "branch", "from_bus", "to_bus"),
                branch_definitions,
            ),
            "branch_from_bus": SparseSet(
                "branch_from_bus",
                ("case", "datetime", "branch", "bus"),
                branch_from,
            ),
            "branch_to_bus": SparseSet(
                "branch_to_bus", ("case", "datetime", "branch", "bus"), branch_to
            ),
            "branch_bus_connect": SparseSet(
                "branch_bus_connect",
                ("case", "datetime", "branch", "bus"),
                branch_connect,
            ),
            "ac_branch": SparseSet("ac_branch", ("case", "datetime", "branch"), ac),
            "hvdc_link": SparseSet("hvdc_link", ("case", "datetime", "branch"), hvdc),
        }
