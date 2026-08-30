from __future__ import annotations

from dataclasses import replace
from itertools import product

import pyomo.environ as pyo
import pytest
from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.architecture import ModelAssembler
from pyspd.hvdc import audit_pricing_model
from pyspd.reserve import (
    IndependentReserveValidator,
    ReservePricingEngine,
    ReserveResultSchema,
    ReserveSolvePolicy,
    reserve_formulation,
    validate_reserve_price_finite_difference,
)
from pyspd.reserve.components import (
    ReserveOfferComponent,
    ReserveRiskComponent,
    ReserveSharingComponent,
)
from pyspd.reserve.data import RESERVE_CLASSES, RESERVE_TYPES, RISK_CLASSES
from tests.reserve.conftest import make_reserve_case


def build(*, secondary: bool = False):
    return ModelAssembler().assemble(
        reserve_formulation(), make_reserve_case(secondary=secondary)
    )


def test_gate7_is_class_composed_and_extensible() -> None:
    formulation = reserve_formulation()
    assert ReserveOfferComponent in formulation.components
    assert ReserveRiskComponent in formulation.components
    assert ReserveSharingComponent in formulation.components
    assert len({component.name for component in formulation.components}) == len(
        formulation.components
    )


def test_fir_sir_and_plro_twro_ilro_are_explicit() -> None:
    built = build()
    reserve = built.artifacts["reserve"]
    assert {(key[-2], key[-1]) for key in reserve} == set(
        product(RESERVE_CLASSES, RESERVE_TYPES)
    )
    assert len(built.artifacts["plsr_maximum"]) == 2
    assert len(built.artifacts["energy_reserve_maximum"]) == 2


def test_every_risk_class_and_secondary_risk_algebra_is_built() -> None:
    built = build(secondary=True)
    island_risk = built.artifacts["island_risk"]
    assert {key[-1] for key in island_risk} == set(RISK_CLASSES)
    assert len(built.artifacts["generator_island_risk"]) == 4
    assert len(built.artifacts["group_island_risk"]) == 2
    assert len(built.artifacts["hvdc_generator_island_risk"]) == 4
    assert len(built.artifacts["hvdc_manual_island_risk"]) == 8


def test_risk_group_ignores_mapping_to_offer_outside_active_domain() -> None:
    case = make_reserve_case()
    assert case.reserve is not None
    reserve = replace(
        case.reserve,
        risk_group_offer=case.reserve.risk_group_offer
        | {("C1", "T1", "G1", "INACTIVE", "genRisk")},
    )
    built = ModelAssembler().assemble(
        reserve_formulation(), replace(case, reserve=reserve)
    )
    assert len(built.artifacts["group_island_risk"]) == 2


@pytest.mark.parametrize("risk_class", RISK_CLASSES)
def test_every_risk_class_has_binding_and_nonbinding_cover_cases(
    risk_class: str,
) -> None:
    built = build(secondary=True)
    key = ("C1", "T1", "NI", "FIR", risk_class)
    risk = built.artifacts["island_risk"]
    island_reserve = built.artifacts["island_reserve"]
    deficit = (
        built.artifacts["reserve_deficit_ce"]
        if risk_class in {"genRisk", "DCCE", "manual", "HVDCsecRisk"}
        else built.artifacts["reserve_deficit_ece"]
    )
    risk[key].set_value(10.0)
    deficit[key[:4]].set_value(0.0)
    island_reserve[key[:4]].set_value(10.0)
    row = built.artifacts["reserve_requirement"][key]
    assert pyo.value(row.body) == pytest.approx(pyo.value(row.upper))
    island_reserve[key[:4]].set_value(11.0)
    assert pyo.value(row.body) < pyo.value(row.upper)


def test_nmir_uses_portable_adjacent_interval_mip_not_native_sos() -> None:
    built = build()
    assert len(built.artifacts["lambda_hvdc_energy_interval"]) == 12
    assert len(built.artifacts["lambda_hvdc_reserve_interval"]) == 96
    assert not tuple(built.model.component_data_objects(pyo.SOSConstraint, active=True))


def test_exact_reserve_share_perturbation_coefficients() -> None:
    built = build()
    definition = built.artifacts["sharing_constraints"]
    penalty = built.artifacts["reserve_share_penalty"]
    row = next(
        constraint
        for constraint in definition.values()
        if any(
            variable.parent_component() is penalty
            for variable in generate_standard_repn(constraint.body).linear_vars
        )
    )
    repn = generate_standard_repn(row.body, compute_values=True)
    coefficients = {
        variable.parent_component().local_name: float(coefficient)
        for variable, coefficient in zip(
            repn.linear_vars, repn.linear_coefs, strict=True
        )
    }
    assert abs(coefficients["SharedNFR"]) == pytest.approx(1e-5)
    assert abs(coefficients["SharedReserve"]) == pytest.approx(2e-5)
    assert abs(coefficients["ReserveShareEffectiveCE"]) == pytest.approx(3e-5)
    assert abs(coefficients["ReserveShareEffectiveECE"]) == pytest.approx(3e-5)


def test_net_benefit_excludes_the_vspd_commented_scarcity_constant() -> None:
    """The model objective must match vSPD's active ObjectiveFunction algebra."""

    base = make_reserve_case()
    scarcity_block = (*next(iter(base.nodes)), "t1")
    case = replace(
        base,
        scarcity_blocks=frozenset({scarcity_block}),
        scarcity_limit={scarcity_block: 100.0},
        scarcity_price={scarcity_block: 1_000.0},
        scarcity_enabled={period: 1.0 for period in base.periods},
    )
    built = ModelAssembler().assemble(reserve_formulation(), case)
    share_penalty = built.artifacts["reserve_share_penalty"]
    expected = (
        built.artifacts["system_benefit"]
        - built.artifacts["system_cost"]
        - built.artifacts["system_penalty"]
        - built.artifacts["scarcity_cost"]
        - sum(share_penalty[key] for key in case.periods)
    )
    actual_repn = generate_standard_repn(
        built.artifacts["net_benefit"], compute_values=True
    )
    expected_repn = generate_standard_repn(expected, compute_values=True)

    assert float(actual_repn.constant or 0.0) == pytest.approx(
        float(expected_repn.constant or 0.0)
    )
    assert {
        variable.name: float(coefficient)
        for variable, coefficient in zip(
            actual_repn.linear_vars, actual_repn.linear_coefs, strict=True
        )
    } == pytest.approx(
        {
            variable.name: float(coefficient)
            for variable, coefficient in zip(
                expected_repn.linear_vars, expected_repn.linear_coefs, strict=True
            )
        }
    )


def test_scip_mip_to_fixed_highs_rmip_and_independent_validation() -> None:
    built = build()
    outcome = ReserveSolvePolicy().solve(built)
    assert outcome.primary_mip is not None
    assert outcome.primary_mip.solve.backend == "native-scip"
    assert outcome.primary_mip.solve.status.value == "optimal"
    assert outcome.pricing_lp.backend == "highs"
    assert outcome.pricing_lp.status.value == "optimal"
    assert all(value >= 0.0 for value in outcome.fixed_sos_members.values())
    audit = audit_pricing_model(outcome)
    assert audit.passed, audit
    assert audit.fixed_name_count > 0
    assert audit.pricing_discrete_count == 0
    report = IndependentReserveValidator().validate(outcome)
    assert report.passed, max(report.residuals.items(), key=lambda item: item[1])
    prices = ReservePricingEngine().price(built, outcome)
    assert all(value >= 0.0 for value in prices.reserve.values())
    result = ReserveResultSchema().collect(built, outcome)
    assert dict(result.reserve_prices) == dict(prices.reserve)


def test_reserve_price_matches_fixed_rmip_rhs_perturbation() -> None:
    built = build()
    outcome = ReserveSolvePolicy().solve(built)
    key = ("C1", "T1", "NI", "FIR")
    check = validate_reserve_price_finite_difference(outcome, key)
    assert check.passed, check
