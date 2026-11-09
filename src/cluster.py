"""Turn multi-scale OCR boxes into a voted table.

Pipeline:
  1. normalise coordinates back to original-image space (divide by scale)
  2. sort by vertical centre - OCR backends often emit boxes bottom-up
  3. cluster boxes into rows by y, then into cells by x
  4. vote inside each cell: more occurrences across scales wins, then mean score
"""

from statistics import median
from typing import Dict, List, Sequence, Tuple

from .models import Cell, OCRItem

Table = List[List[Cell]]


def _center(item: OCRItem, axis: str) -> float:
    cx, cy = item.center
    return cy if axis == "y" else cx


def _cluster(items: Sequence[OCRItem], axis: str, tolerance: float) -> List[List[OCRItem]]:
    """Greedy 1-D clustering against the running mean of each group."""
    if not items:
        return []
    ordered = sorted(items, key=lambda it: _center(it, axis))
    groups: List[List[OCRItem]] = [[ordered[0]]]
    for item in ordered[1:]:
        group = groups[-1]
        mean = sum(_center(g, axis) for g in group) / len(group)
        if abs(_center(item, axis) - mean) <= tolerance:
            group.append(item)
        else:
            groups.append([item])
    return groups


def _gaps(items: Sequence[OCRItem], axis: str) -> List[float]:
    centers = sorted(_center(it, axis) for it in items)
    return [b - a for a, b in zip(centers, centers[1:]) if b - a > 1.0]


def estimate_row_tolerance(items: Sequence[OCRItem], ratio: float = 0.7,
                           fallback: float = 20.0) -> float:
    """Estimate row spacing from the median vertical gap between boxes."""
    gaps = _gaps(items, "y")
    if len(gaps) < 2:
        return fallback
    return max(6.0, median(gaps) * ratio)


def estimate_col_tolerance(row: Sequence[OCRItem], ratio: float = 0.9,
                           fallback: float = 18.0) -> float:
    """Estimate cell spacing from the median box width in one row."""
    widths = [it.width for it in row if it.width > 1.0]
    if len(widths) < 2:
        return fallback
    return max(8.0, median(widths) * ratio)


def _vote_cell(items: Sequence[OCRItem]) -> Cell:
    """Pick the text seen most often across scales; break ties by mean score."""
    buckets: Dict[str, Dict[str, float]] = {}
    for item in items:
        text = item.text.strip()
        if not text:
            continue
        entry = buckets.setdefault(text, {"votes": 0.0, "score": 0.0})
        entry["votes"] += 1
        entry["score"] += item.score
    if not buckets:
        return Cell("", 0, 0.0)
    best = max(
        buckets.items(),
        key=lambda kv: (kv[1]["votes"], kv[1]["score"] / kv[1]["votes"]),
    )
    text, stat = best
    votes = int(stat["votes"])
    mean_score = stat["score"] / stat["votes"]
    total = sum(int(entry["votes"]) for entry in buckets.values())
    # Agreement ratio: how much of this cell's evidence supports the winner.
    confidence = mean_score * (votes / total if total else 0.0)
    return Cell(text, votes, round(confidence, 4),
                round(sum(it.center[0] for it in items) / len(items), 2))


def build_table(items: Sequence[OCRItem], row_tolerance_ratio: float = 0.7,
                col_tolerance_ratio: float = 0.9) -> Tuple[Table, Dict[str, float]]:
    """Build ``[[Cell, ...], ...]`` and return it with a few debug statistics."""
    normalized = [it.normalized() for it in items if it.text.strip()]
    row_tol = estimate_row_tolerance(normalized, row_tolerance_ratio)
    rows = _cluster(normalized, "y", row_tol)

    table: Table = []
    for row in rows:
        col_tol = estimate_col_tolerance(row, col_tolerance_ratio)
        cells = [_vote_cell(group) for group in _cluster(row, "x", col_tol)]
        cells = [c for c in cells if c.text]
        if cells:
            table.append(sorted(cells, key=lambda c: c.x))

    stats = {
        "input_boxes": float(len(items)),
        "rows": float(len(table)),
        "row_tolerance": round(row_tol, 2),
    }
    return table, stats
