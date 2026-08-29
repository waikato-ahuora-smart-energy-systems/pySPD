"""Canonical anonymous-row matrix parity for the Gate 7 reserve projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyomo.environ as pyo
from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import GdxAdapter
from pyspd.reserve import reserve_formulation
from tools.gate4.oracle_matrix import _semantic
from tools.gate5.oracle_matrix import _source
from tools.oracle.canonical import ConvertDictionaryReader, ConvertMatrixReader

STAGE7_ROW_FAMILIES = frozenset(
    {
        "AClineRiskGroupCalculation",
        "AClineRiskGroupCalculation_1",
        "BothClearedAndFreeReserveCanBeShared",
        "EffectiveReserveShareCalculation",
        "EnergyAndReserveMaximum",
        "ExcessReserveSharePenalty",
        "ForwardReserveOnlyToEnergyReceivingIsland",
        "ForwardReserveReceivedAtHVDCReceivingIsland",
        "FwdReserveShareSentLimitByHVDCCapacity",
        "GenIslandRiskCalculation",
        "GenIslandRiskCalculation_1",
        "GenIslandRiskGroupCalculation",
        "GenIslandRiskGroupCalculation_1",
        "GenRiskReserveShortFallCalculation",
        "HVDCFlowAccountedForForwardReserve",
        "HVDCFlowAccountedForReverseReserve",
        "HVDCIslandRiskCalculation",
        "HVDCIslandSecRiskCalculation_GEN",
        "HVDCIslandSecRiskCalculation_GEN_1",
        "HVDCIslandSecRiskCalculation_Manual",
        "HVDCIslandSecRiskCalculation_Manu_1",
        "HVDCRecCalculation",
        "HVDCRiskReserveShortFallCalculation",
        "HVDCSendMustZeroBinaryDefinition",
        "HVDCSendingIslandDefinition",
        "HVDCSentCalculation",
        "HVDCSentEnergyFlowDefinition",
        "HVDCSentEnergyLambdaDefinition",
        "HVDCSentEnergyLossesDefinition",
        "HVDCSentReserveFlowDefinition",
        "HVDCSentReserveLambdaDefinition",
        "HVDCSentReserveLossesDefinition",
        "HVDCsecManualRiskReserveShortFallCalculation",
        "HVDCsecRiskReserveShortFallCalculation",
        "IslandReserveCalculation",
        "ManualIslandRiskCalculation",
        "ManualRiskReserveShortFallCalculation",
        "OnlyOneActiveHVDCZoneForEachReserveClass",
        "OnlyOneSendingIslandExists",
        "PLSRReserveProportionMaximum",
        "ReserveInterruptibleOfferLimit",
        "ReserveOfferDefinition",
        "ReserveShareEffective_CE_Calculation",
        "ReserveShareEffective_ECE_Calculation",
        "ReserveShareSentLimitByHVDCControlBand",
        "ReverseReserveLimitInReserveZone",
        "ReverseReserveOnlyToEnergySendingIsland",
        "ReverseReserveReceivedAtHVDCSendingIsland",
        "ReverseReserveShareLimitByHVDCControlBand",
        "RiskGroupReserveShortFallCalculation",
        "RiskOffsetCalculation_DCCE",
        "RiskOffsetCalculation_DCECE",
        "RoundPowerZoneSentHVDCUpperLimit",
        "SharedReserveLimitByClearedReserve",
        "SupplyDemandReserveRequirement",
        "ZeroReserveInNoReserveZone",
        "ZeroSentHVDCFlowForNonSendingIsland",
    }
)

PYOMO_ROW_COMPONENTS = frozenset(
    {
        "ReserveOffers.PLSRReserveProportionMaximum",
        "ReserveOffers.ReserveInterruptibleOfferLimit",
        "ReserveOffers.ReserveOfferDefinition",
        "ReserveOffers.EnergyAndReserveMaximum",
        "ReserveScarcity.ShortfallDefinitions",
        "ReserveRisk.Constraints",
        "ReserveSharing.Constraints",
        "IslandReserve.IslandReserveCalculation",
        "ReserveRequirement.SupplyDemandReserveRequirement",
    }
)

PYOMO_VARIABLES = {
    "EnergyOffers.Generation": "GENERATION",
    "DemandBids.Purchase": "PURCHASE",
    "ACNetwork.ACBranchFlow": "ACBRANCHFLOW",
    "HVDCTransmission.HVDCLinkFlow": "HVDCLINKFLOW",
    "HVDCTransmission.HVDCLinkLosses": "HVDCLINKLOSSES",
    "ReserveOffers.Reserve": "RESERVE",
    "ReserveOffers.ReserveBlock": "RESERVEBLOCK",
    "ReserveScarcity.ReserveShortfall": "RESERVESHORTFALL",
    "ReserveScarcity.ReserveShortfallBlock": "RESERVESHORTFALLBLK",
    "ReserveScarcity.ReserveShortfallUnit": "RESERVESHORTFALLUNIT",
    "ReserveScarcity.ReserveShortfallUnitBlock": "RESERVESHORTFALLUNITBLK",
    "ReserveScarcity.ReserveShortfallGroup": "RESERVESHORTFALLGROUP",
    "ReserveScarcity.ReserveShortfallGroupBlock": "RESERVESHORTFALLGROUPBLK",
    "ReserveRisk.IslandRisk": "ISLANDRISK",
    "ReserveRisk.GeneratorIslandRisk": "GENISLANDRISK",
    "ReserveRisk.GroupIslandRisk": "GENISLANDRISKGROUP",
    "ReserveRisk.HVDCGeneratorIslandRisk": "HVDCGENISLANDRISK",
    "ReserveRisk.HVDCManualIslandRisk": "HVDCMANISLANDRISK",
    "ReserveRisk.HVDCReceived": "HVDCREC",
    "ReserveRisk.RiskOffset": "RISKOFFSET",
    "ReserveSharing.SharedNFR": "SHAREDNFR",
    "ReserveSharing.SharedReserve": "SHAREDRESERVE",
    "ReserveSharing.HVDCSent": "HVDCSENT",
    "ReserveSharing.HVDCSentLoss": "HVDCSENTLOSS",
    "ReserveSharing.ReserveShareEffective": "RESERVESHAREEFFECTIVE",
    "ReserveSharing.ReserveShareReceived": "RESERVESHARERECEIVED",
    "ReserveSharing.ReserveShareSent": "RESERVESHARESENT",
    "ReserveSharing.ReserveSharePenalty": "RESERVESHAREPENALTY",
    "ReserveSharing.ReserveShareEffectiveCE": "RESERVESHAREEFFECTIVE_CE",
    "ReserveSharing.ReserveShareEffectiveECE": "RESERVESHAREEFFECTIVE_ECE",
    "ReserveSharing.HVDCSending": "HVDCSENDING",
    "ReserveSharing.HVDCSendZero": "HVDCSENDZERO",
    "ReserveSharing.InZone": "INZONE",
    "ReserveSharing.LambdaHVDCEnergy": "LAMBDAHVDCENERGY",
    "ReserveSharing.LambdaHVDCReserve": "LAMBDAHVDCRESERVE",
    "ReserveSharing.HVDCReserveSent": "HVDCRESERVESENT",
    "ReserveSharing.HVDCReserveLoss": "HVDCRESERVELOSS",
    "IslandReserve.IslandReserve": "ISLANDRESERVE",
    "ReserveRequirement.DeficitReserveCE": "DEFICITRESERVE_CE",
    "ReserveRequirement.DeficitReserveECE": "DEFICITRESERVE_ECE",
}

STAGE7_VARIABLE_FAMILIES = frozenset(
    set(PYOMO_VARIABLES.values())
    - {"GENERATION", "PURCHASE", "ACBRANCHFLOW", "HVDCLINKFLOW", "HVDCLINKLOSSES"}
)


def compare(
    *,
    input_gdx: Path,
    matrix_gdx: Path,
    dictionary_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    built = ModelAssembler().assemble(
        reserve_formulation(preprocess=True),
        CaseData("vspd-v5.0.6", identifier, raw),
    )
    scalar = ConvertMatrixReader(system_directory).read(matrix_gdx)
    dictionary = ConvertDictionaryReader(system_directory).read(dictionary_gdx)
    oracle = dictionary.apply(scalar)
    python_columns, python_rows, unmapped = _pyomo_projection(built.model)
    oracle_columns = {
        column.name: _column_signature(
            column.lower,
            column.upper,
            column.objective,
            column.discrete_type,
        )
        for column in oracle.columns
        if _family(column.name) in STAGE7_VARIABLE_FAMILIES
    }
    oracle_row_names = {
        row.name for row in oracle.rows if _family(row.name) in STAGE7_ROW_FAMILIES
    }
    oracle_bounds = {
        row.name: (row.lower, row.upper)
        for row in oracle.rows
        if row.name in oracle_row_names
    }
    oracle_entries: dict[str, list[tuple[str, float]]] = {
        name: [] for name in oracle_row_names
    }
    for entry in oracle.entries:
        if entry.row in oracle_entries and _family(entry.column) in set(
            PYOMO_VARIABLES.values()
        ):
            oracle_entries[entry.row].append((entry.column, entry.coefficient))
    oracle_rows = Counter(
        _row_signature(*oracle_bounds[name], oracle_entries[name])
        for name in oracle_row_names
    )
    python_counter = Counter(python_rows)
    missing_rows = sum((oracle_rows - python_counter).values())
    extra_rows = sum((python_counter - oracle_rows).values())
    column_mismatches = sum(
        python_columns.get(name) != signature
        for name, signature in oracle_columns.items()
    )
    mismatch_names = [
        name
        for name, signature in oracle_columns.items()
        if python_columns.get(name) != signature
    ]
    missing_columns = len(set(oracle_columns) - set(python_columns))
    extra_columns = len(set(python_columns) - set(oracle_columns))
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-reserve-stage7",
        "case": asdict(identifier),
        "sources": {
            "input_gdx": _source(input_gdx),
            "matrix_gdx": _source(matrix_gdx),
            "dictionary_gdx": _source(dictionary_gdx),
        },
        "projection": {
            "portable_sos2_rows_excluded": True,
            "portable_sos2_columns_excluded": True,
            "row_names_ignored": True,
            "row_signature": "canonical bounds plus semantic column/coefficient multiset",
        },
        "python": {
            "column_count": len(python_columns),
            "row_count": sum(python_counter.values()),
            "column_sha256": _digest(sorted(python_columns.items())),
            "row_sha256": _digest(sorted(python_counter.items(), key=repr)),
        },
        "gams": {
            "column_count": len(oracle_columns),
            "row_count": sum(oracle_rows.values()),
            "column_sha256": _digest(sorted(oracle_columns.items())),
            "row_sha256": _digest(sorted(oracle_rows.items(), key=repr)),
        },
        "differences": {
            "missing_columns": missing_columns,
            "extra_columns": extra_columns,
            "column_mismatches": column_mismatches,
            "missing_rows": missing_rows,
            "extra_rows": extra_rows,
            "unmapped_pyomo_terms": unmapped,
            "column_mismatches_by_family": dict(
                sorted(Counter(_family(name) for name in mismatch_names).items())
            ),
            "column_mismatch_sample": {
                name: {
                    "python": python_columns.get(name),
                    "gams": oracle_columns[name],
                }
                for name in mismatch_names[:10]
            },
            "missing_row_signature_sample": [
                repr(item) for item in list(oracle_rows - python_counter)[:2]
            ],
            "extra_row_signature_sample": [
                repr(item) for item in list(python_counter - oracle_rows)[:2]
            ],
        },
    }
    report["passed"] = not any(
        (
            missing_columns,
            extra_columns,
            column_mismatches,
            missing_rows,
            extra_rows,
            unmapped,
        )
    )
    return report


def _pyomo_projection(
    model: pyo.ConcreteModel,
) -> tuple[dict[str, tuple[Any, ...]], list[tuple[Any, ...]], int]:
    fixed = {
        id(variable): _value(variable)
        for variable in model.component_data_objects(pyo.Var, active=True)
        if variable.fixed
    }
    for variable in model.component_data_objects(pyo.Var, active=True):
        if id(variable) in fixed:
            variable.unfix()
    objective = next(model.component_data_objects(pyo.Objective, active=True))
    objective_repn = generate_standard_repn(objective.expr, compute_values=True)
    objective_by_id = {
        id(variable): float(coefficient)
        for variable, coefficient in zip(
            objective_repn.linear_vars, objective_repn.linear_coefs, strict=True
        )
    }
    names: dict[int, str] = {}
    columns: dict[str, tuple[Any, ...]] = {}
    for variable in model.component_data_objects(pyo.Var, active=True):
        family = PYOMO_VARIABLES.get(variable.parent_component().name)
        if family is None:
            continue
        name = _semantic(family, variable.index())
        names[id(variable)] = name
        if family in STAGE7_VARIABLE_FAMILIES:
            fixed_value = fixed.get(id(variable))
            columns[name] = _column_signature(
                fixed_value if fixed_value is not None else _bound(variable.lb, -math.inf),
                fixed_value if fixed_value is not None else _bound(variable.ub, math.inf),
                objective_by_id.get(id(variable), 0.0),
                "binary"
                if variable.is_binary()
                else "integer"
                if variable.is_integer()
                else "continuous",
            )
    rows: list[tuple[Any, ...]] = []
    unmapped = 0
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        if constraint.parent_component().name not in PYOMO_ROW_COMPONENTS:
            continue
        repn = generate_standard_repn(constraint.body, compute_values=True)
        constant = float(repn.constant or 0.0)
        entries: list[tuple[str, float]] = []
        for variable, coefficient in zip(
            repn.linear_vars, repn.linear_coefs, strict=True
        ):
            column_name = names.get(id(variable))
            if column_name is None:
                unmapped += 1
            elif float(coefficient) != 0.0:
                entries.append((column_name, float(coefficient)))
        rows.append(
            _row_signature(
                _bound(constraint.lower, -math.inf) - constant,
                _bound(constraint.upper, math.inf) - constant,
                entries,
            )
        )
    for variable in model.component_data_objects(pyo.Var, active=True):
        if id(variable) in fixed:
            variable.fix(fixed[id(variable)])
    return columns, rows, unmapped


def _column_signature(
    lower: float, upper: float, objective: float, discrete: str
) -> tuple[Any, ...]:
    return (_number(lower), _number(upper), _number(objective), discrete)


def _row_signature(
    lower: float, upper: float, entries: list[tuple[str, float]]
) -> tuple[Any, ...]:
    forward = (
        _number(lower),
        _number(upper),
        tuple(sorted((name, _number(value)) for name, value in entries)),
    )
    reverse = (
        _number(-upper),
        _number(-lower),
        tuple(sorted((name, _number(-value)) for name, value in entries)),
    )
    return min(forward, reverse, key=repr)


def _number(value: float) -> float | str:
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if abs(value) < 5e-12:
        return 0.0
    return round(value, 10)


def _bound(value: Any, default: float) -> float:
    return default if value is None else float(pyo.value(value))


def _value(value: Any) -> float:
    evaluated = pyo.value(value, exception=False)
    return 0.0 if evaluated is None else float(evaluated)


def _family(name: str) -> str:
    return name.split("[", 1)[0]


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=list).encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-gdx", type=Path, required=True)
    parser.add_argument("--matrix-gdx", type=Path, required=True)
    parser.add_argument("--dictionary-gdx", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--trading-period", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(
        input_gdx=args.input_gdx.resolve(),
        matrix_gdx=args.matrix_gdx.resolve(),
        dictionary_gdx=args.dictionary_gdx.resolve(),
        system_directory=args.system_directory.resolve(),
        identifier=CaseIdentifier(args.case_id, args.datetime, args.trading_period),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
