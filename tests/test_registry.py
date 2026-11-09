"""Tests for the OCR registry and plugin discovery."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from src import config_io  # noqa: E402
from src.ocr import available_engines, discover, engine_names, get_engine  # noqa: E402

PLUGIN_SOURCE = '''
class MyOCR:
    def __init__(self, **kwargs):
        self.options = kwargs

    def recognize(self, image):
        return [("插件文本", [(10, 10), (90, 10), (90, 30), (10, 30)], 0.9)]
'''

PLUGIN_DECL = {
    "name": "my_ocr",
    "module": "my_ocr.py",
    "class": "MyOCR",
    "kwargs": {"model_dir": "models/demo"},
    "description": "测试插件",
}


class TestRegistry(unittest.TestCase):

    def test_builtin_engines_are_always_available(self):
        with tempfile.TemporaryDirectory() as folder:
            names = engine_names(folder)
            for expected in ("dummy", "rapidocr", "maaocr"):
                self.assertIn(expected, names)

    def test_dummy_backend_still_works(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = get_engine("dummy", app_dir=folder)
            items = engine.recognize(Image.new("RGB", (100, 50), "white"))
            self.assertTrue(items)
            self.assertEqual(engine.name, "dummy")

    def test_plugin_is_discovered_loaded_and_normalised(self):
        with tempfile.TemporaryDirectory() as folder:
            engines = os.path.join(folder, "engines")
            os.makedirs(engines)
            with open(os.path.join(engines, "my_ocr.py"), "w", encoding="utf-8") as f:
                f.write(PLUGIN_SOURCE)
            with open(os.path.join(engines, "my_ocr.json"), "w", encoding="utf-8") as f:
                json.dump(PLUGIN_DECL, f)

            declared = discover(folder)
            self.assertIn("my_ocr", declared)
            self.assertIn("my_ocr", engine_names(folder))
            self.assertTrue(any("[插件]" in label
                                for _name, label in available_engines(folder)))

            engine = get_engine("my_ocr", app_dir=folder)
            items = engine.recognize(Image.new("RGB", (100, 50), "white"), scale=2.0)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].text, "插件文本")
            self.assertEqual(items[0].scale, 2.0)
            self.assertEqual(engine._impl.options["model_dir"], "models/demo")

    def test_unknown_engine_reports_available_names(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError) as ctx:
                get_engine("does_not_exist", app_dir=folder)
            self.assertIn("rapidocr", str(ctx.exception))

    def test_config_keeps_custom_engine_name(self):
        cfg = config_io.normalize({
            "columns": [{"name": "列"}],
            "ocr": {"engine": "my_ocr"},
        })
        self.assertEqual(cfg["ocr"]["engine"], "my_ocr")

    def test_maaocr_no_longer_requires_module_dir_in_config(self):
        cfg = config_io.example_config()
        cfg["ocr"]["engine"] = "maaocr"
        cfg["ocr"]["module_dir"] = ""
        self.assertEqual(config_io.validate(cfg), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
