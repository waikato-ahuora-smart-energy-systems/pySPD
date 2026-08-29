from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date

import pytest

from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import RawRecord, RawSymbol, RawSymbols, ScalarValue, SymbolType


def _symbol(
    name: str,
    symbol_type: SymbolType,
    domains: tuple[str, ...],
    rows: list[tuple[tuple[str, ...], float | None]],
) -> RawSymbol:
    records = tuple(
        RawRecord(keys, {} if value is None else {"value": ScalarValue.finite(value)})
        for keys, value in rows
    )
    uels = tuple(
        tuple(dict.fromkeys(record.keys[index] for record in records))
        for index in range(len(domains))
    )
    return RawSymbol(
        name,
        symbol_type,
        len(domains),
        domains,
        "Gate 3 deterministic fixture",
        uels,
        records,
    )


def _set(name: str, domains: tuple[str, ...], *keys: tuple[str, ...]) -> RawSymbol:
    return _symbol(name, SymbolType.SET, domains, [(key, None) for key in keys])


def _parameter(
    name: str,
    domains: tuple[str, ...],
    *rows: tuple[tuple[str, ...], float],
) -> RawSymbol:
    return _symbol(name, SymbolType.PARAMETER, domains, list(rows))


def make_case(input_date: date = date(2024, 1, 2)) -> CaseData:
    ca, dt = "C1", "D1"
    symbols = (
        _parameter(
            "i_gdxDate",
            ("*",),
            (("year",), float(input_date.year)),
            (("month",), float(input_date.month)),
            (("day",), float(input_date.day)),
        ),
        _set("i_caseDefn", ("ca", "cn", "rundt"), (ca, "case", "run")),
        _parameter(
            "i_runMode",
            ("ca", "casePar"),
            ((ca, "studyMode"), 101.0),
            ((ca, "intervalLength"), 30.0),
        ),
        _set("i_dateTimeTradePeriodMap", ("ca", "dt", "tp"), (ca, dt, "1")),
        _parameter(
            "i_dateTimeParameter",
            ("ca", "dt", "dtPar"),
            ((ca, dt, "enrgScarcity"), 1.0),
            ((ca, dt, "resrvScarcity"), 0.0),
            ((ca, dt, "badPriceFactor"), 0.0),
            ((ca, dt, "useActualLoad"), 0.0),
            ((ca, dt, "igIncreaseLimitRTD"), 3.0),
        ),
        _parameter(
            "i_dateTimeIslandParameter",
            ("ca", "dt", "isl", "islPar"),
            ((ca, dt, "NI", "MWIPS"), 100.0),
            ((ca, dt, "NI", "PSD"), 10.0),
            ((ca, dt, "NI", "Losses"), 5.0),
            ((ca, dt, "NI", "SPDLoadCalcLosses"), 4.0),
            ((ca, dt, "SI", "MWIPS"), 80.0),
            ((ca, dt, "SI", "PSD"), 0.0),
            ((ca, dt, "SI", "Losses"), 4.0),
            ((ca, dt, "SI", "SPDLoadCalcLosses"), 3.0),
        ),
        _parameter(
            "i_dateTimeNodeParameter",
            ("ca", "dt", "n", "nodePar"),
            ((ca, dt, "N1", "demand"), 25.0),
            ((ca, dt, "N2", "demand"), 80.0),
            ((ca, dt, "N1", "initialLoad"), 90.0),
            ((ca, dt, "N2", "initialLoad"), 70.0),
            ((ca, dt, "N1", "conformingFactor"), 1.0),
            ((ca, dt, "N2", "conformingFactor"), 1.0),
            ((ca, dt, "N1", "nonConformingFactor"), 0.0),
            ((ca, dt, "N2", "nonConformingFactor"), 0.0),
            ((ca, dt, "N1", "loadIsOverride"), 0.0),
            ((ca, dt, "N2", "loadIsOverride"), 0.0),
            ((ca, dt, "N1", "loadIsBad"), 0.0),
            ((ca, dt, "N2", "loadIsBad"), 0.0),
            ((ca, dt, "N1", "loadIsNCL"), 0.0),
            ((ca, dt, "N2", "loadIsNCL"), 0.0),
            ((ca, dt, "N1", "maxLoad"), 200.0),
            ((ca, dt, "N2", "maxLoad"), 200.0),
            ((ca, dt, "N1", "instructedLoadShed"), 0.0),
            ((ca, dt, "N2", "instructedLoadShed"), 0.0),
            ((ca, dt, "N1", "instructedShedActive"), 0.0),
            ((ca, dt, "N2", "instructedShedActive"), 0.0),
            ((ca, dt, "N1", "dispatchedLoad"), 0.0),
            ((ca, dt, "N2", "dispatchedLoad"), 0.0),
            ((ca, dt, "N1", "dispatchedGeneration"), 0.0),
            ((ca, dt, "N2", "dispatchedGeneration"), 0.0),
        ),
        _set(
            "i_dateTimeBusIsland",
            ("ca", "dt", "b", "isl"),
            (ca, dt, "B1", "NI"),
            (ca, dt, "B2", "SI"),
        ),
        _parameter(
            "i_dateTimeBusElectricalIsland",
            ("ca", "dt", "b"),
            ((ca, dt, "B1"), 1.0),
            ((ca, dt, "B2"), 2.0),
        ),
        _set(
            "i_dateTimeNodeBus",
            ("ca", "dt", "n", "b"),
            (ca, dt, "N1", "B1"),
            (ca, dt, "N2", "B2"),
        ),
        _parameter(
            "i_dateTimeNodeBusAllocationFactor",
            ("ca", "dt", "n", "b"),
            ((ca, dt, "N1", "B1"), 2.0),
            ((ca, dt, "N2", "B2"), 4.0),
        ),
        _set(
            "i_dateTimeBranchDefn",
            ("ca", "dt", "br", "b1", "b2"),
            (ca, dt, "BR1", "B1", "B2"),
            (ca, dt, "HV1", "B2", "B1"),
        ),
        _parameter(
            "i_dateTimeBranchParameter",
            ("ca", "dt", "br", "brPar"),
            *(
                (((ca, dt, branch, component), value))
                for branch, values in {
                    "BR1": {
                        "isOpen": 0.0,
                        "forwardCap": 100.0,
                        "backwardCap": 80.0,
                        "HVDCbranch": 0.0,
                        "resistance": 0.02,
                        "susceptance": 0.3,
                        "fixedLosses": 1.0,
                        "numLossTranches": 3.0,
                    },
                    "HV1": {
                        "isOpen": 0.0,
                        "forwardCap": 200.0,
                        "backwardCap": 0.0,
                        "HVDCbranch": 1.0,
                        "resistance": 0.01,
                        "susceptance": 0.0,
                        "fixedLosses": 2.0,
                        "numLossTranches": 1.0,
                    },
                }.items()
                for component, value in values.items()
            ),
        ),
        _parameter(
            "i_dateTimeBranchConstraintFactors",
            ("ca", "dt", "brCstr", "br"),
            ((ca, dt, "BC1", "BR1"), 1.0),
        ),
        _parameter(
            "i_dateTimeBranchConstraintRHS",
            ("ca", "dt", "brCstr", "CstrRHS"),
            ((ca, dt, "BC1", "cnstrSense"), -1.0),
            ((ca, dt, "BC1", "cnstrLimit"), 90.0),
            ((ca, dt, "BC1", "rampingCnstr"), 0.0),
        ),
        _set(
            "i_dateTimeOfferNode",
            ("ca", "dt", "o", "n"),
            (ca, dt, "O1", "N1"),
            (ca, dt, "O2", "N1"),
        ),
        _set(
            "i_dateTimePrimarySecondaryOffer",
            ("ca", "dt", "o", "o1"),
            (ca, dt, "O1", "O2"),
        ),
        _parameter(
            "i_dateTimeOfferParameter",
            ("ca", "dt", "o", "offerPar"),
            *(
                (((ca, dt, offer, component), value))
                for offer, values in {
                    "O1": {
                        "initialMW": 50.0,
                        "solvedInitialMW": 49.0,
                        "rampUpRate": 5.0,
                        "rampDnRate": 4.0,
                        "resrvGenMax": 100.0,
                        "isIG": 1.0,
                        "isPriceResponse": 1.0,
                        "potentialMW": 50.0,
                        "maxFactorFIR": 0.8,
                        "maxFactorSIR": 0.9,
                        "dispatchable": 1.0,
                    },
                    "O2": {
                        "initialMW": 10.0,
                        "solvedInitialMW": 9.0,
                        "rampUpRate": 2.0,
                        "rampDnRate": 2.0,
                        "resrvGenMax": 20.0,
                        "isIG": 0.0,
                        "isPriceResponse": 0.0,
                        "potentialMW": 0.0,
                        "maxFactorFIR": 1.0,
                        "maxFactorSIR": 1.0,
                        "dispatchable": 1.0,
                    },
                }.items()
                for component, value in values.items()
            ),
        ),
        _parameter(
            "i_dateTimeEnergyOffer",
            ("ca", "dt", "o", "blk", "bidofrCmpnt"),
            ((ca, dt, "O1", "t1", "limitMW"), 100.0),
            ((ca, dt, "O1", "t1", "price"), 50.0),
            ((ca, dt, "O1", "t2", "limitMW"), 10.0),
            ((ca, dt, "O1", "t2", "price"), 70.0),
            ((ca, dt, "O2", "t1", "limitMW"), 20.0),
            ((ca, dt, "O2", "t1", "price"), 60.0),
        ),
        _parameter(
            "i_dateTimeReserveOffer",
            ("ca", "dt", "o", "resC", "resT", "blk", "bidofrCmpnt"),
            ((ca, dt, "O1", "FIR", "PLRO", "t1", "limitMW"), 10.0),
            ((ca, dt, "O1", "FIR", "PLRO", "t1", "price"), 4.0),
            ((ca, dt, "O1", "FIR", "PLRO", "t1", "plsrPct"), 25.0),
        ),
        _set("i_dateTimeBidNode", ("ca", "dt", "bd", "n"), (ca, dt, "BD1", "N2")),
        _parameter(
            "i_dateTimeBidParameter",
            ("ca", "dt", "bd", "bidPar"),
            ((ca, dt, "BD1", "dispatchable"), 1.0),
            ((ca, dt, "BD1", "difference"), 0.0),
        ),
        _parameter(
            "i_dateTimeEnergyBid",
            ("ca", "dt", "bd", "blk", "bidofrCmpnt"),
            ((ca, dt, "BD1", "t1", "limitMW"), 30.0),
            ((ca, dt, "BD1", "t1", "price"), 100.0),
        ),
        _parameter(
            "i_dateTimeMNCnstrRHS",
            ("ca", "dt", "MnodeCstr", "CstrRHS"),
            ((ca, dt, "MC1", "cnstrSense"), 1.0),
            ((ca, dt, "MC1", "cnstrLimit"), 150.0),
        ),
        _parameter(
            "i_dateTimeMNCnstrEnrgFactors",
            ("ca", "dt", "MnodeCstr", "o"),
            ((ca, dt, "MC1", "O1"), 1.0),
        ),
        _parameter(
            "i_dateTimeMNCnstrResrvFactors",
            ("ca", "dt", "MnodeCstr", "o", "resC", "resT"),
        ),
        _parameter("i_dateTimeMNCnstrEnrgBidFactors", ("ca", "dt", "MnodeCstr", "bd")),
        _parameter(
            "i_dateTimeMNCnstrResrvBidFactors", ("ca", "dt", "MnodeCstr", "bd", "resC")
        ),
        _set(
            "i_dateTimeRiskGroup",
            ("ca", "dt", "rg", "o", "riskC"),
            (ca, dt, "RG1", "O1", "genRisk"),
        ),
        _parameter("i_dateTimeRiskGroupBranch", ("ca", "dt", "rg", "br", "riskC")),
        _parameter(
            "i_dateTimeRiskParameter",
            ("ca", "dt", "isl", "resC", "riskC", "riskPar"),
            ((ca, dt, "NI", "FIR", "genRisk", "adjustFactor"), 0.95),
        ),
        _parameter(
            "i_dateTimeReserveSharing",
            ("ca", "dt", "resPar"),
            ((ca, dt, "sharingFIR"), 1.0),
            ((ca, dt, "sharingSIR"), 1.0),
            ((ca, dt, "roundPwrFIR"), 10.0),
            ((ca, dt, "roundPwrSIR"), 12.0),
            ((ca, dt, "MRCE"), 5.0),
            ((ca, dt, "MRECE"), 6.0),
            ((ca, dt, "roundPwr2Mono"), 100.0),
            ((ca, dt, "biPole2Mono"), 120.0),
        ),
        _parameter(
            "i_dateTimeScarcityNationalFactor",
            ("ca", "dt", "blk", "bidofrCmpnt"),
            ((ca, dt, "t1", "price"), 1000.0),
            ((ca, dt, "t2", "price"), 2000.0),
        ),
        _parameter(
            "i_dateTimeScarcityResrvLimit",
            ("ca", "dt", "isl", "resC", "blk", "bidofrCmpnt"),
            ((ca, dt, "NI", "FIR", "t1", "limitMW"), 5.0),
            ((ca, dt, "NI", "FIR", "t1", "price"), 500.0),
        ),
    )
    raw = RawSymbols("gate3.gdx", hashlib.sha256(b"gate3").hexdigest(), symbols)
    return CaseData("vspd-v5.0.6", CaseIdentifier(ca, dt, "1"), raw)


@pytest.fixture
def representative_case() -> CaseData:
    return make_case()


@pytest.fixture
def case_factory() -> Callable[[date], CaseData]:
    return make_case
