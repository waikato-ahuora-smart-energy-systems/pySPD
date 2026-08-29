from __future__ import annotations

import json

from pyspd.application import (
    ApplicationConfiguration,
    ConfigurationError,
    PyspdApplication,
)
from pyspd.cli import main
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
    assert payload == {
        "formulations": sorted((FORMULATION, SPD16_FORMULATION_ID))
    }
