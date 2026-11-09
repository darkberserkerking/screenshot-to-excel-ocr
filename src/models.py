"""Small, dependency-free data containers shared by every stage."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class OCRItem:
    """One text box returned by an OCR backend.

    ``box`` accepts either 4 corner points or a flat ``(x1, y1, x2, y2)``
    rectangle. ``scale`` records which resized copy of the image produced it,
    so coordinates from different scales can be normalised back to the
    original image before clustering.
    """

    text: str
    box: List[Tuple[float, float]]
    score: float = 1.0
    scale: float = 1.0

    @property
    def center(self) -> Tuple[float, float]:
        xs = [p[0] for p in self.box]
        ys = [p[1] for p in self.box]
        return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    @property
    def width(self) -> float:
        xs = [p[0] for p in self.box]
        return max(xs) - min(xs)

    @property
    def height(self) -> float:
        ys = [p[1] for p in self.box]
        return max(ys) - min(ys)

    def normalized(self) -> "OCRItem":
        """Return a copy whose coordinates are back in original-image space."""
        if self.scale == 1.0:
            return self
        box = [(x / self.scale, y / self.scale) for x, y in self.box]
        return OCRItem(self.text, box, self.score, 1.0)


@dataclass
class Cell:
    """A voted cell: the winning text plus how trustworthy it is."""

    text: str
    votes: int = 1
    confidence: float = 1.0
    x: float = 0.0


@dataclass
class FieldResult:
    """One cleaned field ready to be written into a spreadsheet cell."""

    value: Any = ""
    confidence: float = 1.0
    raw: str = ""
    flagged: bool = False


@dataclass
class RowRecord:
    """One output row, keyed by configured column name."""

    fields: Dict[str, FieldResult] = field(default_factory=dict)
    source: str = ""

    @property
    def flagged(self) -> bool:
        return any(f.flagged for f in self.fields.values())
