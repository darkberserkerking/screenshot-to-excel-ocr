"""Configuration loading, saving and validation for the graphical interface.

Keeping this separate from the widgets makes every setting round-trippable and
unit-testable without opening a window.
"""

import copy
import json
import os
import sys
from typing import Any, Dict, List

# In a one-file build the shipped example lives in the bundle directory, while
# user-editable config.json and engines/ stay next to the executable.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    BUNDLE_DIR = APP_DIR

ROOT = APP_DIR
EXAMPLE_PATH = os.path.join(BUNDLE_DIR, "config.example.json")
LOCAL_PATH = os.path.join(APP_DIR, "config.json")

TYPES = ("str", "int", "float", "date")
ENGINES = ("dummy", "rapidocr", "maaocr")  # built-ins; plugin names are dynamic
MODES = ("table", "text_dump")

DEFAULTS: Dict[str, Any] = {
    "ocr": {
        "engine": "rapidocr",
        "scales": [1, 2, 3],
        "min_score": 0.5,
        # Optional local paths for the maaocr adapter. Left empty in the
        # shipped example; auto-discovery uses engines/maaocr/.
        "module_dir": "",
        "model_dir": "",
    },
    "output": {"mode": "table"},
    "dump": {"dedup_grid": 12.0},
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
        if key == "columns":
            continue
        if key in config and isinstance(config[key], dict):
            if isinstance(value, dict):
                config[key].update(value)
        else:
            config[key] = value
    # Engine names are intentionally not restricted to the built-in list:
    # user plugins declared in engines/*.json are valid too.
    if config["output"].get("mode") not in MODES:
        config["output"]["mode"] = "table"
    config["columns"] = [_column(c) for c in (raw.get("columns") or [])]
    return config


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return normalize(json.load(handle))


def example_config() -> Dict[str, Any]:
    return load_config(EXAMPLE_PATH)


def save_config(config: Dict[str, Any], path: str) -> str:
    """Write a normalised config as UTF-8 JSON and return the path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(normalize(config), handle, ensure_ascii=False, indent=2)
    return path


def validate(config: Dict[str, Any]) -> List[str]:
    """Return human-readable problems; an empty list means the config is usable."""
    cfg = normalize(config)
    errors: List[str] = []

    columns = cfg["columns"]
    if not columns:
        errors.append("至少需要在「列定义」里添加一列（仅表格提取模式需要）")
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

    try:
        if float(cfg["dump"]["dedup_grid"]) <= 0:
            errors.append("去重网格必须大于 0")
    except (TypeError, ValueError, KeyError):
        errors.append("去重网格必须是数字")

    return errors
