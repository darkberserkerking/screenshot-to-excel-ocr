#!/usr/bin/env python3
"""Optional desktop front-end for the extraction pipeline.

Built on tkinter (Python standard library) so the project keeps zero GUI
dependencies. Run with::

    python gui.py

Long-running work happens on a worker thread; results come back through a
queue and are applied on the main thread, which keeps the window responsive.
"""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.pipeline import run, run_demo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "config.example.json")
DEFAULT_INPUT = os.path.join(HERE, "samples")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "report.xlsx")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.running = False
        root.title("截图转 Excel 报表工具")
        root.geometry("720x520")
        root.minsize(660, 460)
        self._build()
        self.root.after(120, self._poll)

    def _row(self, parent, label: str, row: int) -> tk.StringVar:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=7)
        var = tk.StringVar()
        ttk.Entry(parent, textvariable=var, width=62).grid(
            row=row, column=1, sticky="ew", padx=6, pady=7)
        return var

    def _build(self):
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self.input_var = self._row(frame, "图片文件夹", 0)
        self.input_var.set(DEFAULT_INPUT)
        ttk.Button(frame, text="浏览…", command=self._pick_input).grid(row=0, column=2, padx=6)

        self.config_var = self._row(frame, "配置文件", 1)
        self.config_var.set(DEFAULT_CONFIG)
        ttk.Button(frame, text="浏览…", command=self._pick_config).grid(row=1, column=2, padx=6)

        self.output_var = self._row(frame, "输出 xlsx", 2)
        self.output_var.set(DEFAULT_OUTPUT)
        ttk.Button(frame, text="浏览…", command=self._pick_output).grid(row=2, column=2, padx=6)

        ttk.Label(frame, text="OCR 引擎").grid(row=3, column=0, sticky="w", padx=12, pady=7)
        self.engine_var = tk.StringVar(value="dummy")
        ttk.Combobox(frame, textvariable=self.engine_var, state="readonly",
                     values=("dummy", "rapidocr", "maaocr"), width=20).grid(
            row=3, column=1, sticky="w", padx=6)

        ttk.Label(frame, text="扫描尺度").grid(row=4, column=0, sticky="w", padx=12, pady=7)
        self.scales_var = tk.StringVar(value="1,2,3")
        ttk.Entry(frame, textvariable=self.scales_var, width=20).grid(
            row=4, column=1, sticky="w", padx=6)

        self.demo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="演示模式（内置合成数据，无需图片与模型）",
                        variable=self.demo_var).grid(row=5, column=1, sticky="w", padx=6, pady=4)

        self.start_btn = ttk.Button(frame, text="开始处理", command=self._start)
        self.start_btn.grid(row=6, column=1, sticky="w", padx=6, pady=10)

        ttk.Label(frame, text="运行日志").grid(row=7, column=0, sticky="nw", padx=12, pady=6)
        self.log = tk.Text(frame, height=12, wrap="word")
        self.log.grid(row=7, column=1, columnspan=2, sticky="nsew", padx=6, pady=6)
        frame.rowconfigure(7, weight=1)

    def _pick_input(self):
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)

    def _pick_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.config_var.set(path)

    def _pick_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.output_var.set(path)

    def _append(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def _start(self):
        if self.running:
            return
        try:
            with open(self.config_var.get(), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            scales = [float(part.strip())
                      for part in self.scales_var.get().split(",") if part.strip()]
        except Exception as exc:
            messagebox.showerror("配置有误", str(exc))
            return

        # Read every tkinter variable on the main thread before starting work.
        params = {
            "config": config,
            "scales": scales,
            "demo": bool(self.demo_var.get()),
            "input": self.input_var.get(),
            "output": self.output_var.get(),
            "engine": self.engine_var.get(),
        }
        self.running = True
        self.start_btn.config(state="disabled")
        self._append("开始处理…")
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()

    def _worker(self, params):
        try:
            if params["demo"]:
                output = os.path.join(HERE, "output", "demo_report.xlsx")
                stats = run_demo(output, params["config"], params["scales"])
            else:
                output = params["output"]
                stats = run(params["input"], output, params["config"],
                            params["engine"], params["scales"])
            message = (
                f"完成：{output}\n"
                f"文件 {stats.files} | 文本框 {stats.boxes} | 行 {stats.rows} | "
                f"需复核 {stats.flagged_rows} | 引擎 {stats.engine}"
            )
            self.queue.put(("ok", message))
        except Exception as exc:  # keep the window alive on any pipeline failure
            self.queue.put(("error", str(exc)))

    def _poll(self):
        try:
            kind, message = self.queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._append(("[完成] " if kind == "ok" else "[失败] ") + message)
            self.running = False
            self.start_btn.config(state="normal")
            if kind == "error":
                messagebox.showerror("处理失败", message)
        self.root.after(120, self._poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
