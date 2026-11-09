"""Spreadsheet writer.

Low-confidence cells are highlighted instead of being silently guessed at,
and the original OCR text is attached as a cell comment so a human reviewer
can spot-check the result quickly.
"""

import os
from typing import Any, Dict, Sequence

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import RowRecord

HEADER_FILL = PatternFill("solid", fgColor="E8EEF7")
REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")


def _default_width(name: str) -> float:
    return min(36.0, max(12.0, len(name) * 2.4 + 8))


def write_report(records: Sequence[RowRecord], columns: Sequence[Dict[str, Any]],
                 output_path: str, meta: Any = None) -> str:
    """Write records to ``output_path`` and return the path."""
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "数据"

    # Header
    for col_index, column in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_index, value=column.get("name", f"列{col_index}"))
        cell.font = Font(bold=True, size=11)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        width = column.get("width") or _default_width(str(cell.value))
        ws.column_dimensions[get_column_letter(col_index)].width = width
    ws.row_dimensions[1].height = 22

    # Data
    for row_index, record in enumerate(records, 2):
        for col_index, column in enumerate(columns, 1):
            name = column.get("name", f"列{col_index}")
            result = record.fields.get(name)
            value = result.value if result else ""
            cell = ws.cell(row=row_index, column=col_index, value=value)
            if result and result.flagged:
                cell.fill = REVIEW_FILL
                if result.raw and result.raw != str(value):
                    cell.comment = Comment(f"OCR 原文: {result.raw}", "pipeline")
            if column.get("type") == "int":
                cell.alignment = Alignment(horizontal="right")

    last_col = get_column_letter(max(1, len(columns)))
    last_row = max(2, len(records) + 1)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{last_col}{last_row}"

    # Run metadata / review notes
    info = wb.create_sheet("运行说明")
    info.append(["项目", "值"])
    info["A1"].font = Font(bold=True)
    info["B1"].font = Font(bold=True)
    for key, value in (meta or {}).items():
        info.append([str(key), str(value)])
    info.append(["说明", "黄色底色 = 置信度低或字段校验未通过，建议人工复核"])
    info.append(["说明", "鼠标悬停在单元格上可查看 OCR 原文"])
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 72
    info.freeze_panes = "A2"

    wb.save(output_path)
    return output_path
