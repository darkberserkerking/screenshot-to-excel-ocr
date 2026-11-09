"""Text-list export for screenshots that are not tables.

Instead of clustering boxes into columns, this mode reports every recognised
text box with its source file, confidence and centre coordinate in the original
image. That is what UI automation needs to locate elements on screen.

Output columns: source file / index / text / confidence / centre X / centre Y /
scale. Boxes seen at several scales are collapsed to one row by spatial
distance, keeping the highest-scoring occurrence.
"""

import math
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .ocr import get_engine
from .pipeline import RunStats
from .preprocess import iter_images, load_image, multiscale

HEADERS = ("来源文件", "序号", "识别文本", "置信度", "中心X", "中心Y", "尺度")
HEADER_FILL = PatternFill("solid", fgColor="E8EEF7")
REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")

# Boxes of the same text recognised at 1x/2x/3x drift by a few pixels even
# after coordinate normalisation. The configured grid is a base unit; the real
# merge radius is this multiple of it, so boundary cases (e.g. 647.0 vs 641.5
# with grid=12) are still merged.
MERGE_RADIUS_FACTOR = 1.5

Item = Tuple[str, Any, float]          # (source filename, normalised OCRItem, scale)
Row = Tuple[str, str, float, float, float, float]  # (source, text, score, cx, cy, scale)


def collect_items(folder: str, engine_name: str = "dummy",
                  scales: Optional[Sequence[float]] = None,
                  min_score: float = 0.5) -> Tuple[List[Item], int, str]:
    """Run OCR over every image at every scale; return normalised boxes."""
    engine = get_engine(engine_name)
    collected: List[Item] = []
    file_count = 0
    for path in iter_images(folder):
        image = load_image(path)
        file_count += 1
        for scale, scaled in multiscale(image, list(scales or [1, 2, 3])):
            for item in engine.recognize(scaled, scale=scale):
                if item.score >= min_score and item.text.strip():
                    collected.append((os.path.basename(path), item.normalized(), scale))
    return collected, file_count, engine.name


def deduplicate(items: Sequence[Item], grid: float = 12.0) -> List[Row]:
    """Collapse multi-scale duplicates by distance, then sort by file / y / x.

    Grouping by ``round(cx / grid)`` buckets used to miss duplicates whenever
    two centres landed on opposite sides of a bucket boundary, even 0.3px
    apart. Here boxes are grouped by ``(source, text)``, processed from the
    highest score down, and any box whose centre is within the merge radius of
    an already kept box is dropped. Genuine repeated labels further apart are
    preserved.
    """
    radius = max(1.0, float(grid)) * MERGE_RADIUS_FACTOR
    groups: Dict[Tuple[str, str], List[Tuple[Any, float]]] = defaultdict(list)
    for source, item, scale in items:
        item = item.normalized()
        groups[(source, item.text)].append((item, scale))

    rows: List[Row] = []
    for (source, text), group in groups.items():
        group.sort(key=lambda pair: pair[0].score, reverse=True)
        kept: List[Tuple[float, float]] = []
        for item, scale in group:
            cx, cy = item.center
            if any(math.hypot(cx - kx, cy - ky) <= radius
                   for kx, ky in kept):
                continue
            kept.append((cx, cy))
            rows.append((source, text, item.score,
                         round(cx, 1), round(cy, 1), scale))
    rows.sort(key=lambda r: (r[0], r[4], r[3]))
    return rows


def write_dump(rows: Sequence[Row], output_path: str, threshold: float = 0.85,
               meta: Optional[Dict[str, Any]] = None) -> str:
    """Write the text list workbook and return its path."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "文本清单"

    for index, header in enumerate(HEADERS, 1):
        cell = ws.cell(1, index, header)
        cell.font = Font(bold=True, size=11)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 22

    for index, (source, text, score, cx, cy, scale) in enumerate(rows, 1):
        ws.append([source, index, text, round(score, 4), cx, cy, scale])
        if score < threshold:
            ws.cell(index + 1, 4).fill = REVIEW_FILL

    for column, width in zip("ABCDEFG", (42, 8, 46, 12, 12, 12, 8)):
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{max(2, len(rows) + 1)}"

    info = wb.create_sheet("运行说明")
    info.append(["项目", "值"])
    info["A1"].font = Font(bold=True)
    info["B1"].font = Font(bold=True)
    for key, value in (meta or {}).items():
        info.append([str(key), str(value)])
    info.append(["说明", "坐标已归一化回原图尺寸，为文本框中心点"])
    info.append(["说明", "黄色置信度 = 低于阈值，建议人工复核"])
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 72
    info.freeze_panes = "A2"

    wb.save(output_path)
    return output_path


def run_text_dump(input_dir: str, output_path: str, config: Dict[str, Any],
                  engine_name: Optional[str] = None,
                  scales: Optional[Sequence[float]] = None,
                  dedup_grid: Optional[float] = None) -> RunStats:
    """End-to-end text-list export, returning the same stats object as ``run``."""
    ocr = config.get("ocr") or {}
    name = engine_name or ocr.get("engine", "dummy")
    chosen_scales = list(scales or ocr.get("scales") or [1, 2, 3])
    min_score = float(ocr.get("min_score", 0.5))
    grid = float(dedup_grid if dedup_grid is not None
                 else (config.get("dump") or {}).get("dedup_grid", 12))
    threshold = float(config.get("low_confidence_threshold", 0.85))

    items, file_count, engine_label = collect_items(
        input_dir, name, chosen_scales, min_score)
    if file_count == 0:
        raise FileNotFoundError(f"no supported images found in: {input_dir}")

    rows = deduplicate(items, grid)
    stats = RunStats(
        files=file_count,
        rows=len(rows),
        flagged_rows=sum(1 for r in rows if r[2] < threshold),
        boxes=len(items),
        engine=engine_label,
        scales=",".join(str(s) for s in chosen_scales),
    )
    meta = {
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "输出模式": "文本清单（文字 + 坐标）",
        "OCR 引擎": stats.engine,
        "扫描尺度": stats.scales,
        "输入文件数": stats.files,
        "识别文本框数": stats.boxes,
        "去重后条目": stats.rows,
        "低置信条目": stats.flagged_rows,
        "去重网格(px)": grid,
        "实际合并半径(px)": round(grid * MERGE_RADIUS_FACTOR, 1),
    }
    write_dump(rows, output_path, threshold, meta)
    return stats
