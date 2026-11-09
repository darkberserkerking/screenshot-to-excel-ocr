"""Tests for the text-list export mode (no real OCR model required)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook  # noqa: E402
from PIL import Image  # noqa: E402

from src import config_io  # noqa: E402
from src.dump import collect_items, deduplicate, run_text_dump  # noqa: E402
from src.models import OCRItem  # noqa: E402


def box_at(cx, cy, w=20, h=9):
    """A rectangle whose centre is exactly (cx, cy)."""
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
            (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def scaled_item(text, cx, cy, score, scale):
    """A box reported at ``scale``; normalisation brings it back to (cx, cy)."""
    return OCRItem(text, box_at(cx * scale, cy * scale,
                                20 * scale, 9 * scale), score, scale)


class TestDedup(unittest.TestCase):

    def test_same_box_at_different_scales_collapses(self):
        base = OCRItem("文本", [(30, 40), (160, 40), (160, 66), (30, 66)], 0.9, 1.0)
        doubled = OCRItem("文本", [(60, 80), (320, 80), (320, 132), (60, 132)], 0.95, 2.0)
        rows = deduplicate([("a.png", base, 1.0), ("a.png", doubled, 2.0)], grid=12)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "文本")
        self.assertEqual(rows[0][2], 0.95)
        self.assertAlmostEqual(rows[0][3], 95.0, places=1)

    def test_different_files_are_kept_separately(self):
        item = OCRItem("文本", [(10, 10), (50, 10), (50, 30), (10, 30)], 0.9, 1.0)
        rows = deduplicate([("a.png", item, 1.0), ("b.png", item, 1.0)], grid=12)
        self.assertEqual(len(rows), 2)

    # --- regression: bucket-boundary duplicates from real screenshots ------
    def test_bucket_boundary_duplicates_are_merged(self):
        # Under the old grid key: 647.0 -> bucket 54, 641.5 -> bucket 53.
        a = scaled_item("强攻秘藏-第56层", 647.0, 34.5, 0.980, 1.0)
        b = scaled_item("强攻秘藏-第56层", 641.5, 35.5, 0.957, 2.0)
        rows = deduplicate([("备战.png", a, 1.0), ("备战.png", b, 2.0)], grid=12)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "强攻秘藏-第56层")
        self.assertEqual(rows[0][2], 0.980)

    def test_subpixel_drift_is_merged(self):
        # Under the old grid key: 1014.0 -> bucket 84, 1014.3 -> bucket 85.
        a = scaled_item("自动挑战", 541.0, 953.8, 0.994, 2.0)
        b = scaled_item("自动挑战", 541.3, 954.2, 0.994, 3.0)
        rows = deduplicate([("备战.png", a, 2.0), ("备战.png", b, 3.0)], grid=12)
        self.assertEqual(len(rows), 1)

    def test_largest_observed_drift_is_merged(self):
        a = scaled_item("首次通关", 636.5, 649.5, 0.984, 1.0)
        b = scaled_item("首次通关", 650.8, 649.8, 0.990, 3.0)
        rows = deduplicate([("自动结束.png", a, 1.0), ("自动结束.png", b, 3.0)], grid=12)
        self.assertEqual(len(rows), 1)

    def test_distant_identical_labels_are_preserved(self):
        # A row of six "450" rewards ~100px apart must NOT be collapsed.
        items = [("关卡.png", OCRItem("450", box_at(100 + i * 100, 780), 0.98, 1.0), 1.0)
                 for i in range(6)]
        rows = deduplicate(items, grid=12)
        self.assertEqual(len(rows), 6)


class TestTextDump(unittest.TestCase):

    def _image_folder(self, folder):
        Image.new("RGB", (900, 200), "white").save(os.path.join(folder, "shot.png"))

    def test_dummy_single_scale_produces_expected_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            self._image_folder(folder)
            out = os.path.join(folder, "dump.xlsx")
            cfg = config_io.normalize({"columns": [{"name": "列"}]})
            stats = run_text_dump(folder, out, cfg, engine_name="dummy", scales=[1])
            self.assertEqual(stats.files, 1)
            self.assertEqual(stats.rows, 14)  # non-empty cells in DEMO_ROWS
            self.assertEqual(stats.boxes, 14)
            wb = load_workbook(out)
            ws = wb["文本清单"]
            self.assertEqual([c.value for c in ws[1]][:4],
                             ["来源文件", "序号", "识别文本", "置信度"])
            self.assertEqual(ws.max_row, 15)
            wb.close()

    def test_multiscale_is_normalised_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            self._image_folder(folder)
            out = os.path.join(folder, "dump.xlsx")
            cfg = config_io.normalize({"columns": [{"name": "列"}]})
            stats = run_text_dump(folder, out, cfg, engine_name="dummy", scales=[1, 3])
            self.assertEqual(stats.boxes, 28)
            self.assertEqual(stats.rows, 14)

    def test_empty_folder_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = config_io.normalize({"columns": [{"name": "列"}]})
            with self.assertRaises(FileNotFoundError):
                run_text_dump(folder, os.path.join(folder, "x.xlsx"), cfg,
                              engine_name="dummy", scales=[1])


class TestModeConfig(unittest.TestCase):

    def test_defaults_and_mode_switch(self):
        cfg = config_io.example_config()
        self.assertEqual(cfg["output"]["mode"], "table")
        self.assertEqual(cfg["dump"]["dedup_grid"], 12)
        cfg["output"]["mode"] = "text_dump"
        cfg["dump"]["dedup_grid"] = 24
        self.assertEqual(config_io.validate(cfg), [])
        roundtrip = config_io.normalize(cfg)
        self.assertEqual(roundtrip["output"]["mode"], "text_dump")
        self.assertEqual(roundtrip["dump"]["dedup_grid"], 24)

    def test_bad_mode_and_grid(self):
        cfg = config_io.example_config()
        cfg["output"]["mode"] = "nonsense"
        self.assertEqual(cfg["output"]["mode"], "nonsense")
        self.assertEqual(config_io.normalize(cfg)["output"]["mode"], "table")
        bad = config_io.example_config()
        bad["dump"]["dedup_grid"] = 0
        self.assertTrue(any("去重网格" in e for e in config_io.validate(bad)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
