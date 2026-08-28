"""Faithful raw-symbol and GAMS-free canonical data contracts."""

from pyspd.data.canonical import CanonicalArchive, CanonicalIntegrityError
from pyspd.data.catalog import SymbolCatalog, SymbolCatalogError, SymbolSpec
from pyspd.data.gdx import GdxAdapter
from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.values import ScalarValue, ValueKind

__all__ = [
    "CanonicalArchive",
    "CanonicalIntegrityError",
    "GdxAdapter",
    "RawRecord",
    "RawSymbol",
    "RawSymbols",
    "ScalarValue",
    "SymbolCatalog",
    "SymbolCatalogError",
    "SymbolSpec",
    "SymbolType",
    "ValueKind",
]
