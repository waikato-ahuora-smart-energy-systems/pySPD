"""Scalable one-record-per-row canonical artifact feed."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.values import ScalarValue


class CanonicalFeedError(ValueError):
    """A canonical feed is unsupported, corrupt, or semantically inconsistent."""


@dataclass(frozen=True, slots=True)
class CanonicalFeed:
    root: Path
    _manifest: dict[str, Any] = field(repr=False, compare=False)

    @classmethod
    def write(
        cls, symbols: RawSymbols, root: Path, *, compression: str = "zstd"
    ) -> CanonicalFeed:
        items = (
            (cls._symbol_metadata(symbol), cls._symbol_table(symbol))
            for symbol in symbols.symbols
        )
        return cls.write_tables(
            source_name=symbols.source_name,
            source_sha256=symbols.source_sha256,
            items=items,
            root=root,
            compression=compression,
        )

    @classmethod
    def write_tables(
        cls,
        *,
        source_name: str,
        source_sha256: str,
        items: Iterable[tuple[dict[str, Any], pa.Table]],
        root: Path,
        compression: str = "zstd",
    ) -> CanonicalFeed:
        root = root.resolve()
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"canonical feed directory is not empty: {root}")
        symbol_root = root / "symbols"
        symbol_root.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        for ordinal, (metadata, table) in enumerate(items):
            relative = f"symbols/{ordinal:04d}.parquet"
            target = root / relative
            pq.write_table(
                table,
                target,
                compression=compression,
                version="2.6",
                write_statistics=False,
            )
            entry = {
                "ordinal": ordinal,
                **metadata,
                "record_count": table.num_rows,
                "parquet_row_count": table.num_rows,
                "path": relative,
                "physical_sha256": cls._file_sha256(target),
                "logical_sha256": cls._table_sha256(metadata, table),
            }
            entries.append(entry)
        logical_sha256 = cls._feed_sha256(
            source_name, source_sha256, entries
        )
        manifest = {
            "schema_version": 1,
            "format": "pyspd-canonical-feed-v1",
            "source_name": source_name,
            "source_sha256": source_sha256,
            "logical_sha256": logical_sha256,
            "physical_encoding": {
                "library": "pyarrow",
                "version": pa.__version__,
                "compression": compression,
            },
            "symbols": entries,
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return cls(root, manifest)

    @classmethod
    def open(cls, root: Path) -> CanonicalFeed:
        root = root.resolve()
        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CanonicalFeedError(f"invalid feed manifest: {error}") from error
        if manifest.get("schema_version") != 1:
            raise CanonicalFeedError("unsupported feed schema version")
        if manifest.get("format") != "pyspd-canonical-feed-v1":
            raise CanonicalFeedError("unsupported canonical feed format")
        try:
            names = [str(item["name"]) for item in manifest["symbols"]]
            if len(names) != len(set(names)):
                raise CanonicalFeedError("duplicate symbol name in feed manifest")
            for item in manifest["symbols"]:
                artifact = (root / item["path"]).resolve()
                if not artifact.is_relative_to(root):
                    raise CanonicalFeedError(
                        f"artifact path escapes feed root: {item['path']}"
                    )
        except (KeyError, TypeError) as error:
            raise CanonicalFeedError(
                f"invalid feed manifest structure: {error}"
            ) from error
        expected = cls._feed_sha256(
            manifest["source_name"], manifest["source_sha256"], manifest["symbols"]
        )
        if expected != manifest.get("logical_sha256"):
            raise CanonicalFeedError("feed logical SHA-256 does not match")
        return cls(root, manifest)

    @property
    def logical_sha256(self) -> str:
        return str(self._manifest["logical_sha256"])

    @property
    def source_sha256(self) -> str:
        return str(self._manifest["source_sha256"])

    @property
    def symbol_names(self) -> tuple[str, ...]:
        return tuple(item["name"] for item in self._manifest["symbols"])

    @property
    def symbol_record_counts(self) -> dict[str, int]:
        return {
            item["name"]: int(item["record_count"])
            for item in self._manifest["symbols"]
        }

    def read_symbol(self, name: str) -> RawSymbol:
        return self._read_symbol(name, case_id=None)

    def read_case(self, case_id: str) -> RawSymbols:
        return RawSymbols(
            source_name=self._manifest["source_name"],
            source_sha256=self._manifest["source_sha256"],
            symbols=tuple(
                self._read_symbol(item["name"], case_id=case_id)
                for item in self._manifest["symbols"]
            ),
        )

    def read_schema(self) -> RawSymbols:
        """Load only manifest metadata and UEL orders, never Parquet records."""
        return RawSymbols(
            source_name=self._manifest["source_name"],
            source_sha256=self._manifest["source_sha256"],
            symbols=tuple(
                RawSymbol(
                    name=item["name"],
                    symbol_type=SymbolType(item["symbol_type"]),
                    dimension=item["dimension"],
                    domains=tuple(item["domains"]),
                    description=item["description"],
                    uel_orders=tuple(tuple(order) for order in item["uel_orders"]),
                    records=(),
                )
                for item in self._manifest["symbols"]
            ),
        )

    def _read_symbol(self, name: str, case_id: str | None) -> RawSymbol:
        try:
            metadata = next(
                item for item in self._manifest["symbols"] if item["name"] == name
            )
        except StopIteration as error:
            raise KeyError(name) from error
        path = self.root / metadata["path"]
        if self._file_sha256(path) != metadata["physical_sha256"]:
            raise CanonicalFeedError(f"physical SHA-256 mismatch for {name}")
        filters = None
        if (
            case_id is not None
            and metadata["dimension"] > 0
            and metadata["domains"][0] in {"ca", "caseID"}
        ):
            filters = [("key_0", "=", case_id)]
        table = pq.read_table(path, filters=filters)
        records: list[RawRecord] = []
        for row in table.to_pylist():
            keys = tuple(row[f"key_{index}"] for index in range(metadata["dimension"]))
            values: dict[str, ScalarValue] = {}
            for field_name in metadata["value_fields"]:
                kind = row[f"{field_name}__kind"]
                if kind is not None:
                    number = row[f"{field_name}__number"]
                    values[field_name] = ScalarValue.from_wire(
                        kind,
                        number.hex() if number is not None else None,
                        row[f"{field_name}__text"],
                    )
            records.append(RawRecord(keys, values))
        symbol = RawSymbol(
            name=metadata["name"],
            symbol_type=SymbolType(metadata["symbol_type"]),
            dimension=metadata["dimension"],
            domains=tuple(metadata["domains"]),
            description=metadata["description"],
            uel_orders=tuple(tuple(order) for order in metadata["uel_orders"]),
            records=tuple(records),
        )
        logical_metadata = {
            key: metadata[key]
            for key in (
                "name",
                "symbol_type",
                "dimension",
                "domains",
                "description",
                "uel_orders",
                "value_fields",
            )
        }
        if (
            case_id is None
            and self._table_sha256(logical_metadata, table)
            != metadata["logical_sha256"]
        ):
            raise CanonicalFeedError(f"logical SHA-256 mismatch for {name}")
        return symbol

    @staticmethod
    def _value_fields(symbol: RawSymbol) -> list[str]:
        return list(
            dict.fromkeys(
                name for record in symbol.records for name in record.values
            )
        )

    @classmethod
    def _symbol_table(cls, symbol: RawSymbol) -> pa.Table:
        fields = cls._value_fields(symbol)
        columns: dict[str, Any] = {
            "record_ordinal": pa.array(
                range(len(symbol.records)), type=pa.int64()
            )
        }
        for index in range(symbol.dimension):
            columns[f"key_{index}"] = pa.array(
                [record.keys[index] for record in symbol.records], type=pa.string()
            )
        for name in fields:
            values = [record.values.get(name) for record in symbol.records]
            columns[f"{name}__kind"] = [
                value.kind.value if value is not None else None for value in values
            ]
            columns[f"{name}__number"] = [
                value.number if value is not None else None for value in values
            ]
            columns[f"{name}__text"] = [
                value.string if value is not None else None for value in values
            ]
        return pa.Table.from_pydict(columns)

    @classmethod
    def _symbol_metadata(cls, symbol: RawSymbol) -> dict[str, Any]:
        return {
            "name": symbol.name,
            "symbol_type": symbol.symbol_type.value,
            "dimension": symbol.dimension,
            "domains": list(symbol.domains),
            "description": symbol.description,
            "uel_orders": [list(order) for order in symbol.uel_orders],
            "value_fields": cls._value_fields(symbol),
        }

    @staticmethod
    def _table_sha256(metadata: dict[str, Any], table: pa.Table) -> str:
        digest = hashlib.sha256()
        digest.update(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        )
        digest.update(struct.pack(">Q", table.num_rows))
        for name in table.column_names:
            encoded_name = name.encode("utf-8")
            digest.update(struct.pack(">I", len(encoded_name)))
            digest.update(encoded_name)
            column = table.column(name)
            for chunk in column.chunks:
                for value in chunk.to_pylist():
                    if value is None:
                        digest.update(b"N")
                    elif isinstance(value, str):
                        encoded = value.encode("utf-8")
                        digest.update(b"S")
                        digest.update(struct.pack(">Q", len(encoded)))
                        digest.update(encoded)
                    elif isinstance(value, bool):
                        digest.update(b"B1" if value else b"B0")
                    elif isinstance(value, int):
                        digest.update(b"I")
                        digest.update(struct.pack(">q", value))
                    elif isinstance(value, float):
                        digest.update(b"F")
                        digest.update(value.hex().encode("ascii"))
                        digest.update(b"\0")
                    else:
                        raise TypeError(
                            f"unsupported canonical table value for {name}: "
                            f"{type(value).__name__}"
                        )
        return digest.hexdigest()

    @staticmethod
    def _feed_sha256(
        source_name: str, source_sha256: str, entries: list[dict[str, Any]]
    ) -> str:
        payload = {
            "format": "pyspd-canonical-feed-v1",
            "source_name": source_name,
            "source_sha256": source_sha256,
            "symbols": [
                {"name": item["name"], "logical_sha256": item["logical_sha256"]}
                for item in entries
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise CanonicalFeedError(f"cannot read feed artifact {path}: {error}") from error
        return digest.hexdigest()
