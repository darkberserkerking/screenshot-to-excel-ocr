"""Optional backend: RapidOCR (ONNX Runtime), installable with plain pip."""

from typing import Any, List

from ..models import OCRItem
from .base import BaseOCREngine, parse_raw


class RapidOCREngine(BaseOCREngine):
    name = "rapidocr"

    def __init__(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "rapidocr backend requires: pip install -r requirements.txt"
            ) from exc
        self._engine = RapidOCR()

    def recognize(self, image: Any, scale: float = 1.0) -> List[OCRItem]:
        import numpy as np

        array = np.asarray(image.convert("RGB"))
        result = self._engine(array)
        # Different releases return either ``result`` or ``(result, elapsed)``.
        raw = result[0] if isinstance(result, tuple) else result
        return parse_raw(raw, scale)


__all__ = ["RapidOCREngine"]
