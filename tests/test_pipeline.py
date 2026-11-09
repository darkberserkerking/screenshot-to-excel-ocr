"""Pure-logic tests: no OCR model, no image files, no network required."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook  # noqa: E402
from PIL import Image  # noqa: E402

from src.cluster import build_table  # noqa: E402
from src.extract import clean_text, coerce, extract_rows  # noqa: E402
from src.models import Cell, OCRItem  # noqa: E402
from src.ocr import get_engine  # noqa: E402
from src.ocr.base import parse_raw  # noqa: E402
from src.pipeline import run_demo  # noqa: E402
from src.preprocess import multiscale  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    with open(os.path.join(HERE, "config.example.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def box(x, y, w=130, h=26):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


class TestNormalisation(unittest.TestCase):

    def test_scale_coordinates_are_normalised(self):
        item = OCRItem("A", box(20, 30), 0.9, scale=2.0)
        self.assertEqual(item.normalized().center, (42.5, 21.5))

    def test_parse_raw_accepts_both_tuple_orders(self):
        a = parse_raw([("文本", box(1, 2), 0.8)], scale=1.0)
        b = parse_raw([(box(1, 2), "文本", 0.8)], scale=1.0)
        self.assertEqual(a[0].text, b[0].text)
        self.assertEqual(a[0].box, b[0].box)

    def test_multiscale_keeps_coordinate_semantics(self):
        image = Image.new("RGB", (100, 50), "white")
        pairs = multiscale(image, [1, 2, 3])
        self.assertEqual([p[0] for p in pairs], [1.0, 2.0, 3.0])
        self.assertEqual(pairs[2][1].size, (300, 150))


class TestCleaning(unittest.TestCase):

    def test_fullwidth_and_emoji(self):
        self.assertEqual(clean_text("ＡＢＣ１２３\u3000测试🎉"), "ABC123 测试")

    def test_coerce_number_and_date(self):
        self.assertEqual(coerce("1,024", "int"), 1024)
        self.assertEqual(coerce("2026/11/05", "date"), "2026-11-05")
        self.assertIsNone(coerce("暂无", "int"))


class TestVoting(unittest.TestCase):

    def test_majority_vote_recovers_correct_text(self):
        engine = get_engine("dummy")
        items = []
        image = Image.new("RGB", (900, 180), "white")
        for scale, scaled in multiscale(image, [1, 2, 3]):
            items.extend(engine.recognize(scaled, scale=scale))
        table, stats = build_table(items, 0.7)
        self.assertEqual(len(table), 3, "three source rows should survive voting")
        second_row = [cell.text for cell in table[1]]
        self.assertIn("设备登记表", second_row,
                      "2x mis-recognition must lose the 1x/3x majority vote")
        self.assertGreaterEqual(stats["rows"], 3)


class TestEndToEnd(unittest.TestCase):

    def test_demo_writes_valid_workbook(self):
        config = load_config()
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "demo.xlsx")
            stats = run_demo(target, config)
            self.assertTrue(os.path.isfile(target))
            self.assertEqual(stats.rows, 3)
            wb = load_workbook(target)
            self.assertIn("数据", wb.sheetnames)
            self.assertIn("运行说明", wb.sheetnames)
            ws = wb["数据"]
            self.assertEqual(ws["A1"].value, "编号")
            self.assertEqual(ws["A2"].value, "A-1024")
            self.assertEqual(ws.max_row, 4)  # header + 3 rows
            wb.close()

    def test_extract_marks_missing_required_field(self):
        config = load_config()
        table = [[Cell("x", 2, 0.95, 10)]]
        records = extract_rows(table, config["columns"], config)
        self.assertTrue(records[0].flagged)


if __name__ == "__main__":
    unittest.main(verbosity=2)
