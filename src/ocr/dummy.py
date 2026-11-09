"""Deterministic backend used by ``--demo`` and the test suite.

It needs no model files, no network and no third-party OCR package, so the
whole pipeline can be verified on a fresh clone. Coordinates are multiplied by
``scale`` on purpose: a real backend reports boxes in the resized image, and
this lets the normalisation/voting code be exercised honestly.
"""

from typing import Any, List

from ..models import OCRItem
from .base import BaseOCREngine

DEMO_ROWS = [
    ["A-1024", "办公用品批次", "128", "2026-11-03", "已复核"],
    ["B-2078", "设备登记表", "56", "2026-11-04", ""],
    ["C-3310", "月度汇总", "1024", "2026/11/05", "待确认"],
]


class DummyEngine(BaseOCREngine):
    name = "dummy"

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else DEMO_ROWS

    def recognize(self, image: Any, scale: float = 1.0) -> List[OCRItem]:
        items: List[OCRItem] = []
        for row_index, row in enumerate(self.rows):
            for col_index, text in enumerate(row):
                if not text:
                    continue
                # Simulate one recognition slip on the 2x pass only, so the
                # majority vote across 1x/2x/3x still recovers the right text.
                if scale == 2.0 and row_index == 1 and col_index == 1:
                    text = "设备登记未"
                x1 = (30 + col_index * 170) * scale
                y1 = (30 + row_index * 44) * scale
                x2 = (30 + col_index * 170 + 130) * scale
                y2 = (30 + row_index * 44 + 26) * scale
                box = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                items.append(OCRItem(text, box, 0.95, scale))
        return items
