"""Backend-independent OCR interface and result normalisation."""

from typing import Any, List, Sequence, Tuple

from ..models import OCRItem


class BaseOCREngine:
    """Every backend returns ``List[OCRItem]`` in the coordinate space of the
    image it was given. ``scale`` is passed by the pipeline so a backend can
    (optionally) adapt its behaviour for a resized copy.
    """

    name = "base"

    def recognize(self, image: Any, scale: float = 1.0) -> List[OCRItem]:
        raise NotImplementedError


def _to_points(box: Any) -> List[Tuple[float, float]]:
    """Accept ``[[x,y], ...]`` or a flat ``(x1, y1, x2, y2)`` rectangle."""
    if isinstance(box, (list, tuple)) and len(box) == 4 \
            and all(isinstance(v, (int, float)) for v in box):
        x1, y1, x2, y2 = box
        return [(float(x1), float(y1)), (float(x2), float(y1)),
                (float(x2), float(y2)), (float(x1), float(y2))]
    points: List[Tuple[float, float]] = []
    try:
        for point in box:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
    except TypeError:
        return []
    return points if len(points) >= 2 else []


def parse_raw(raw: Any, scale: float = 1.0) -> List[OCRItem]:
    """Normalise the common result shapes into ``OCRItem`` objects.

    Supported shapes::

        (text, box, score)      # detection + recognition engines
        (box, text, score)      # some ONNX-based engines
        {"text": ..., "box": ..., "score": ...}
    """
    items: List[OCRItem] = []
    for entry in raw or []:
        text: Any = None
        box: Any = None
        score = 1.0

        if isinstance(entry, dict):
            text = entry.get("text") or entry.get("label")
            box = entry.get("box") or entry.get("points") or entry.get("bbox")
            try:
                score = float(entry.get("score", entry.get("confidence", 1.0)))
            except (TypeError, ValueError):
                score = 1.0
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            first, second = entry[0], entry[1]
            if isinstance(first, str) and not isinstance(second, str):
                text, box = first, second
            elif isinstance(second, str) and not isinstance(first, str):
                box, text = first, second
            if len(entry) >= 3:
                try:
                    score = float(entry[2])
                except (TypeError, ValueError):
                    score = 1.0

        if not text or box is None:
            continue
        points = _to_points(box)
        if not points:
            continue
        items.append(OCRItem(str(text).strip(), points, score, scale))
    return items


__all__ = ["BaseOCREngine", "parse_raw"]
