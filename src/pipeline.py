"""Orchestration: images -> multi-scale OCR -> voted table -> Excel report."""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image

from .cluster import build_table
from .excel import write_report
from .extract import extract_rows
from .models import OCRItem, RowRecord
from .ocr import get_engine
from .preprocess import iter_images, load_image, multiscale


@dataclass
class RunStats:
    files: int = 0
    rows: int = 0
    flagged_rows: int = 0
    boxes: int = 0
    engine: str = "dummy"
    scales: str = "1,2,3"


def _config_values(config: Dict[str, Any], engine_name: Optional[str],
                   scales: Optional[Sequence[float]]):
    ocr_cfg = config.get("ocr", {})
    name = engine_name or ocr_cfg.get("engine", "dummy")
    chosen_scales = list(scales or ocr_cfg.get("scales", [1, 2, 3]))
    min_score = float(ocr_cfg.get("min_score", 0.5))
    return name, chosen_scales, min_score


def _recognize(image: Image.Image, engine, scales: Sequence[float],
               min_score: float) -> List[OCRItem]:
    items: List[OCRItem] = []
    for scale, scaled in multiscale(image, scales):
        for item in engine.recognize(scaled, scale=scale):
            if item.score >= min_score:
                items.append(item)
    return items


def _to_records(items: List[OCRItem], config: Dict[str, Any], source: str):
    table, debug = build_table(
        items,
        float(config.get("row_tolerance_ratio", 0.7)),
        float(config.get("col_tolerance_ratio", 0.9)),
    )
    records = extract_rows(table, config["columns"], config)
    for record in records:
        record.source = source
    return records, debug


def _save(records: List[RowRecord], config: Dict[str, Any], output_path: str,
          stats: RunStats, debug: Dict[str, float]) -> str:
    meta = {
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "OCR 引擎": stats.engine,
        "扫描尺度": stats.scales,
        "输入文件数": stats.files,
        "识别文本框数": stats.boxes,
        "输出行数": stats.rows,
        "需人工复核行数": stats.flagged_rows,
        "行聚类容差": debug.get("row_tolerance", ""),
        "低置信阈值": config.get("low_confidence_threshold", 0.85),
    }
    return write_report(records, config["columns"], output_path, meta)


def _finish(stats: RunStats, records: List[RowRecord]) -> RunStats:
    stats.rows = len(records)
    stats.flagged_rows = sum(1 for r in records if r.flagged)
    return stats


def run(input_dir: str, output_path: str, config: Dict[str, Any],
        engine_name: Optional[str] = None,
        scales: Optional[Sequence[float]] = None) -> RunStats:
    """Process every supported image in ``input_dir``."""
    name, chosen_scales, min_score = _config_values(config, engine_name, scales)
    engine = get_engine(name)
    stats = RunStats(engine=engine.name, scales=",".join(str(s) for s in chosen_scales))

    records: List[RowRecord] = []
    debug: Dict[str, float] = {}
    for path in iter_images(input_dir):
        image = load_image(path)
        items = _recognize(image, engine, chosen_scales, min_score)
        batch, debug = _to_records(items, config, os.path.basename(path))
        records.extend(batch)
        stats.files += 1
        stats.boxes += len(items)

    if stats.files == 0:
        raise FileNotFoundError(f"no supported images found in: {input_dir}")

    _finish(stats, records)
    _save(records, config, output_path, stats, debug)
    return stats


def run_demo(output_path: str, config: Dict[str, Any],
             scales: Optional[Sequence[float]] = None) -> RunStats:
    """Run the complete pipeline on synthetic data, with zero external assets."""
    name, chosen_scales, min_score = _config_values(config, "dummy", scales)
    engine = get_engine(name)
    stats = RunStats(files=1, engine=engine.name,
                     scales=",".join(str(s) for s in chosen_scales))

    image = Image.new("RGB", (900, 180), "white")
    items = _recognize(image, engine, chosen_scales, min_score)
    records, debug = _to_records(items, config, "demo")
    stats.boxes = len(items)

    _finish(stats, records)
    _save(records, config, output_path, stats, debug)
    return stats
