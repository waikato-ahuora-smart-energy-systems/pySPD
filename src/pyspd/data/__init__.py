"""Faithful raw-symbol and GAMS-free canonical data contracts."""

from pyspd.data.canonical import CanonicalArchive, CanonicalIntegrityError
from pyspd.data.catalog import SymbolCatalog, SymbolCatalogError, SymbolSpec
from pyspd.data.feed import CanonicalFeed, CanonicalFeedError
from pyspd.data.gdx import GdxAdapter
from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.validation import (
    InputValidationError,
    V5InputValidator,
    ValidationIssue,
    ValidationReport,
)
from pyspd.data.values import ScalarValue, ValueKind

__all__ = [
    "CanonicalArchive",
    "CanonicalFeed",
    "CanonicalFeedError",
    "CanonicalIntegrityError",
    "GdxAdapter",
    "InputValidationError",
    "RawRecord",
    "RawSymbol",
    "RawSymbols",
    "ScalarValue",
    "SymbolCatalog",
    "SymbolCatalogError",
    "SymbolSpec",
    "SymbolType",
    "V5InputValidator",
    "ValidationIssue",
    "ValidationReport",
    "ValueKind",
]
