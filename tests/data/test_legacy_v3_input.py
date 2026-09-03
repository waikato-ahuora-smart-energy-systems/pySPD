from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.data import LEGACY_V3_INPUT_SCHEMA, GdxAdapter, LegacyV3InputAdapter
from pyspd.data.catalog import SymbolCatalog
from pyspd.reserve import RESERVE_FORMULATION_ID

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures/cplex_reference/2019/20190622/input/FP_20190622_F.gdx"
)
SOURCE_SHA256 = "62cb85144a54ef87b48bac34281030a918fab174e2ccad06f341bf0b4b65b448"


@pytest.mark.oracle
def test_legacy_v3_fixture_normalizes_and_prepares_48_cases(tmp_path: Path) -> None:
    system_text = os.environ.get("GAMS_SYSTEM_DIRECTORY")
    if not system_text:
        pytest.skip("GAMS_SYSTEM_DIRECTORY is required")
    system = Path(system_text)

    source = GdxAdapter.read(FIXTURE, system_directory=system)
    normalized = LegacyV3InputAdapter().normalize(source)
    SymbolCatalog.vspd_v5().validate(normalized)
    assert len(normalized["i_caseDefn"].records) == 48

    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=FIXTURE,
        output_directory=tmp_path / "unused",
        source_sha256=SOURCE_SHA256,
        gams_system_directory=system,
        input_schema=LEGACY_V3_INPUT_SCHEMA,
    )
    prepared = tuple(PyspdApplication().iter_prepared_cases(configuration))
    assert len(prepared) == 48
    assert prepared[0].specification.date_time == "22-JUN-2019 00:00"
    assert prepared[0].specification.schedule_type.value == "SPD"
    assert prepared[0].specification.study_mode == 111
    assert prepared[-1].specification.date_time == "22-JUN-2019 23:30"
