"""Explicit adapter for legacy vSPD final-pricing GDX input symbols."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pyspd.data.catalog import SymbolCatalog, SymbolSpec
from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.values import ScalarValue, ValueKind

LEGACY_V3_INPUT_SCHEMA = "vspd-v3-final-pricing"
V5_INPUT_SCHEMA = "vspd-v5.0.6"
SUPPORTED_INPUT_SCHEMAS = frozenset({V5_INPUT_SCHEMA, LEGACY_V3_INPUT_SCHEMA})

_ENERGY_COMPONENT = {
    "i_GenerationMWOffer": "limitMW",
    "i_GenerationMWOfferPrice": "price",
    "i_BidMW": "limitMW",
    "i_BidPrice": "price",
}
_BRANCH_COMPONENT = {
    "i_branchResistance": "resistance",
    "i_branchSusceptance": "susceptance",
    "i_BranchFixedLosses": "fixedLosses",
    "i_numLossTranches": "numLossTranches",
}
_OFFER_COMPONENT = {
    "i_InitialMW": "initialMW",
    "i_RampUpRate": "rampUpRate",
    "i_RampDnRate": "rampDnRate",
    "i_ReserveGenerationMaximum": "resrvGenMax",
    "i_WindOffer": "isIG",
    "i_FKBandMW": "FKbandMW",
    "i_IsPriceResponse": "isPriceResponse",
    "i_PotentialMW": "potentialMW",
}
_RHS_COMPONENT = {
    "i_ConstraintLimit": "cnstrLimit",
    "i_ConstraintSense": "cnstrSense",
}
_RISK_CLASS = {
    "GENRISK": "genRisk",
    "GENRISK_ECE": "genRiskECE",
    "DCCE": "DCCE",
    "DCECE": "DCECE",
    "Manual": "manual",
    "Manual_ECE": "manualECE",
    "HVDCSECRISK_CE": "HVDCsecRisk",
    "HVDCSECRISK_ECE": "HVDCsecRiskECE",
}
_RISK_COMPONENT = {
    "i_FreeReserve": "freeReserve",
    "i_RiskAdjustmentFactor": "adjustFactor",
    "i_HVDCPoleRampUp": "HVDCRampUp",
}
_RESERVE_TYPE = {"PLSR": "PLRO", "TWDR": "TWRO", "ILR": "ILRO"}
_RESERVE_COMPONENT = {
    "i_PLSROfferPercentage": "plsrPct",
    "i_PLSROfferMax": "limitMW",
    "i_PLSROfferPrice": "price",
    "i_TWDROfferMax": "limitMW",
    "i_TWDROfferPrice": "price",
    "i_ILROfferMax": "limitMW",
    "i_ILROfferPrice": "price",
}


class LegacyV3InputAdapter:
    """Normalize one 48-period legacy final-pricing input to the v5 source shape.

    The adapter changes representation only. It retains every source numeric
    value and makes all label translations explicit; the normal date-sensitive
    compatibility preprocessing remains responsible for formulation behavior.
    """

    def normalize(self, source: RawSymbols) -> RawSymbols:
        by_name = {symbol.name: symbol for symbol in source.symbols}
        self._validate_source(by_name)
        period_map = self._period_map(by_name)
        cases = {
            tp: (f"V3{date_time[:11].replace('-', '').replace(' ', '')}{tp}", date_time)
            for tp, date_time in period_map.items()
        }
        records: dict[str, list[RawRecord]] = {
            spec.name: [] for spec in SymbolCatalog.vspd_v5().symbols
        }

        self._identity_records(by_name, cases, records)
        self._copy_global(by_name, records, "i_node")
        self._copy_global(by_name, records, "i_bus")
        self._simple_period_symbols(by_name, cases, records)
        self._node_parameters(by_name, cases, records)
        self._island_parameters(by_name, cases, records)
        self._branch_parameters(by_name, cases, records)
        self._offer_parameters(by_name, cases, records)
        self._reserve_offers(by_name, cases, records)
        self._bid_parameters(by_name, cases, records)
        self._risk_parameters(by_name, cases, records)
        self._reserve_sharing(by_name, cases, records)

        specifications = {spec.name: spec for spec in SymbolCatalog.vspd_v5().symbols}
        normalized = tuple(
            self._symbol(specifications[name], tuple(items))
            for name, items in records.items()
        )
        return RawSymbols(source.source_name, source.source_sha256, normalized)

    @staticmethod
    def _validate_source(by_name: Mapping[str, RawSymbol]) -> None:
        required = {
            "caseName",
            "i_day",
            "i_month",
            "i_year",
            "i_dateTimeTradePeriodMap",
            "i_StudyTradePeriod",
            "i_tradePeriodNodeDemand",
            "i_tradePeriodEnergyOffer",
        }
        missing = sorted(required - set(by_name))
        if missing:
            raise ValueError(
                f"legacy v3 input is missing symbols: {', '.join(missing)}"
            )
        if "i_caseDefn" in by_name:
            raise ValueError("legacy v3 adapter rejects an already case-indexed input")

    @staticmethod
    def _period_map(by_name: Mapping[str, RawSymbol]) -> dict[str, str]:
        studied = {
            record.keys[0]
            for record in by_name["i_StudyTradePeriod"].records
            if _number(record) != 0.0
        }
        result = {
            record.keys[1]: record.keys[0]
            for record in by_name["i_dateTimeTradePeriodMap"].records
            if record.keys[1] in studied
        }
        if len(result) != len(studied) or not result:
            raise ValueError("legacy trade-period/date-time mapping is incomplete")
        return result

    def _identity_records(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        case_name = by_name["caseName"].records[0].keys[0]
        day = _scalar(by_name["i_day"])
        month = _scalar(by_name["i_month"])
        year = _scalar(by_name["i_year"])
        for name, value in (("day", day), ("month", month), ("year", year)):
            output["i_gdxDate"].append(_numeric((name,), value))
        interval = _scalar(by_name["i_tradingPeriodLength"])
        for tp, (case_id, date_time) in cases.items():
            output["i_caseDefn"].append(_set((case_id, f"{case_name}_{tp}", date_time)))
            output["i_runMode"].extend(
                (
                    _numeric((case_id, "studyMode"), 111.0),
                    _numeric((case_id, "intervalLength"), interval),
                )
            )
            output["i_dateTimeTradePeriodMap"].append(_set((case_id, date_time, tp)))
            output["i_dateTimeParameter"].extend(
                (
                    _numeric((case_id, date_time, "usegeninitialMW"), 1.0),
                    _numeric((case_id, date_time, "maxSolveLoop"), 5.0),
                )
            )
            output["i_priceCaseFilesPublishedSecs"].append(
                _numeric((case_id, tp), interval * 60.0)
            )

    @staticmethod
    def _copy_global(
        by_name: Mapping[str, RawSymbol],
        output: dict[str, list[RawRecord]],
        name: str,
    ) -> None:
        output[name].extend(by_name[name].records)

    def _simple_period_symbols(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        mapping: dict[str, tuple[str, Callable[[tuple[str, ...]], tuple[str, ...]]]] = {
            "i_tradePeriodBusIsland": ("i_dateTimeBusIsland", _identity),
            "i_tradePeriodBusElectricalIsland": (
                "i_dateTimeBusElectricalIsland",
                _identity,
            ),
            "i_tradePeriodNodeBus": ("i_dateTimeNodeBus", _identity),
            "i_tradePeriodNodeBusAllocationFactor": (
                "i_dateTimeNodeBusAllocationFactor",
                _identity,
            ),
            "i_tradePeriodBranchDefn": ("i_dateTimeBranchDefn", _identity),
            "i_tradePeriodBranchConstraintFactors": (
                "i_dateTimeBranchConstraintFactors",
                _identity,
            ),
            "i_tradePeriodBranchConstraintRHS": (
                "i_dateTimeBranchConstraintRHS",
                lambda keys: (*keys[:-1], _RHS_COMPONENT[keys[-1]]),
            ),
            "i_tradePeriodOfferNode": ("i_dateTimeOfferNode", _identity),
            "i_tradePeriodOfferTrader": ("i_dateTimeOfferTrader", _identity),
            "i_tradePeriodPrimarySecondaryOffer": (
                "i_dateTimePrimarySecondaryOffer",
                _identity,
            ),
            "i_tradePeriodRiskGroup": (
                "i_dateTimeRiskGroup",
                lambda keys: (*keys[:-1], _RISK_CLASS[keys[-1]]),
            ),
            "i_tradePeriodEnergyOffer": (
                "i_dateTimeEnergyOffer",
                lambda keys: (*keys[:-1], _ENERGY_COMPONENT[keys[-1]]),
            ),
            "i_tradePeriodBidNode": ("i_dateTimeBidNode", _identity),
            "i_tradePeriodBidTrader": ("i_dateTimeBidTrader", _identity),
            "i_tradePeriodEnergyBid": (
                "i_dateTimeEnergyBid",
                lambda keys: (*keys[:-1], _ENERGY_COMPONENT[keys[-1]]),
            ),
            "i_tradePeriodMNodeConstraintRHS": (
                "i_dateTimeMNCnstrRHS",
                lambda keys: (*keys[:-1], _RHS_COMPONENT[keys[-1]]),
            ),
            "i_tradePeriodMNodeEnergyOfferConstraintFactors": (
                "i_dateTimeMNCnstrEnrgFactors",
                _identity,
            ),
            "i_tradePeriodMNodeReserveOfferConstraintFactors": (
                "i_dateTimeMNCnstrResrvFactors",
                lambda keys: (*keys[:-1], _RESERVE_TYPE[keys[-1]]),
            ),
            "i_tradePeriodMNodeEnergyBidConstraintFactors": (
                "i_dateTimeMNCnstrEnrgBidFactors",
                _identity,
            ),
            "i_tradePeriodMNodeILReserveBidConstraintFactors": (
                "i_dateTimeMNCnstrResrvBidFactors",
                _identity,
            ),
        }
        for source_name, (target, transform) in mapping.items():
            self._copy_period(by_name, cases, output, source_name, target, transform)

    def _node_parameters(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        for source_name, component in (
            ("i_tradePeriodNodeDemand", "demand"),
            ("i_tradePeriodReferenceNode", "referenceNode"),
        ):
            for record in by_name[source_name].records:
                prefix = _prefix(record, cases)
                output["i_dateTimeNodeParameter"].append(
                    RawRecord((*prefix, record.keys[1], component), record.values)
                )

    def _island_parameters(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        for record in by_name["i_tradePeriodSharedNFRloadOffset"].records:
            output["i_dateTimeIslandParameter"].append(
                RawRecord(
                    (*_prefix(record, cases), record.keys[1], "sharedNFRLoadOffset"),
                    record.values,
                )
            )
        for record in by_name["i_tradePeriodRMTReserveLimit"].records:
            component = f"RMTlimit{record.keys[2]}"
            output["i_dateTimeIslandParameter"].append(
                RawRecord(
                    (*_prefix(record, cases), record.keys[1], component), record.values
                )
            )

    def _branch_parameters(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        target = output["i_dateTimeBranchParameter"]
        for record in by_name["i_tradePeriodBranchParameter"].records:
            target.append(
                RawRecord(
                    (
                        *_prefix(record, cases),
                        record.keys[1],
                        _BRANCH_COMPONENT[record.keys[2]],
                    ),
                    record.values,
                )
            )
        for record in by_name["i_tradePeriodBranchCapacity"].records:
            prefix = (*_prefix(record, cases), record.keys[1])
            target.extend(
                (
                    RawRecord((*prefix, "forwardCap"), record.values),
                    RawRecord((*prefix, "backwardCap"), record.values),
                )
            )
        for source_name, component in (
            ("i_tradePeriodBranchOpenStatus", "isOpen"),
            ("i_tradePeriodHVDCBranch", "HVDCbranch"),
        ):
            for record in by_name[source_name].records:
                target.append(
                    RawRecord(
                        (*_prefix(record, cases), record.keys[1], component),
                        record.values,
                    )
                )

    def _offer_parameters(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        target = output["i_dateTimeOfferParameter"]
        offers: set[tuple[str, str]] = set()
        for record in by_name["i_tradePeriodOfferParameter"].records:
            tp, offer, component = record.keys
            offers.add((tp, offer))
            values = record.values
            if component in {"i_RampUpRate", "i_RampDnRate"}:
                values = {"value": ScalarValue.finite(60.0 * _number(record))}
            target.append(
                RawRecord(
                    (*_prefix(record, cases), offer, _OFFER_COMPONENT[component]),
                    values,
                )
            )
        risk_generators = {
            record.keys for record in by_name["i_tradePeriodRiskGenerator"].records
        }
        for tp, offer in sorted(offers):
            case_id, date_time = cases[tp]
            prefix = (case_id, date_time, offer)
            target.extend(
                (
                    _numeric((*prefix, "dispatchable"), 1.0),
                    _numeric((*prefix, "maxFactorFIR"), 1.0),
                    _numeric((*prefix, "maxFactorSIR"), 1.0),
                )
            )
            if (tp, offer) in risk_generators:
                target.append(_numeric((*prefix, "riskGenerator"), 1.0))

    def _reserve_offers(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        configurations = (
            ("i_tradePeriodFastPLSRoffer", "FIR", "PLRO"),
            ("i_tradePeriodSustainedPLSRoffer", "SIR", "PLRO"),
            ("i_tradePeriodFastTWDRoffer", "FIR", "TWRO"),
            ("i_tradePeriodSustainedTWDRoffer", "SIR", "TWRO"),
            ("i_tradePeriodFastILRoffer", "FIR", "ILRO"),
            ("i_tradePeriodSustainedILRoffer", "SIR", "ILRO"),
        )
        target = output["i_dateTimeReserveOffer"]
        for source_name, reserve_class, reserve_type in configurations:
            for record in by_name[source_name].records:
                tp, offer, block, component = record.keys
                target.append(
                    RawRecord(
                        (
                            *cases[tp],
                            offer,
                            reserve_class,
                            reserve_type,
                            block,
                            _RESERVE_COMPONENT[component],
                        ),
                        record.values,
                    )
                )

    def _bid_parameters(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        for record in by_name["i_tradePeriodDispatchableBid"].records:
            output["i_dateTimeBidParameter"].append(
                _numeric((*_prefix(record, cases), record.keys[1], "dispatchable"), 1.0)
            )

    def _risk_parameters(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        target = output["i_dateTimeRiskParameter"]
        for record in by_name["i_tradePeriodRiskParameter"].records:
            tp, island, reserve_class, risk_class, component = record.keys
            target.append(
                RawRecord(
                    (
                        *cases[tp],
                        island,
                        reserve_class,
                        _RISK_CLASS[risk_class],
                        _RISK_COMPONENT[component],
                    ),
                    record.values,
                )
            )
        for source_name, risk_class in (
            ("i_tradePeriodManualRisk", "manual"),
            ("i_tradePeriodManualRisk_ECE", "manualECE"),
        ):
            for record in by_name[source_name].records:
                tp, island, reserve_class = record.keys
                target.append(
                    RawRecord(
                        (*cases[tp], island, reserve_class, risk_class, "minRisk"),
                        record.values,
                    )
                )
        for record in by_name["i_tradePeriodReserveEffectiveFactor"].records:
            tp, island, reserve_class, risk_class = record.keys
            target.append(
                RawRecord(
                    (
                        *cases[tp],
                        island,
                        reserve_class,
                        _RISK_CLASS[risk_class],
                        "sharingEffectiveFactor",
                    ),
                    record.values,
                )
            )

    def _reserve_sharing(
        self,
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
    ) -> None:
        target = output["i_dateTimeReserveSharing"]
        for source_name, prefix in (
            ("i_tradePeriodReserveSharing", "sharing"),
            ("i_tradePeriodReserveRoundPower", "roundPwr"),
        ):
            for record in by_name[source_name].records:
                target.append(
                    RawRecord(
                        (*_prefix(record, cases), f"{prefix}{record.keys[1]}"),
                        record.values,
                    )
                )
        for record in by_name["i_tradePeriodModulationRisk"].records:
            component = "MRCE" if record.keys[1] == "DCCE" else "MRECE"
            target.append(
                RawRecord((*_prefix(record, cases), component), record.values)
            )
        for source_name, component in (
            ("i_tradePeriodRoundPower2Mono", "roundPwr2Mono"),
            ("i_tradePeriodBipole2Mono", "biPole2Mono"),
            ("i_tradePeriodReserveSharingPoleMin", "monoPoleMin"),
            ("i_tradePeriodHVDClossScalingFactor", "lossScalingFactorHVDC"),
            ("i_tradePeriodSharedNFRfactor", "sharedNFRfactor"),
        ):
            for record in by_name[source_name].records:
                target.append(
                    RawRecord((*_prefix(record, cases), component), record.values)
                )
        for record in by_name["i_tradePeriodHVDCcontrolBand"].records:
            component = f"{record.keys[1].casefold()}HVDCcontrolBand"
            target.append(
                RawRecord((*_prefix(record, cases), component), record.values)
            )

    @staticmethod
    def _copy_period(
        by_name: Mapping[str, RawSymbol],
        cases: Mapping[str, tuple[str, str]],
        output: dict[str, list[RawRecord]],
        source_name: str,
        target_name: str,
        transform: Callable[[tuple[str, ...]], tuple[str, ...]],
    ) -> None:
        source = by_name[source_name]
        for record in source.records:
            output[target_name].append(
                RawRecord(
                    (*_prefix(record, cases), *transform(record.keys[1:])),
                    record.values,
                )
            )

    @staticmethod
    def _symbol(spec: SymbolSpec, records: tuple[RawRecord, ...]) -> RawSymbol:
        name = spec.name
        dimension = spec.dimension
        orders: list[tuple[str, ...]] = []
        for index in range(dimension):
            orders.append(
                tuple(dict.fromkeys(record.keys[index] for record in records))
            )
        return RawSymbol(
            name,
            SymbolType(spec.symbol_type),
            dimension,
            spec.domains,
            f"Normalized from legacy vSPD final-pricing input: {name}",
            tuple(orders),
            records,
        )


def _prefix(record: RawRecord, cases: Mapping[str, tuple[str, str]]) -> tuple[str, str]:
    try:
        return cases[record.keys[0]]
    except KeyError as error:
        raise ValueError(
            f"legacy record references an unstudiable period: {record.keys[0]}"
        ) from error


def _identity(keys: tuple[str, ...]) -> tuple[str, ...]:
    return keys


def _number(record: RawRecord) -> float:
    value = record.values.get("value")
    if value is None or value.kind not in {ValueKind.FINITE, ValueKind.EPS}:
        raise ValueError(f"legacy numeric record is not finite: {record.keys}")
    if value.kind is ValueKind.EPS:
        return 0.0
    assert value.number is not None
    return float(value.number)


def _scalar(symbol: RawSymbol) -> float:
    if len(symbol.records) != 1:
        raise ValueError(f"legacy scalar {symbol.name} must contain one record")
    return _number(symbol.records[0])


def _numeric(keys: tuple[str, ...], value: float) -> RawRecord:
    return RawRecord(keys, {"value": ScalarValue.finite(value)})


def _set(keys: tuple[str, ...]) -> RawRecord:
    return RawRecord(keys, {"element_text": ScalarValue.text("")})
