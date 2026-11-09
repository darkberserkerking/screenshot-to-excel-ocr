#!/usr/bin/env python3
"""Command line entry point. Run ``python cli.py --help`` for usage."""

import argparse
import json
import os
import sys
from typing import Optional, Sequence

from src.pipeline import run, run_demo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "config.example.json")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "report.xlsx")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not config.get("columns"):
        raise ValueError("config must define at least one column")
    return config


def _parse_scales(text: str):
    if not text.strip():
        return None
    return [float(part.strip()) for part in text.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract table-like data from screenshots into an Excel report.")
    parser.add_argument("--input", default=os.path.join(HERE, "samples"),
                        help="folder containing screenshots")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="output .xlsx path")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="column/rule config JSON")
    parser.add_argument("--engine", choices=("dummy", "rapidocr", "maaocr"),
                        help="override the OCR backend from config")
    parser.add_argument("--scales", default="", help='e.g. "1,2,3"')
    parser.add_argument("--demo", action="store_true",
                        help="run on built-in sample data, no OCR model required")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        scales = _parse_scales(args.scales)
        output = args.output
        if args.demo:
            if output == DEFAULT_OUTPUT:
                output = os.path.join(HERE, "output", "demo_report.xlsx")
            stats = run_demo(output, config, scales)
        else:
            stats = run(args.input, output, config, args.engine, scales)
    except (OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[ok] report -> {output}")
    print(f"     files={stats.files}  boxes={stats.boxes}  "
          f"rows={stats.rows}  need_review={stats.flagged_rows}  "
          f"engine={stats.engine}  scales={stats.scales}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
