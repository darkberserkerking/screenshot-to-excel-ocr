"""Optional adapter for a user-provided MaaOCR-style module.

Nothing about the host project is hard-coded here. Point the two environment
variables at your own checkout and model directory::

    OCR_MODULE_DIR=/path/to/dir/containing/maa_ocr.py
    OCR_MODEL_DIR=/path/to/ocr/model

The module must expose ``MaaOCR(model_dir=...)`` with a ``recognize(image)``
method returning ``(text, box, score)`` tuples. Images are passed as
``PIL.Image`` objects, never as path strings.
"""

import os
import sys
from typing import Any, List

from ..models import OCRItem
from .base import BaseOCREngine, parse_raw


class MaaOCREngine(BaseOCREngine):
    name = "maaocr"

    def __init__(self):
        module_dir = os.environ.get("OCR_MODULE_DIR")
        model_dir = os.environ.get("OCR_MODEL_DIR")
        if not module_dir:
            raise RuntimeError(
                "maaocr backend requires OCR_MODULE_DIR (directory containing "
                "maa_ocr.py) and optionally OCR_MODEL_DIR"
            )
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        try:
            from maa_ocr import MaaOCR  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                f"cannot import maa_ocr from OCR_MODULE_DIR={module_dir!r}"
            ) from exc
        self._engine = MaaOCR(model_dir=model_dir) if model_dir else MaaOCR()

    def recognize(self, image: Any, scale: float = 1.0) -> List[OCRItem]:
        return parse_raw(self._engine.recognize(image), scale)


__all__ = ["MaaOCREngine"]
