"""Canonical Arrow/Parquet archive boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.values import ScalarValue


class CanonicalIntegrityError(ValueError):
    """A canonical archive failed its fail-closed integrity checks."""


@dataclass(frozen=True, slots=True)
class CanonicalArchive:
    root: Path

    @property
    def records_path(self) -> Path:
        return self.root / "records.parquet"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @classmethod
    def write(cls, symbols: RawSymbols, root: Path) -> CanonicalArchive:
        root = root.resolve()
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"canonical archive directory is not empty: {root}")
        root.mkdir(parents=True, exist_ok=True)
        archive = cls(root)

        rows: dict[str, list[Any]] = {
            "symbol_ordinal": [],
            "record_ordinal": [],
            "cell_ordinal": [],
            "cell_role": [],
            "cell_name": [],
            "value_kind": [],
            "number_hex": [],
            "text_value": [],
        }
        for symbol_ordinal, symbol in enumerate(symbols.symbols):
            for record_ordinal, record in enumerate(symbol.records):
                for cell_ordinal, (domain, key) in enumerate(
                    zip(symbol.domains, record.keys, strict=True)
                ):
                    cls._append_cell(
                        rows,
                        symbol_ordinal,
                        record_ordinal,
                        cell_ordinal,
                        "key",
                        domain,
                        ScalarValue.text(key),
                    )
                for value_ordinal, (name, value) in enumerate(record.values.items()):
                    cls._append_cell(
                        rows,
                        symbol_ordinal,
                        record_ordinal,
                        value_ordinal,
                        "value",
                        name,
                        value,
                    )

        schema = pa.schema(
            [
                ("symbol_ordinal", pa.int32()),
                ("record_ordinal", pa.int64()),
                ("cell_ordinal", pa.int32()),
                ("cell_role", pa.string()),
                ("cell_name", pa.string()),
                ("value_kind", pa.string()),
                ("number_hex", pa.string()),
                ("text_value", pa.string()),
            ]
        )
        table = pa.Table.from_pydict(rows, schema=schema)
        pq.write_table(
            table,
            archive.records_path,
            compression="zstd",
            version="2.6",
            write_statistics=False,
        )
        records_sha256 = cls._file_sha256(archive.records_path)
        manifest = {
            "schema_version": 1,
            "format": "pyspd-canonical-arrow-long-v1",
            "source_name": symbols.source_name,
            "source_sha256": symbols.source_sha256,
            "logical_sha256": symbols.logical_sha256,
            "records_sha256": records_sha256,
            "writer": {"library": "pyarrow", "version": pa.__version__},
            "symbols": [
                {
                    "name": symbol.name,
                    "symbol_type": symbol.symbol_type.value,
                    "dimension": symbol.dimension,
                    "domains": list(symbol.domains),
                    "description": symbol.description,
                    "uel_orders": [list(order) for order in symbol.uel_orders],
                    "record_count": len(symbol.records),
                }
                for symbol in symbols.symbols
            ],
        }
        archive.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return archive

    @classmethod
    def read(cls, root: Path) -> RawSymbols:
        archive = cls(root.resolve())
        try:
            manifest: dict[str, Any] = json.loads(
                archive.manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise CanonicalIntegrityError(f"invalid canonical manifest: {error}") from error
        if manifest.get("schema_version") != 1:
            raise CanonicalIntegrityError("unsupported canonical schema version")
        actual_physical = cls._file_sha256(archive.records_path)
        if actual_physical != manifest.get("records_sha256"):
            raise CanonicalIntegrityError("records physical SHA-256 does not match")

        table = pq.read_table(archive.records_path)
        rows = table.to_pylist()
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(
                (row["symbol_ordinal"], row["record_ordinal"]), []
            ).append(row)

        symbols: list[RawSymbol] = []
        for symbol_ordinal, metadata in enumerate(manifest["symbols"]):
            records: list[RawRecord] = []
            for record_ordinal in range(metadata["record_count"]):
                cells = grouped.get((symbol_ordinal, record_ordinal), [])
                keys = tuple(
                    cell["text_value"]
                    for cell in sorted(
                        (cell for cell in cells if cell["cell_role"] == "key"),
                        key=lambda cell: cell["cell_ordinal"],
                    )
                )
                values = {
                    cell["cell_name"]: ScalarValue.from_wire(
                        cell["value_kind"], cell["number_hex"], cell["text_value"]
                    )
                    for cell in sorted(
                        (cell for cell in cells if cell["cell_role"] == "value"),
                        key=lambda cell: cell["cell_ordinal"],
                    )
                }
                records.append(RawRecord(keys, values))
            symbols.append(
                RawSymbol(
                    name=metadata["name"],
                    symbol_type=SymbolType(metadata["symbol_type"]),
                    dimension=metadata["dimension"],
                    domains=tuple(metadata["domains"]),
                    description=metadata["description"],
                    uel_orders=tuple(
                        tuple(order) for order in metadata["uel_orders"]
                    ),
                    records=tuple(records),
                )
            )
        restored = RawSymbols(
            source_name=manifest["source_name"],
            source_sha256=manifest["source_sha256"],
            symbols=tuple(symbols),
        )
        if restored.logical_sha256 != manifest.get("logical_sha256"):
            raise CanonicalIntegrityError("logical SHA-256 does not match")
        return restored

    @staticmethod
    def _append_cell(
        rows: dict[str, list[Any]],
        symbol_ordinal: int,
        record_ordinal: int,
        cell_ordinal: int,
        role: str,
        name: str,
        value: ScalarValue,
    ) -> None:
        wire = value.to_wire()
        rows["symbol_ordinal"].append(symbol_ordinal)
        rows["record_ordinal"].append(record_ordinal)
        rows["cell_ordinal"].append(cell_ordinal)
        rows["cell_role"].append(role)
        rows["cell_name"].append(name)
        rows["value_kind"].append(value.kind.value)
        rows["number_hex"].append(wire["number_hex"])
        rows["text_value"].append(wire["text"])

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise CanonicalIntegrityError(f"cannot read canonical records: {error}") from error
        return digest.hexdigest()
