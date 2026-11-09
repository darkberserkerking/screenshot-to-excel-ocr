"""OCR backend registry. Backends are imported lazily so that the core
pipeline stays usable with zero optional dependencies.
"""

from typing import Any

from .base import BaseOCREngine, parse_raw


def get_engine(name: str, **kwargs: Any) -> BaseOCREngine:
    name = (name or "dummy").lower().strip()
    if name == "dummy":
        from .dummy import DummyEngine
        return DummyEngine(**kwargs)
    if name == "rapidocr":
        from .rapidocr import RapidOCREngine
        return RapidOCREngine(**kwargs)
    if name == "maaocr":
        from .maaocr import MaaOCREngine
        return MaaOCREngine(**kwargs)
    raise ValueError(f"unknown OCR backend: {name!r} (expected dummy/rapidocr/maaocr)")


__all__ = ["get_engine", "BaseOCREngine", "parse_raw"]
