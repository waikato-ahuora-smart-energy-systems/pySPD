"""Pinned-GAMS instrumentation for canonical Gate 12 replay evidence."""

from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pyspd.data import SymbolCatalog
from pyspd.data.gdx import GdxAdapter
from pyspd.orchestration import DailyCaseSelector
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.incremental_replay import IncrementalReplayWorkItem
from tools.gate12.pyspd_surfaces import CanonicalCaseSurfaces
from tools.oracle.vspd import (
    NativeGamsProfile,
    VspdRunConfiguration,
    VspdSourcePatcher,
)

GAMS_GATE12_REPLAY_PROFILE = "gams-v5.0.2-scip-mip-fixed-highs-rmip-gate12-v1"
_SAFE_IDENTITY = re.compile(r"[A-Za-z0-9_.-]+")

_DECLARATIONS = """* pySPD Gate 12 cumulative replay evidence
Parameters
  pyspd_gate12_raw_bus_price(ca,dt,b)
  pyspd_gate12_repaired_bus_price(ca,dt,b)
  pyspd_gate12_final_required_load(ca,dt,n)
  pyspd_gate12_final_energy_shortfall(ca,dt,n)
  pyspd_gate12_transfer_mw(ca,dt,n,n1)
  pyspd_gate12_untransferred(ca,dt,n)
  pyspd_gate12_primary_objective(ca,dt)
  pyspd_gate12_pricing_objective(ca,dt)
  pyspd_gate12_solve_count(ca,dt)
  pyspd_gate12_HVDCSENDING(ca,dt,isl)
  pyspd_gate12_INZONE(ca,dt,isl,resC,z)
  pyspd_gate12_HVDCSENTINSEGMENT(ca,dt,isl,los)
  pyspd_gate12_PURCHASEBLOCKBINARY(ca,dt,bd,blk)
  pyspd_gate12_HVDCSENDZERO(ca,dt,isl)
  pyspd_gate12_ACBRANCHFLOWDIRECTED_INTEGER(ca,dt,br,fd)
  pyspd_gate12_HVDCLINKFLOWDIRECTED_INTEGER(ca,dt,fd)
  pyspd_gate12_HVDCPOLEFLOW_INTEGER(ca,dt,pole,fd)
  pyspd_gate12_LAMBDAINTEGER(ca,dt,br,bp)
  pyspd_gate12_LAMBDAHVDCENERGY(ca,dt,isl,bp)
  pyspd_gate12_LAMBDAHVDCRESERVE(ca,dt,isl,resC,rd,rsbp)
  ;
"""

_ACCEPTED_STATE = """* pySPD Gate 12 accepted state capture
        pyspd_gate12_final_required_load(t,n) $ Node(t,n) = requiredLoad(t,n);
        pyspd_gate12_final_energy_shortfall(t,n) $ Node(t,n) = o_nodeDeficit_TP(t,n);
        pyspd_gate12_primary_objective(t) = pyspd_primary_objective;
        pyspd_gate12_pricing_objective(t) = NETBENEFIT.l;
        pyspd_gate12_solve_count(t) = LoopCount(t) - 1;
        pyspd_gate12_HVDCSENDING(t,isl) = HVDCSENDING.l(t,isl);
        pyspd_gate12_INZONE(t,isl,resC,z) = INZONE.l(t,isl,resC,z);
        pyspd_gate12_HVDCSENTINSEGMENT(t,isl,los) = HVDCSENTINSEGMENT.l(t,isl,los);
        pyspd_gate12_PURCHASEBLOCKBINARY(t,bd,blk) = PURCHASEBLOCKBINARY.l(t,bd,blk);
        pyspd_gate12_HVDCSENDZERO(t,isl) = HVDCSENDZERO.l(t,isl);
        pyspd_gate12_ACBRANCHFLOWDIRECTED_INTEGER(t,br,fd) = ACBRANCHFLOWDIRECTED_INTEGER.l(t,br,fd);
        pyspd_gate12_HVDCLINKFLOWDIRECTED_INTEGER(t,fd) = HVDCLINKFLOWDIRECTED_INTEGER.l(t,fd);
        pyspd_gate12_HVDCPOLEFLOW_INTEGER(t,pole,fd) = HVDCPOLEFLOW_INTEGER.l(t,pole,fd);
        pyspd_gate12_LAMBDAINTEGER(t,br,bp) = LAMBDAINTEGER.l(t,br,bp);
        pyspd_gate12_LAMBDAHVDCENERGY(t,isl,bp) = LAMBDAHVDCENERGY.l(t,isl,bp);
        pyspd_gate12_LAMBDAHVDCRESERVE(t,isl,resC,rd,rsbp) = LAMBDAHVDCRESERVE.l(t,isl,resC,rd,rsbp);
"""

_FINAL_UNLOAD = """* pySPD Gate 12 cumulative canonical source artifact
execute_unload 'pyspd_gate12_results.gdx'
  case2dt2tp, casefileseconds, studyMode, dtParameter,
  offer, node, bus, nodeBus, NodeBusAllocationFactor, isl, resC,
  pyspd_gate12_raw_bus_price, pyspd_gate12_repaired_bus_price,
  pyspd_gate12_final_required_load, pyspd_gate12_final_energy_shortfall,
  pyspd_gate12_transfer_mw, pyspd_gate12_untransferred,
  pyspd_gate12_primary_objective, pyspd_gate12_pricing_objective,
  pyspd_gate12_solve_count,
  pyspd_gate12_HVDCSENDING, pyspd_gate12_INZONE,
  pyspd_gate12_HVDCSENTINSEGMENT, pyspd_gate12_PURCHASEBLOCKBINARY,
  pyspd_gate12_HVDCSENDZERO, pyspd_gate12_ACBRANCHFLOWDIRECTED_INTEGER,
  pyspd_gate12_HVDCLINKFLOWDIRECTED_INTEGER,
  pyspd_gate12_HVDCPOLEFLOW_INTEGER, pyspd_gate12_LAMBDAINTEGER,
  pyspd_gate12_LAMBDAHVDCENERGY, pyspd_gate12_LAMBDAHVDCRESERVE,
  o_offerEnergy_TP, o_busGeneration_TP, o_busLoad_TP, o_busPrice_TP,
  o_nodePrice_TP, o_ResPrice_TP,
  o_PublisedPrice_TP, o_PublisedFIRPrice_TP, o_PublisedSIRPrice_TP;

"""


class Gate12GamsSourcePatcher(VspdSourcePatcher):
    """Add cumulative observational evidence to the qualified solver overlay."""

    def __init__(
        self,
        *,
        affected_case_ids: tuple[str, ...],
        base: VspdSourcePatcher | None = None,
    ) -> None:
        if not affected_case_ids or len(set(affected_case_ids)) != len(
            affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-GAMS: affected case identities must be unique and non-empty"
            )
        if any(not _SAFE_IDENTITY.fullmatch(case_id) for case_id in affected_case_ids):
            raise EvidenceContractError("REQ-G12-GAMS: unsafe affected case identity")
        self.affected_case_ids = affected_case_ids
        self.base = base or VspdSourcePatcher()

    def apply(
        self,
        programs: Path,
        profile: NativeGamsProfile,
        configuration: VspdRunConfiguration | None = None,
    ) -> None:
        if not profile.explicit_fixed_lp_pricing or not profile.supports_marginals:
            raise EvidenceContractError(
                "REQ-G12-GAMS: canonical replay requires fixed-RMIP marginals"
            )
        if configuration is None or configuration.daily_mode != 1:
            raise EvidenceContractError(
                "REQ-G12-GAMS: canonical replay requires explicit daily mode"
            )
        if not set(self.affected_case_ids).issubset(configuration.case_ids):
            raise EvidenceContractError(
                "REQ-G12-GAMS: affected cases are absent from the replay prefix"
            )
        self.base.apply(programs, profile, configuration)
        self._normalise_portable_paths(programs)
        solve = programs / "vSPDsolve.gms"
        self._replace_gate12_exact(
            solve,
            "Parameters\n  casefileseconds(ca,tp)",
            _DECLARATIONS + "\nParameters\n  casefileseconds(ca,tp)",
        )
        self._replace_gate12_exact(
            solve,
            "        busPrice(bus(t,b))      = ACnodeNetInjectionDefinition2.m(t,b) ;",
            "        busPrice(bus(t,b))      = ACnodeNetInjectionDefinition2.m(t,b) ;\n"
            "        pyspd_gate12_raw_bus_price(bus(t,b)) = busPrice(t,b);",
        )
        self._replace_gate12_exact(
            solve,
            "            ShortfallAdjustmentMW(t,n) $ sum[ n1, ShortfallTransferFromTo(t,n,n1)] = 0;",
            "            pyspd_gate12_transfer_mw(t,n,n1)"
            " $ ShortfallTransferFromTo(t,n,n1)\n"
            "                = pyspd_gate12_transfer_mw(t,n,n1)"
            " + ShortfallAdjustmentMW(t,n);\n"
            "            pyspd_gate12_untransferred(t,n)"
            " $ { ShortfallAdjustmentMW(t,n)"
            " and (sum[n1, ShortfallTransferFromTo(t,n,n1)] = 0) } = 1;\n"
            "            ShortfallAdjustmentMW(t,n) $ sum[ n1, ShortfallTransferFromTo(t,n,n1)] = 0;",
        )
        self._replace_gate12_exact(
            solve,
            "*   Reporting at trading period start",
            "        pyspd_gate12_repaired_bus_price(bus(t,b)) = busPrice(t,b);\n\n"
            "*   Reporting at trading period start",
        )
        self._replace_gate12_exact(
            solve,
            "*       branch output",
            _ACCEPTED_STATE + "\n*       branch output",
        )
        self._replace_gate12_exact(
            solve,
            "* 9. Write results to CSV report files and GDX files",
            _FINAL_UNLOAD + "* 9. Write results to CSV report files and GDX files",
        )

    def _normalise_portable_paths(self, programs: Path) -> None:
        """Replace pinned Windows separators at the GAMS preprocessor boundary."""

        settings = programs / "vSPDsettings.inc"
        period = programs / "vSPDperiod.gms"
        solve = programs / "vSPDsolve.gms"
        self._replace_gate12_exact(
            settings,
            "'%system.fp%..\\Input\\'",
            "'%system.fp%../Input/'",
        )
        self._replace_gate12_exact(
            settings,
            "'%system.fp%..\\Output\\'",
            "'%system.fp%../Output/'",
        )
        self._replace_gate12_exact(
            settings,
            "'%system.fp%..\\Override\\'",
            "'%system.fp%../Override/'",
        )
        self._replace_gate12_all(
            period,
            "%inputPath%\\%GDXname%.gdx",
            "%inputPath%/%GDXname%.gdx",
            expected_count=2,
        )
        self._replace_gate12_exact(
            period,
            "%programPath%\\vSPDperiod.gdx",
            "%programPath%/vSPDperiod.gdx",
        )
        self._replace_gate12_all(
            solve,
            "%inputPath%\\%GDXname%.gdx",
            "%inputPath%/%GDXname%.gdx",
            expected_count=4,
        )
        self._replace_gate12_exact(
            solve,
            "unsolvedDT(ca,dt) = yes $ case2dt(ca,dt) ;",
            "pyspd_gate12_transfer_mw(ca,dt,n,n1) = 0;\n"
            "unsolvedDT(ca,dt) = yes $ case2dt(ca,dt) ;",
        )
        self._replace_gate12_all(
            programs / "vSPDreportSetup.gms",
            "%outputPath%\\%runName%\\",
            "%outputPath%%runName%/",
            expected_count=19,
        )
        self._replace_gate12_all(
            programs / "vSPDreport.gms",
            "%outputPath%\\%runName%\\",
            "%outputPath%%runName%/",
            expected_count=22,
        )

    @staticmethod
    def _replace_gate12_exact(path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise EvidenceContractError(
                f"REQ-G12-GAMS: {path.name} contained {count} instrumentation "
                f"targets for {old!r}; expected one"
            )
        path.write_text(text.replace(old, new), encoding="utf-8")

    @staticmethod
    def _replace_gate12_all(
        path: Path,
        old: str,
        new: str,
        *,
        expected_count: int,
    ) -> None:
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count != expected_count:
            raise EvidenceContractError(
                f"REQ-G12-GAMS: {path.name} contained {count} portability "
                f"targets for {old!r}; expected {expected_count}"
            )
        path.write_text(text.replace(old, new), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class GamsReplayArtifacts:
    """Paths and status evidence from one completed pinned-GAMS prefix."""

    result_gdx: Path
    report_directory: Path
    all_solves_optimal: bool


class GamsReplaySurfaceExporter:
    """Project instrumented pinned-GAMS results onto all Gate 12 surfaces."""

    _discrete_symbols: ClassVar[Mapping[str, str]] = {
        "pyspd_gate12_HVDCSENDING": "hvdc-sending",
        "pyspd_gate12_INZONE": "in-zone",
        "pyspd_gate12_HVDCSENDZERO": "hvdc-send-zero",
    }
    _sos_symbols: ClassVar[Mapping[str, str]] = {
        "pyspd_gate12_LAMBDAHVDCENERGY": "hvdc-energy-lambda",
        "pyspd_gate12_LAMBDAHVDCRESERVE": "hvdc-reserve-lambda",
    }

    def export(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        source: Path,
        system_directory: Path,
        artifacts: GamsReplayArtifacts,
    ) -> tuple[CanonicalCaseSurfaces, ...]:
        if not artifacts.all_solves_optimal:
            raise EvidenceContractError(
                "REQ-G12-GAMS: canonical surfaces require all optimal solves"
            )
        if not artifacts.result_gdx.is_file():
            raise EvidenceContractError(
                "REQ-G12-GAMS: cumulative replay GDX is unavailable"
            )
        source_symbols = GdxAdapter.read(source, system_directory=system_directory)
        if source_symbols.source_sha256 != work_item.source_sha256:
            raise EvidenceContractError("REQ-G12-GAMS: source hash mismatch")
        SymbolCatalog.vspd_v5().validate(source_symbols)
        selected = DailyCaseSelector().select(
            source_symbols, case_ids=work_item.case_ids
        )
        by_id = {case.case_id: case for case in selected}
        evidence = _GamsParameterStore(artifacts.result_gdx, system_directory)
        total_seconds = self._total_seconds(evidence, frozenset(work_item.case_ids))
        return tuple(
            self._case_surfaces(
                work_item=work_item,
                selected=by_id[case_id],
                evidence=evidence,
                report_directory=artifacts.report_directory,
                total_seconds=total_seconds,
            )
            for case_id in work_item.affected_case_ids
        )

    def _case_surfaces(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        selected: Any,
        evidence: _GamsParameterStore,
        report_directory: Path,
        total_seconds: Mapping[str, float],
    ) -> CanonicalCaseSurfaces:
        case_id = selected.case_id
        date_time = selected.date_time
        prefix = (case_id, date_time)
        offers = evidence.members("offer", prefix=prefix)
        buses = evidence.members("bus", prefix=prefix)
        nodes = evidence.members("node", prefix=prefix)
        generation = {
            key[2:]: evidence.value("o_offerEnergy_TP", key) for key in offers
        }
        bus_generation = {
            key: evidence.value("o_busGeneration_TP", key) for key in buses
        }
        bus_load = {key: evidence.value("o_busLoad_TP", key) for key in buses}
        raw_bus = {
            key: evidence.value("pyspd_gate12_raw_bus_price", key) for key in buses
        }
        repaired_bus = {
            key: evidence.value("pyspd_gate12_repaired_bus_price", key) for key in buses
        }
        node_prices = {key: evidence.value("o_nodePrice_TP", key) for key in nodes}
        final_load = {
            key: evidence.value("pyspd_gate12_final_required_load", key)
            for key in nodes
        }
        energy_shortfall = {
            key: evidence.value("pyspd_gate12_final_energy_shortfall", key)
            for key in nodes
        }
        reserve_prices = {
            key: value
            for key, value in evidence.numeric("o_ResPrice_TP").items()
            if key[:2] == prefix
        }
        transfers = {
            ((key[0], key[1], key[2]), (key[0], key[1], key[3])): value
            for key, value in evidence.numeric("pyspd_gate12_transfer_mw").items()
            if key[:2] == prefix
        }
        untransferred = [
            list(key)
            for key, value in evidence.numeric("pyspd_gate12_untransferred").items()
            if key[:2] == prefix and value != 0.0
        ]
        fixed_discrete = self._fixed_state(evidence, prefix, self._discrete_symbols)
        fixed_sos = self._fixed_state(evidence, prefix, self._sos_symbols)
        period = selected.trading_period
        published_energy = {
            key: round(value, 5)
            for key, value in evidence.numeric("o_PublisedPrice_TP").items()
            if key[0] == period
        }
        published_reserve = self._published_reserve(evidence, period)
        surfaces = {
            "case-selection": _json_bytes(
                {
                    "case_id": case_id,
                    "date_time": date_time,
                    "trading_period": period,
                    "study_mode": selected.study_mode,
                    "schedule_type": selected.schedule_type.value,
                    "interval_minutes": _number(selected.interval_minutes),
                    "publication_seconds": _number(selected.publication_seconds),
                    "ordinal": selected.ordinal,
                    "source_sha256": selected.source_sha256,
                }
            ),
            "state-transition": _json_bytes(
                {
                    "status": "complete",
                    "solve_count": int(
                        evidence.value("pyspd_gate12_solve_count", prefix)
                    ),
                    "events": [],
                    "transfers": _mapping(transfers),
                    "untransferred_nodes": sorted(untransferred),
                }
            ),
            "primary-physics": _json_bytes(
                {
                    "generation": _mapping(generation),
                    "energy_shortfall": _mapping(energy_shortfall),
                    "bus_generation": _mapping(bus_generation),
                    "bus_load": _mapping(bus_load),
                    "final_required_load": _mapping(final_load),
                    "structural_signature": None,
                    "variables": [],
                }
            ),
            "primary-objective": _json_bytes(
                {
                    "primary_mip_objective_nzd": _number(
                        evidence.value("pyspd_gate12_primary_objective", prefix)
                    ),
                    "fixed_rmip_objective_nzd": _number(
                        evidence.value("pyspd_gate12_pricing_objective", prefix)
                    ),
                }
            ),
            "fixed-discrete-pricing-state": _json_bytes(
                {
                    "fixed_discrete": _mapping(fixed_discrete),
                    "fixed_sos_members": _mapping(fixed_sos),
                    "primary_structural_signature": None,
                    "pricing_structural_signature": None,
                }
            ),
            "raw-bus-price": _json_bytes(_mapping(raw_bus)),
            "repaired-bus-price": _json_bytes(_mapping(repaired_bus)),
            "node-price": _json_bytes(_mapping(node_prices)),
            "reserve-price": _json_bytes(_mapping(reserve_prices)),
            "publication-seconds": _json_bytes(
                {
                    "trading_period": period,
                    "seconds": _number(selected.publication_seconds),
                }
            ),
            "rounded-published-output": _json_bytes(
                {
                    "energy": _mapping(published_energy),
                    "reserve": _mapping(published_reserve),
                    "total_seconds": _number(total_seconds.get(period, 0.0)),
                }
            ),
            "report-field": self._report_surface(
                report_directory, case_id=case_id, trading_period=period
            ),
        }
        return CanonicalCaseSurfaces(case_id, work_item.trading_date, surfaces)

    @staticmethod
    def _fixed_state(
        evidence: _GamsParameterStore,
        prefix: tuple[str, str],
        names: Mapping[str, str],
    ) -> dict[tuple[str, ...], float]:
        output: dict[tuple[str, ...], float] = {}
        for name, family in names.items():
            for key, value in evidence.numeric(name).items():
                if key[:2] == prefix and value != 0.0:
                    output[(family, *key)] = value
        return output

    @staticmethod
    def _published_reserve(
        evidence: _GamsParameterStore, period: str
    ) -> dict[tuple[str, str, str], float]:
        output = {
            (key[0], key[1], "FIR"): round(value, 5)
            for key, value in evidence.numeric("o_PublisedFIRPrice_TP").items()
            if key[0] == period
        }
        output.update(
            {
                (key[0], key[1], "SIR"): round(value, 5)
                for key, value in evidence.numeric("o_PublisedSIRPrice_TP").items()
                if key[0] == period
            }
        )
        return output

    @staticmethod
    def _total_seconds(
        evidence: _GamsParameterStore, case_ids: frozenset[str]
    ) -> dict[str, float]:
        output: dict[str, float] = {}
        for (case_id, period), seconds in evidence.numeric("casefileseconds").items():
            if case_id in case_ids:
                output[period] = output.get(period, 0.0) + seconds
        return output

    @staticmethod
    def _report_surface(directory: Path, *, case_id: str, trading_period: str) -> bytes:
        if not directory.is_dir():
            raise EvidenceContractError("REQ-G12-GAMS: report directory is missing")
        tables: dict[str, object] = {}
        for path in sorted(directory.glob("*.csv")):
            with path.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames is None:
                    raise EvidenceContractError("REQ-G12-GAMS: report has no header")
                rows = []
                for row in reader:
                    if "CaseID" in row and row["CaseID"] != case_id:
                        continue
                    if (
                        "CaseID" not in row
                        and "TradingPeriod" in row
                        and row["TradingPeriod"] != trading_period
                    ):
                        continue
                    rows.append(dict(row))
                tables[path.stem] = {
                    "fields": list(reader.fieldnames),
                    "rows": rows,
                }
        if not tables:
            raise EvidenceContractError("REQ-G12-GAMS: no CSV report evidence")
        return _json_bytes(tables)


class _GamsParameterStore:
    def __init__(self, path: Path, system_directory: Path) -> None:
        from gams.transfer import Container

        self.container = Container(system_directory=str(system_directory))
        self.container.read(str(path))
        self._numeric: dict[str, dict[tuple[str, ...], float]] = {}

    def numeric(self, name: str) -> dict[tuple[str, ...], float]:
        if name in self._numeric:
            return self._numeric[name]
        try:
            symbol = self.container[name]
        except KeyError as error:
            raise EvidenceContractError(
                f"REQ-G12-GAMS: result symbol is missing: {name}"
            ) from error
        frame = symbol.records
        if frame is None:
            return {}
        columns = tuple(str(column) for column in frame.columns)
        value_columns = [
            index
            for index, column in enumerate(columns)
            if column.casefold() == "value"
        ]
        if len(value_columns) != 1:
            raise EvidenceContractError(
                f"REQ-G12-GAMS: result parameter has no unique value column: {name}"
            )
        value_index = value_columns[0]
        dimension = int(symbol.dimension)
        values = {
            tuple(str(value) for value in row[:dimension]): _finite(
                row[value_index], name
            )
            for row in frame.itertuples(index=False, name=None)
        }
        self._numeric[name] = values
        return values

    def members(
        self, name: str, *, prefix: tuple[str, ...]
    ) -> tuple[tuple[str, ...], ...]:
        try:
            symbol = self.container[name]
        except KeyError as error:
            raise EvidenceContractError(
                f"REQ-G12-GAMS: result set is missing: {name}"
            ) from error
        frame = symbol.records
        if frame is None:
            return ()
        dimension = int(symbol.dimension)
        return tuple(
            key
            for row in frame.itertuples(index=False, name=None)
            if (key := tuple(str(value) for value in row[:dimension]))[: len(prefix)]
            == prefix
        )

    def value(self, name: str, key: tuple[str, ...]) -> float:
        return self.numeric(name).get(key, 0.0)


def _finite(value: object, symbol: str) -> float:
    number = float(str(value))
    if not math.isfinite(number):
        raise EvidenceContractError(
            f"REQ-G12-GAMS: {symbol} contains non-finite evidence"
        )
    return number


def _number(value: float) -> str:
    return _finite(value, "canonical surface").hex()


def _mapping(values: Mapping[Any, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, value in values.items():
        identity = key if isinstance(key, tuple) else (key,)
        rows.append(
            {
                "identity": [str(item) for item in identity],
                "value": _number(float(value)),
            }
        )
    return sorted(
        rows, key=lambda row: json.dumps(row["identity"], separators=(",", ":"))
    )


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
