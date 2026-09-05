from __future__ import annotations

import json

import pytest

from pyspd.application import (
    CBC_CLP_VALIDATION_SOLVER_PROFILE,
    CBC_HIGHS_VALIDATION_SOLVER_PROFILE,
    CLP_VALIDATION_SOLVER_PROFILE,
    PORTABLE_SOLVER_PROFILE,
    ApplicationConfiguration,
    ConfigurationError,
    PyspdApplication,
)
from pyspd.cli import main
from pyspd.data import LEGACY_V3_INPUT_SCHEMA, V5_INPUT_SCHEMA
from pyspd.orchestration import ReserveCaseExecutor
from pyspd.solver import CbcBackend, ClpBackend
from pyspd.v16 import SPD16_FORMULATION_ID

FORMULATION = "vspd-v5.0.6-reserve"


def test_application_configuration_is_strict_and_hash_bound(tmp_path) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")
    config = ApplicationConfiguration(
        formulation_id=FORMULATION,
        input_path=source,
        output_directory=tmp_path / "output",
        source_sha256="0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8",
        gams_system_directory=tmp_path,
    )
    assert len(config.logical_sha256) == 64
    assert config.input_path == source.resolve()
    assert config.solver_profile == PORTABLE_SOLVER_PROFILE
    assert config.input_schema == V5_INPUT_SCHEMA

    selected = ApplicationConfiguration(
        formulation_id=FORMULATION,
        input_path=source,
        output_directory=tmp_path / "selected-output",
        source_sha256="0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8",
        gams_system_directory=tmp_path,
        case_ids=("CASE-2", "CASE-1"),
    )
    assert selected.case_ids == ("CASE-2", "CASE-1")
    assert selected.logical_sha256 != config.logical_sha256

    try:
        ApplicationConfiguration(
            formulation_id=FORMULATION,
            input_path=source,
            output_directory=tmp_path / "output",
            source_sha256="0" * 64,
            gams_system_directory=tmp_path,
        )
    except ConfigurationError as error:
        assert "hash" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("source hash mismatch was accepted")


def test_application_configuration_rejects_ambiguous_case_selection(tmp_path) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")

    for case_ids in (("CASE-1", "CASE-1"), ("",)):
        try:
            ApplicationConfiguration(
                formulation_id=FORMULATION,
                input_path=source,
                output_directory=tmp_path / "output",
                source_sha256=(
                    "0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8"
                ),
                gams_system_directory=tmp_path,
                case_ids=case_ids,
            )
        except ConfigurationError as error:
            assert "case_ids" in str(error)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("ambiguous case selection was accepted")


def test_application_rejects_nonpositive_preparation_bound(tmp_path) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")
    configuration = ApplicationConfiguration(
        formulation_id=FORMULATION,
        input_path=source,
        output_directory=tmp_path / "output",
        source_sha256=(
            "0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8"
        ),
        gams_system_directory=tmp_path,
    )

    with pytest.raises(ConfigurationError, match="maximum_cases"):
        next(PyspdApplication().iter_prepared_cases(configuration, maximum_cases=0))


def test_application_configuration_requires_an_explicit_supported_input_schema(
    tmp_path,
) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")
    source_sha256 = "0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8"

    try:
        ApplicationConfiguration(
            formulation_id=FORMULATION,
            input_path=source,
            output_directory=tmp_path / "output",
            source_sha256=source_sha256,
            gams_system_directory=tmp_path,
            input_schema="auto-detect",
        )
    except ConfigurationError as error:
        assert "input_schema" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unsupported input schema was accepted")

    try:
        ApplicationConfiguration(
            formulation_id=SPD16_FORMULATION_ID,
            input_path=source,
            output_directory=tmp_path / "output",
            source_sha256=source_sha256,
            gams_system_directory=tmp_path,
            input_schema=LEGACY_V3_INPUT_SCHEMA,
        )
    except ConfigurationError as error:
        assert "not valid for the SPD v16" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("legacy v3 input was accepted for SPD v16")


def test_application_configuration_rejects_implicit_solver_substitution(
    tmp_path,
) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")

    try:
        ApplicationConfiguration(
            formulation_id=FORMULATION,
            input_path=source,
            output_directory=tmp_path / "output",
            source_sha256=(
                "0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8"
            ),
            gams_system_directory=tmp_path,
            solver_profile="some-available-solver",
        )
    except ConfigurationError as error:
        assert "solver_profile" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unsupported solver substitution was accepted")


def test_application_explicitly_selects_optional_clp_validation_profile(
    tmp_path,
) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")
    configuration = ApplicationConfiguration(
        formulation_id=FORMULATION,
        input_path=source,
        output_directory=tmp_path / "output",
        source_sha256=(
            "0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8"
        ),
        gams_system_directory=tmp_path,
        solver_profile=CLP_VALIDATION_SOLVER_PROFILE,
    )

    executor = PyspdApplication().case_executor(configuration)
    assert isinstance(executor, ReserveCaseExecutor)
    assert isinstance(executor.pricing_backend, ClpBackend)
    assert (
        "native-scip-clp"
        in PyspdApplication().daily_configuration(configuration).environment_fingerprint
    )


def test_application_explicitly_selects_cbc_validation_profiles(tmp_path) -> None:
    source = tmp_path / "case.gdx"
    source.write_bytes(b"synthetic-gdx-placeholder")
    for profile, pricing_type in (
        (CBC_HIGHS_VALIDATION_SOLVER_PROFILE, type(None)),
        (CBC_CLP_VALIDATION_SOLVER_PROFILE, ClpBackend),
    ):
        configuration = ApplicationConfiguration(
            formulation_id=FORMULATION,
            input_path=source,
            output_directory=tmp_path / profile,
            source_sha256=(
                "0dd67251795fcbceeac3c5728b868d16f2ecffce6e710acc84fc9bff043cfaf8"
            ),
            gams_system_directory=tmp_path,
            solver_profile=profile,
        )
        executor = PyspdApplication().case_executor(configuration)
        assert isinstance(executor.primary_backend, CbcBackend)
        assert isinstance(executor.pricing_backend, pricing_type)


def test_application_exposes_only_registered_formulations() -> None:
    application = PyspdApplication()
    assert application.formulation_ids == tuple(
        sorted((FORMULATION, SPD16_FORMULATION_ID))
    )
    try:
        application.validate_formulation("date-switched-latest")
    except ConfigurationError as error:
        assert "unknown formulation" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("implicit formulation selection was accepted")


def test_cli_formulations_is_stable_json(capsys) -> None:
    assert main(["formulations", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"formulations": sorted((FORMULATION, SPD16_FORMULATION_ID))}
