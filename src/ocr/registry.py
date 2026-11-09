"""OCR backend registry with plugin discovery.

Built-in backends are imported lazily. A custom backend is declared by a small
JSON file placed in ``<app_dir>/engines/*.json``::

    {
      "name": "my_ocr",
      "module": "my_ocr.py",
      "class": "MyOCR",
      "kwargs": {"model_dir": "models/my"},
      "description": "my custom engine"
    }

The module must expose a class with ``recognize(image)`` returning one of the
result shapes accepted by :func:`parse_raw`; a ``PIL.Image`` is passed in.
Adding an engine never requires touching the main program.
"""

import glob
import importlib.util
import json
import os
from typing import Any, Dict, List, Tuple

from .base import BaseOCREngine, parse_raw

BUILTIN: Dict[str, Tuple[str, str]] = {
    "dummy": ("内置", "合成数据，用于演示与测试"),
    "rapidocr": ("内置", "RapidOCR / ONNX Runtime，随程序分发"),
    "maaocr": ("内置适配器", "自动发现 engines/maaocr/ 或界面指定目录"),
}


def engines_dir(app_dir: Any = None) -> str:
    from ..config_io import APP_DIR
    return os.path.join(app_dir or APP_DIR, "engines")


def discover(app_dir: Any = None) -> Dict[str, Dict[str, Any]]:
    """Return ``{name: declaration}`` for every valid plugin declaration."""
    folder = engines_dir(app_dir)
    found: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(folder):
        return found
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                declaration = json.load(handle)
            name = str(declaration.get("name") or "").strip()
            module = str(declaration.get("module") or "").strip()
            if not name or not module or name in BUILTIN:
                continue
            declaration["_dir"] = os.path.dirname(path)
            found[name] = declaration
        except (OSError, ValueError, TypeError):
            continue
    return found


def available_engines(app_dir: Any = None) -> List[Tuple[str, str]]:
    """``[(name, label), ...]`` for the GUI dropdown."""
    items = [(name, f"[{source}] {description}")
             for name, (source, description) in BUILTIN.items()]
    for name, declaration in discover(app_dir).items():
        label = declaration.get("description") or declaration.get("module") or name
        items.append((name, f"[插件] {label}"))
    return items


def engine_names(app_dir: Any = None) -> List[str]:
    return [name for name, _label in available_engines(app_dir)]


class PluginEngine(BaseOCREngine):
    """Wrap a user-supplied class so it satisfies the built-in interface."""

    def __init__(self, declaration: Dict[str, Any]):
        self.name = declaration["name"]
        module_path = os.path.join(declaration["_dir"], declaration["module"])
        if not os.path.isfile(module_path):
            raise RuntimeError(f"插件模块不存在：{module_path}")
        spec = importlib.util.spec_from_file_location(
            f"ocr_plugin_{self.name}", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载插件模块：{module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, declaration.get("class", "Engine"), None)
        if cls is None:
            raise RuntimeError(
                f"插件 {self.name} 缺少类 {declaration.get('class', 'Engine')}")
        self._impl = cls(**declaration.get("kwargs") or {})

    def recognize(self, image: Any, scale: float = 1.0):
        return parse_raw(self._impl.recognize(image), scale)


def get_engine(name: str, app_dir: Any = None, **kwargs: Any) -> BaseOCREngine:
    """Resolve a built-in or plugin backend by name."""
    name = (name or "dummy").strip()
    if name == "dummy":
        from .dummy import DummyEngine
        return DummyEngine(**kwargs)
    if name == "rapidocr":
        from .rapidocr import RapidOCREngine
        return RapidOCREngine(**kwargs)
    if name == "maaocr":
        from .maaocr import MaaOCREngine
        return MaaOCREngine(**kwargs)
    declaration = discover(app_dir).get(name)
    if declaration:
        return PluginEngine(declaration)
    raise ValueError(
        f"未知 OCR 引擎 {name!r}；可用：{', '.join(engine_names(app_dir))}")
