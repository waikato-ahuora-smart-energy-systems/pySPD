"""Probity tests for targeted solver-record replacement."""

from __future__ import annotations

import io
import json

from tools.replace_solver_path_records import _replace_lines


def test_replacement_preserves_order_and_requires_exact_case_identity() -> None:
    source = io.StringIO(
        "\n".join(
            json.dumps({"case_id": case_id, "value": value})
            for case_id, value in (("A", 1), ("B", 2), ("C", 3))
        )
        + "\n"
    )
    target = io.StringIO()
    used: set[str] = set()
    observed: list[dict[str, object]] = []

    _replace_lines(
        source,
        target,
        {"B": {"case_id": "B", "value": 20}},
        used,
        accumulator=observed.append,
    )

    assert used == {"B"}
    assert [json.loads(line) for line in target.getvalue().splitlines()] == [
        {"case_id": "A", "value": 1},
        {"case_id": "B", "value": 20},
        {"case_id": "C", "value": 3},
    ]
    assert observed[1]["value"] == 20
