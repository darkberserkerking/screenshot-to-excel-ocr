"""Configuration loading, saving and validation for the graphical interface.

Keeping this separate from the widgets makes every setting round-trippable and
unit-testable without opening a window.
"""

import copy
import json
import os
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE_PATH = os.path.join(ROOT, "config.example.json")
LOCAL_PATH = os.path.join(ROOT, "config.json")

TYPES = ("str", "int", "float", "date")
ENGINES = ("dummy", "rapidocr", "maaocr")

DEFAULTS: Dict[str, Any] = {
    "ocr": {
        "engine": "dummy",
        "scales": [1, 2, 3],
        "min_score": 0.5,
        # Local-only paths for the maaocr backend. Kept empty in the shipped
        # example so no machine-specific path ever lands in the repository.
        "module_dir": "",
        "model_dir": "",
    },
    "row_tolerance_ratio": 0.7,
    "col_tolerance_ratio": 0.9,
    "low_confidence_threshold": 0.85,
    "strip_emoji": True,
    "normalize_fullwidth": True,
}


def _column(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw = raw or {}
    result: Dict[str, Any] = {
        "name": str(raw.get("name") or "").strip() or "未命名",
        "type": str(raw.get("type") or "str"),
        "pattern": str(raw.get("pattern") or ""),
        "required": bool(raw.get("required", False)),
    }
    if result["type"] not in TYPES:
        result["type"] = "str"
    if raw.get("index") not in (None, ""):
        try:
            result["index"] = int(raw["index"])
        except (TypeError, ValueError):
            pass
    if raw.get("width") not in (None, ""):
        try:
            result["width"] = float(raw["width"])
        except (TypeError, ValueError):
            pass
    return result


def normalize(raw: Any = None) -> Dict[str, Any]:
    """Return a complete config, filling in any missing keys with defaults."""
    raw = raw or {}
    config = {k: copy.deepcopy(v) for k, v in DEFAULTS.items()}
    for key, value in raw.items():
        if key not in ("ocr", "columns"):
            config[key] = value
    config["ocr"].update(raw.get("ocr") or {})
    if config["ocr"].get("engine") not in ENGINES:
        config["ocr"]["engine"] = "dummy"
    config["columns"] = [_column(c) for c in (raw.get("columns") or [])]
    return config


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return normalize(json.load(handle))


def example_config() -> Dict[str, Any]:
    return load_config(EXAMPLE_PATH)


def save_config(config: Dict[str, Any], path: str) -> str:
    """Write a normalised config as UTF-8 JSON and return the path."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(normalize(config), handle, ensure_ascii=False, indent=2)
    return path


def validate(config: Dict[str, Any]) -> List[str]:
    """Return human-readable problems; an empty list means the config is usable."""
    cfg = normalize(config)
    errors: List[str] = []

    columns = cfg["columns"]
    if not columns:
        errors.append("至少需要在「列定义」里添加一列")
    names = [c["name"] for c in columns]
    if len(names) != len(set(names)):
        errors.append("列名不能重复")
    if any(not c["name"] for c in columns):
        errors.append("列名不能为空")

    scales = cfg["ocr"].get("scales") or []
    try:
        values = [float(s) for s in scales]
    except (TypeError, ValueError):
        values = []
    if not values or any(v <= 0 for v in values):
        errors.append("扫描尺度必须是正数，例如 1,2,3")

    for key, label in (("min_score", "识别分数下限"),
                       ("row_tolerance_ratio", "行聚类容差"),
                       ("col_tolerance_ratio", "列聚类容差"),
                       ("low_confidence_threshold", "低置信阈值")):
        try:
            value = float(cfg["ocr"][key] if key == "min_score" else cfg[key])
        except (TypeError, ValueError, KeyError):
            errors.append(f"{label} 必须是数字")
            continue
        if value < 0:
            errors.append(f"{label} 不能为负数")

    if cfg["ocr"]["engine"] == "maaocr" and not cfg["ocr"].get("module_dir"):
        errors.append("使用 maaocr 引擎时，必须填写「模块目录」")
    return errors
