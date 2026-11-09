"""Round-trip and validation tests for the GUI configuration layer."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config_io  # noqa: E402


class TestConfigIO(unittest.TestCase):

    def test_shipped_example_has_no_machine_specific_paths(self):
        cfg = config_io.example_config()
        self.assertEqual(cfg["ocr"]["module_dir"], "")
        self.assertEqual(cfg["ocr"]["model_dir"], "")
        self.assertEqual(cfg["col_tolerance_ratio"], 0.9)
        self.assertEqual(cfg["ocr"]["engine"], "rapidocr")

    def test_normalize_fills_defaults_and_drops_bad_values(self):
        cfg = config_io.normalize({"columns": [{"name": "甲", "type": "bogus"}]})
        self.assertEqual(cfg["ocr"]["engine"], "rapidocr")
        self.assertEqual(cfg["ocr"]["scales"], [1, 2, 3])
        self.assertEqual(cfg["columns"][0]["type"], "str")
        self.assertEqual(cfg["low_confidence_threshold"], 0.85)

    def test_roundtrip_preserves_index_and_new_columns(self):
        cfg = config_io.example_config()
        cfg["columns"].append({"name": "新增列", "type": "int",
                               "required": True, "pattern": "", "index": 2})
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "cfg.json")
            config_io.save_config(cfg, path)
            loaded = config_io.load_config(path)
        self.assertEqual(loaded["columns"][-1]["name"], "新增列")
        self.assertEqual(loaded["columns"][-1]["index"], 2)

    def test_validate_reports_problems(self):
        self.assertEqual(config_io.validate(config_io.example_config()), [])

        empty = config_io.example_config()
        empty["columns"] = []
        self.assertTrue(config_io.validate(empty))

        bad_scales = config_io.example_config()
        bad_scales["ocr"]["scales"] = []
        self.assertTrue(any("扫描尺度" in e for e in config_io.validate(bad_scales)))

        # maaocr now auto-discovers engines/maaocr/, so a blank path is valid.
        auto_discovery = config_io.example_config()
        auto_discovery["ocr"]["engine"] = "maaocr"
        self.assertEqual(config_io.validate(auto_discovery), [])

        duplicate = config_io.example_config()
        duplicate["columns"][1]["name"] = duplicate["columns"][0]["name"]
        self.assertTrue(any("重复" in e for e in config_io.validate(duplicate)))

    def test_custom_engine_name_is_preserved(self):
        cfg = config_io.normalize({
            "columns": [{"name": "列"}],
            "ocr": {"engine": "my_plugin"},
        })
        self.assertEqual(cfg["ocr"]["engine"], "my_plugin")
        self.assertEqual(config_io.validate(cfg), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
