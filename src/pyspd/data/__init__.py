"""Faithful raw-symbol and GAMS-free canonical data contracts."""

from pyspd.data.canonical import CanonicalArchive, CanonicalIntegrityError
from pyspd.data.catalog import SymbolCatalog, SymbolCatalogError, SymbolSpec
from pyspd.data.feed import CanonicalFeed, CanonicalFeedError
from pyspd.data.gdx import GdxAdapter
from pyspd.data.legacy import (
    LEGACY_V3_INPUT_SCHEMA,
    SUPPORTED_INPUT_SCHEMAS,
    V5_INPUT_SCHEMA,
    LegacyV3InputAdapter,
)
from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.validation import (
    InputValidationError,
    V5InputValidator,
    ValidationIssue,
    ValidationReport,
)
from pyspd.data.values import ScalarValue, ValueKind

__all__ = [
    "LEGACY_V3_INPUT_SCHEMA",
    "SUPPORTED_INPUT_SCHEMAS",
    "V5_INPUT_SCHEMA",
    "CanonicalArchive",
    "CanonicalFeed",
    "CanonicalFeedError",
    "CanonicalIntegrityError",
    "GdxAdapter",
    "InputValidationError",
    "LegacyV3InputAdapter",
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
