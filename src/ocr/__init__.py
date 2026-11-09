"""OCR backend registry: built-ins and user plugins share one entry point."""

from .base import BaseOCREngine, parse_raw
from .registry import (BUILTIN, available_engines, discover, engine_names,
                       get_engine)

__all__ = [
    "BaseOCREngine", "parse_raw", "get_engine", "available_engines",
    "engine_names", "discover", "BUILTIN",
]
