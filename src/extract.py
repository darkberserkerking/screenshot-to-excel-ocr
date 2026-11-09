"""Config-driven cleaning and mapping of voted cells into spreadsheet columns."""

import re
import unicodedata
from typing import Any, Dict, List, Sequence, Tuple

from .models import Cell, FieldResult, RowRecord

_EMOJI_RANGES = [
    (0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0xFE00, 0xFE0F),
    (0x1F000, 0x1F2FF), (0x2190, 0x21FF), (0x2B00, 0x2BFF),
]


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def clean_text(text: str, strip_emoji: bool = True,
               normalize_fullwidth: bool = True) -> str:
    """Normalise a raw OCR string into something safe to put in a cell."""
    text = unicodedata.normalize("NFKC", text or "") if normalize_fullwidth else (text or "")
    if strip_emoji:
        text = "".join(ch for ch in text if not _is_emoji(ch))
    text = text.replace("\u00a0", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", text).strip()


def _coerce_int(text: str) -> Any:
    match = re.search(r"-?\d[\d,，.]*", text)
    if not match:
        return None
    raw = match.group(0).replace(",", "").replace("，", "")
    try:
        return int(float(raw))
    except ValueError:
        return None


def _coerce_date(text: str) -> Any:
    match = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", text)
    if not match:
        return None
    y, m, d = (int(g) for g in match.groups())
    return f"{y:04d}-{m:02d}-{d:02d}"


def coerce(text: str, type_: str) -> Any:
    """Convert a cleaned string to the configured type; ``None`` means failure."""
    if type_ == "int":
        return _coerce_int(text)
    if type_ == "float":
        try:
            return float(re.sub(r"[^\d.\-]", "", text))
        except ValueError:
            return None
    if type_ == "date":
        return _coerce_date(text)
    return text or None


def map_row(cells: Sequence[Cell], columns: Sequence[Dict[str, Any]],
            config: Dict[str, Any]) -> RowRecord:
    """Map one voted row onto configured columns.

    A column may carry ``index`` to bind it to a specific cell position;
    without it, cells are consumed left-to-right in column order.
    """
    threshold = float(config.get("low_confidence_threshold", 0.85))
    used = set()
    record = RowRecord()

    for col_index, column in enumerate(columns):
        name = column["name"]
        idx = column.get("index", col_index)
        cell = cells[idx] if isinstance(idx, int) and 0 <= idx < len(cells) else None
        if cell is not None:
            used.add(idx)

        raw = cell.text if cell else ""
        cleaned = clean_text(
            raw,
            bool(config.get("strip_emoji", True)),
            bool(config.get("normalize_fullwidth", True)),
        )
        value = coerce(cleaned, column.get("type", "str")) if cleaned else None
        confidence = cell.confidence if cell else 0.0

        pattern = column.get("pattern") or ""
        pattern_ok = bool(re.search(pattern, cleaned)) if pattern and cleaned else bool(cleaned)
        missing = value is None or value == ""
        required = bool(column.get("required", False))

        flagged = False
        if missing and required:
            flagged = True
        elif not pattern_ok:
            flagged = True
            confidence *= 0.5
        elif confidence < threshold:
            flagged = True

        record.fields[name] = FieldResult(
            value=value if not missing else "",
            confidence=round(confidence, 4),
            raw=raw,
            flagged=flagged,
        )

    # Unmapped cells are preserved as a note instead of being silently dropped.
    extras = [c.text for i, c in enumerate(cells) if i not in used]
    if extras and "备注" in record.fields and not record.fields["备注"].value:
        record.fields["备注"] = FieldResult(" / ".join(extras), 0.6, "", True)

    return record


def extract_rows(table, columns, config) -> List[RowRecord]:
    """Apply :func:`map_row` to every voted row."""
    return [map_row(cells, columns, config) for cells in table]
