"""Adapter for a user-provided MaaOCR-style module, with auto-discovery.

Resolution order (first match wins):

1. ``OCR_MODULE_DIR`` / ``OCR_MODEL_DIR`` environment variables
2. Paths entered in the GUI (applied in-process before the engine starts)
3. ``<app_dir>/engines/maaocr/`` laid out as::

       engines/maaocr/maa_ocr.py
       engines/maaocr/model/ocr/{det.onnx,rec.onnx,keys.txt}

4. ``<module_dir>/model/ocr/`` if a module directory was given

No third-party source or model weights are shipped with this repository.
The module must expose ``MaaOCR(model_dir=...)`` with ``recognize(image)``
returning ``(text, box, score)`` tuples; a ``PIL.Image`` is passed in.
"""

import os
import sys
from typing import Any, List, Tuple

from ..models import OCRItem
from .base import BaseOCREngine, parse_raw


def _resolve(app_dir: str) -> Tuple[str, str]:
    module_dir = os.environ.get("OCR_MODULE_DIR", "").strip()
    model_dir = os.environ.get("OCR_MODEL_DIR", "").strip()
    auto = os.path.join(app_dir, "engines", "maaocr")

    if not module_dir and os.path.isfile(os.path.join(auto, "maa_ocr.py")):
        module_dir = auto
    if not model_dir:
        candidates = [os.path.join(auto, "model", "ocr")]
        if module_dir:
            candidates.append(os.path.join(module_dir, "model", "ocr"))
        for candidate in candidates:
            if os.path.isfile(os.path.join(candidate, "det.onnx")):
                model_dir = candidate
                break
    return module_dir, model_dir


class MaaOCREngine(BaseOCREngine):
    name = "maaocr"

    def __init__(self, app_dir: Any = None):
        from ..config_io import APP_DIR
        self.module_dir, self.model_dir = _resolve(app_dir or APP_DIR)
        if not self.module_dir:
            raise RuntimeError(
                "未找到该 OCR 模块：请在界面填写模块目录，或把 maa_ocr.py 与 "
                "model/ocr/ 放到程序目录的 engines/maaocr/ 下")
        if self.module_dir not in sys.path:
            sys.path.insert(0, self.module_dir)
        try:
            from maa_ocr import MaaOCR  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                f"无法从 {self.module_dir} 导入 maa_ocr") from exc
        self._engine = (MaaOCR(model_dir=self.model_dir) if self.model_dir
                        else MaaOCR())

    def recognize(self, image: Any, scale: float = 1.0) -> List[OCRItem]:
        return parse_raw(self._engine.recognize(image), scale)


__all__ = ["MaaOCREngine"]
