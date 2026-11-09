#!/usr/bin/env python3
"""Full graphical front-end: every setting is editable without a command line.

Three tabs (Run / Recognition / Columns) plus a configuration bar for
load / save / save-as / restore-example. Long work runs on a worker thread and
results are delivered through a queue back to the main thread.

Launch::

    python gui.py
"""

import copy
import importlib.util
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.config_io import (ENGINES, EXAMPLE_PATH, LOCAL_PATH, TYPES,
                           example_config, load_config, normalize,
                           save_config, validate)
from src.pipeline import run, run_demo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "samples")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "report.xlsx")
DEMO_OUTPUT = os.path.join(HERE, "output", "demo_report.xlsx")

COL_FIELDS = ("name", "type", "pattern", "required", "index", "width")
COL_HEADINGS = ("列名", "类型", "正则校验", "必填", "绑定位置", "列宽")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.running = False
        self.columns = []

        root.title("截图转 Excel 报表工具 · 全图形化设置")
        root.geometry("900x700")
        root.minsize(860, 620)

        self._build()
        initial = LOCAL_PATH if os.path.isfile(LOCAL_PATH) else EXAMPLE_PATH
        try:
            self._load_config(initial, initial=True)
        except Exception as exc:
            self._apply_config(example_config())
            self._append(f"[警告] 配置加载失败，已恢复示例：{exc}")
        self.root.after(120, self._poll)

    # ---------------------------------------------------------------- layout
    def _build(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        tab_run = ttk.Frame(notebook, padding=10)
        tab_ocr = ttk.Frame(notebook, padding=10)
        tab_cols = ttk.Frame(notebook, padding=10)
        notebook.add(tab_run, text="  运行  ")
        notebook.add(tab_ocr, text="  识别参数  ")
        notebook.add(tab_cols, text="  列定义  ")

        self._build_run(tab_run)
        self._build_ocr(tab_ocr)
        self._build_columns(tab_cols)

        bar = ttk.LabelFrame(self.root, text=" 配置文件 ", padding=6)
        bar.pack(fill="x", padx=8, pady=4)
        self.config_path_var = tk.StringVar(value=EXAMPLE_PATH)
        ttk.Entry(bar, textvariable=self.config_path_var).pack(
            side="left", fill="x", expand=True, padx=(4, 6))
        for text, command in (("浏览", self._browse_config),
                              ("加载", lambda: self._load_config()),
                              ("保存", lambda: self._save_config(False)),
                              ("另存为", lambda: self._save_config(True)),
                              ("恢复示例", self._restore_example)):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)

        self.status = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w", padding=(6, 3)).pack(fill="x", side="bottom")

    def _build_run(self, parent):
        paths = ttk.LabelFrame(parent, text=" 输入输出 ", padding=10)
        paths.pack(fill="x", pady=(0, 10))
        paths.columnconfigure(1, weight=1)

        self.input_var = tk.StringVar(value=DEFAULT_INPUT)
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)
        self._path_row(paths, 0, "图片文件夹", self.input_var, self._pick_input)
        self._path_row(paths, 1, "输出 xlsx", self.output_var, self._pick_output)

        self.demo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent, text="演示模式（用内置合成数据跑通流程，忽略下方 OCR 引擎设置）",
            variable=self.demo_var).pack(anchor="w", pady=(0, 8))

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(0, 8))
        self.start_btn = ttk.Button(buttons, text="开始处理", command=self._start)
        self.start_btn.pack(side="left")
        ttk.Button(buttons, text="检查环境", command=self._check_env).pack(side="left", padx=8)

        log_frame = ttk.LabelFrame(parent, text=" 运行日志 ", padding=6)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _path_row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(2, 8), pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="浏览…", command=command).grid(row=row, column=2, padx=6)

    def _build_ocr(self, parent):
        parent.columnconfigure(1, weight=1)

        self.engine_var = tk.StringVar(value="dummy")
        self.scales_var = tk.StringVar(value="1,2,3")
        self.min_score_var = tk.StringVar(value="0.5")
        self.module_dir_var = tk.StringVar()
        self.model_dir_var = tk.StringVar()
        self.row_tol_var = tk.StringVar(value="0.7")
        self.col_tol_var = tk.StringVar(value="0.9")
        self.low_conf_var = tk.StringVar(value="0.85")
        self.strip_emoji_var = tk.BooleanVar(value=True)
        self.fullwidth_var = tk.BooleanVar(value=True)

        ttk.Label(parent, text="OCR 引擎").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        ttk.Combobox(parent, textvariable=self.engine_var, state="readonly",
                     values=ENGINES, width=24).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(parent, text="dummy = 合成数据（不识别图片）",
                  foreground="#b45309").grid(row=0, column=2, sticky="w", padx=6)

        for row, (label, var, hint) in enumerate((
            ("扫描尺度", self.scales_var, "逗号分隔，如 1,2,3；小图建议 2,3"),
            ("识别分数下限", self.min_score_var, "低于此分数的识别框丢弃"),
        ), start=1):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=6)
            ttk.Entry(parent, textvariable=var, width=24).grid(row=row, column=1, sticky="w", padx=4)
            ttk.Label(parent, text=hint, foreground="#6b7280").grid(
                row=row, column=2, sticky="w", padx=6)

        paths = ttk.LabelFrame(parent, text=" 自带 OCR 模块（仅 maaocr 引擎需要） ", padding=8)
        paths.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        paths.columnconfigure(1, weight=1)
        ttk.Label(paths, text="模块目录").grid(row=0, column=0, sticky="w", padx=4, pady=5)
        ttk.Entry(paths, textvariable=self.module_dir_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(paths, text="浏览…", command=self._pick_module_dir).grid(row=0, column=2, padx=4)
        ttk.Label(paths, text="模型目录").grid(row=1, column=0, sticky="w", padx=4, pady=5)
        ttk.Entry(paths, textvariable=self.model_dir_var).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(paths, text="浏览…", command=self._pick_model_dir).grid(row=1, column=2, padx=4)
        ttk.Label(paths, text="路径在界面里填写即可，程序内部设置，不需要命令行；不要提交到仓库",
                  foreground="#6b7280").grid(row=2, column=0, columnspan=3, sticky="w", padx=4, pady=(6, 0))

        cluster = ttk.LabelFrame(parent, text=" 聚类与复核 ", padding=8)
        cluster.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)
        for i, (label, var, hint) in enumerate((
            ("行聚类容差", self.row_tol_var, "相邻框垂直间距中位数 × 系数"),
            ("列聚类容差", self.col_tol_var, "单元格框宽中位数 × 系数"),
            ("低置信阈值", self.low_conf_var, "低于此值标黄待复核"),
        )):
            ttk.Label(cluster, text=label).grid(row=i, column=0, sticky="w", padx=4, pady=5)
            ttk.Entry(cluster, textvariable=var, width=12).grid(row=i, column=1, sticky="w", padx=4)
            ttk.Label(cluster, text=hint, foreground="#6b7280").grid(row=i, column=2, sticky="w", padx=6)

        switches = ttk.Frame(parent)
        switches.grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
        ttk.Checkbutton(switches, text="去除表情符号",
                        variable=self.strip_emoji_var).pack(side="left", padx=(4, 16))
        ttk.Checkbutton(switches, text="全角转半角",
                        variable=self.fullwidth_var).pack(side="left")

    def _build_columns(self, parent):
        ttk.Label(parent, text="行的顺序就是 Excel 的列顺序；双击某行可编辑",
                  foreground="#6b7280").pack(anchor="w", pady=(0, 8))

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=COL_FIELDS, show="headings", height=14)
        widths = (140, 80, 240, 60, 90, 70)
        for key, heading, width in zip(COL_FIELDS, COL_HEADINGS, widths):
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self._edit_column())

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=10)
        for text, command in (("新增", self._add_column),
                              ("编辑", self._edit_column),
                              ("删除", self._delete_column),
                              ("上移", lambda: self._move_column(-1)),
                              ("下移", lambda: self._move_column(1))):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=3)

    # ------------------------------------------------------------- picking
    def _pick_input(self):
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)

    def _pick_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel", "*.xlsx")])
        if path:
            self.output_var.set(path)

    def _pick_module_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.module_dir_var.set(path)

    def _pick_model_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.model_dir_var.set(path)

    def _browse_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.config_path_var.set(path)

    # ----------------------------------------------------------- columns UI
    def _selected_index(self):
        selection = self.tree.selection()
        return self.tree.index(selection[0]) if selection else None

    def _refresh_columns(self):
        self.tree.delete(*self.tree.get_children())
        for column in self.columns:
            self.tree.insert("", "end", values=(
                column.get("name", ""),
                column.get("type", "str"),
                column.get("pattern", ""),
                "是" if column.get("required") else "否",
                column.get("index", ""),
                column.get("width", ""),
            ))

    def _add_column(self):
        self._open_column_dialog(None)

    def _edit_column(self):
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("提示", "请先选中一列")
            return
        self._open_column_dialog(index)

    def _open_column_dialog(self, index):
        existing = self.columns[index] if index is not None else None

        dialog = tk.Toplevel(self.root)
        dialog.title("编辑列" if existing else "新增列")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.columnconfigure(1, weight=1)

        name_var = tk.StringVar(value=(existing or {}).get("name", ""))
        type_var = tk.StringVar(value=(existing or {}).get("type", "str"))
        pattern_var = tk.StringVar(value=(existing or {}).get("pattern", ""))
        required_var = tk.BooleanVar(value=(existing or {}).get("required", False))
        index_var = tk.StringVar(value=str((existing or {}).get("index", "")))
        width_var = tk.StringVar(value=str((existing or {}).get("width", "")))

        rows = [
            ("列名", ttk.Entry(dialog, textvariable=name_var, width=36)),
            ("类型", ttk.Combobox(dialog, textvariable=type_var, state="readonly",
                                  values=TYPES, width=33)),
            ("正则校验", ttk.Entry(dialog, textvariable=pattern_var, width=36)),
            ("绑定位置 index", ttk.Entry(dialog, textvariable=index_var, width=36)),
            ("列宽", ttk.Entry(dialog, textvariable=width_var, width=36)),
        ]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(dialog, text=label).grid(row=i, column=0, sticky="w", padx=12, pady=6)
            widget.grid(row=i, column=1, sticky="w", padx=8, pady=6)
        ttk.Checkbutton(dialog, text="必填（缺失时标黄）",
                        variable=required_var).grid(row=len(rows), column=1, sticky="w", padx=8, pady=4)
        ttk.Label(dialog, text="index / 列宽 留空表示不指定",
                  foreground="#6b7280").grid(row=len(rows) + 1, column=1, sticky="w", padx=8)

        def commit():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("输入有误", "列名不能为空", parent=dialog)
                return
            column = {
                "name": name,
                "type": type_var.get(),
                "pattern": pattern_var.get(),
                "required": bool(required_var.get()),
            }
            for key, var in (("index", index_var), ("width", width_var)):
                text = var.get().strip()
                if text:
                    try:
                        column[key] = int(text) if key == "index" else float(text)
                    except ValueError:
                        messagebox.showerror("输入有误", f"{key} 必须是数字", parent=dialog)
                        return
            clean = normalize({"columns": [column]})["columns"][0]
            if index is None:
                self.columns.append(clean)
            else:
                self.columns[index] = clean
            self._refresh_columns()
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=len(rows) + 2, column=0, columnspan=2, pady=12)
        ttk.Button(buttons, text="确定", command=commit).pack(side="left", padx=6)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=6)
        dialog.wait_window()

    def _delete_column(self):
        index = self._selected_index()
        if index is None or not messagebox.askyesno("确认", "删除选中的列？"):
            return
        self.columns.pop(index)
        self._refresh_columns()

    def _move_column(self, delta):
        index = self._selected_index()
        if index is None:
            return
        target = index + delta
        if not (0 <= target < len(self.columns)):
            return
        self.columns[index], self.columns[target] = self.columns[target], self.columns[index]
        self._refresh_columns()
        self.tree.selection_set(self.tree.get_children()[target])

    # ------------------------------------------------------------- config IO
    def _apply_config(self, cfg):
        cfg = normalize(cfg)
        ocr = cfg["ocr"]
        self.engine_var.set(ocr["engine"])
        self.scales_var.set(",".join(str(s) for s in ocr["scales"]))
        self.min_score_var.set(str(ocr["min_score"]))
        self.module_dir_var.set(ocr.get("module_dir", ""))
        self.model_dir_var.set(ocr.get("model_dir", ""))
        self.row_tol_var.set(str(cfg["row_tolerance_ratio"]))
        self.col_tol_var.set(str(cfg["col_tolerance_ratio"]))
        self.low_conf_var.set(str(cfg["low_confidence_threshold"]))
        self.strip_emoji_var.set(bool(cfg["strip_emoji"]))
        self.fullwidth_var.set(bool(cfg["normalize_fullwidth"]))
        self.columns = copy.deepcopy(cfg["columns"])
        self._refresh_columns()

    def _number(self, var, label):
        try:
            return float(var.get())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"「{label}」必须是数字") from exc

    def _collect_config(self):
        try:
            scales = [float(part.strip())
                      for part in self.scales_var.get().split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError("「扫描尺度」格式应为 1,2,3 这样的数字列表") from exc
        return normalize({
            "columns": copy.deepcopy(self.columns),
            "ocr": {
                "engine": self.engine_var.get(),
                "scales": scales,
                "min_score": self._number(self.min_score_var, "识别分数下限"),
                "module_dir": self.module_dir_var.get().strip(),
                "model_dir": self.model_dir_var.get().strip(),
            },
            "row_tolerance_ratio": self._number(self.row_tol_var, "行聚类容差"),
            "col_tolerance_ratio": self._number(self.col_tol_var, "列聚类容差"),
            "low_confidence_threshold": self._number(self.low_conf_var, "低置信阈值"),
            "strip_emoji": bool(self.strip_emoji_var.get()),
            "normalize_fullwidth": bool(self.fullwidth_var.get()),
        })

    def _load_config(self, path=None, initial=False):
        if not path:
            path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
            if not path:
                return
        try:
            self._apply_config(load_config(path))
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))
            return
        self.config_path_var.set(path)
        self._append(f"[配置] {'启动加载' if initial else '已加载'} {os.path.basename(path)}")

    def _restore_example(self):
        self._apply_config(example_config())
        self.config_path_var.set(EXAMPLE_PATH)
        self._append("[配置] 已恢复示例（保存时会要求另存为，不会覆盖示例文件）")

    def _save_config(self, save_as):
        try:
            cfg = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc))
            return
        # A missing maaocr path is allowed while simply editing a config;
        # it is checked again when an actual run starts.
        problems = [p for p in validate(cfg) if "模块目录" not in p]
        if problems:
            messagebox.showerror("设置有误", "\n".join(problems))
            return
        path = self.config_path_var.get().strip()
        if save_as or not path or os.path.abspath(path) == os.path.abspath(EXAMPLE_PATH):
            chosen = filedialog.asksaveasfilename(
                defaultextension=".json", initialfile="config.json",
                filetypes=[("JSON", "*.json")])
            if not chosen:
                return
            path = chosen
        save_config(cfg, path)
        self.config_path_var.set(path)
        self._append(f"[配置] 已保存 {path}")

    # ---------------------------------------------------------------- actions
    def _append(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def _check_env(self):
        lines = [f"Python: {sys.version.split()[0]}", f"工作目录: {HERE}"]
        for module, label in (("openpyxl", "openpyxl"), ("PIL", "Pillow"),
                              ("tkinter", "tkinter"),
                              ("rapidocr_onnxruntime", "RapidOCR 后端")):
            found = importlib.util.find_spec(module) is not None
            lines.append(f"{label}: {'已安装' if found else '未安装'}")
        lines.append("dummy 后端: 内置（输出合成数据，不识别图片）")
        module_dir = self.module_dir_var.get().strip()
        if module_dir:
            lines.append("maaocr 模块文件: " +
                         ("存在" if os.path.isfile(os.path.join(module_dir, "maa_ocr.py"))
                          else "未找到 maa_ocr.py"))
        model_dir = self.model_dir_var.get().strip()
        if model_dir:
            for filename in ("det.onnx", "rec.onnx", "keys.txt"):
                lines.append(f"  {filename}: " +
                             ("存在" if os.path.isfile(os.path.join(model_dir, filename))
                              else "缺失"))
        self._append("---- 环境检查 ----")
        for line in lines:
            self._append(line)
        self.status.set("环境检查完成")

    def _start(self):
        if self.running:
            return
        try:
            cfg = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc))
            return

        demo = bool(self.demo_var.get())
        problems = validate(cfg) if not demo else []
        if demo and not cfg["columns"]:
            problems = ["至少需要一列"]
        if problems:
            messagebox.showerror("设置有误", "\n".join(problems))
            return
        if not demo and cfg["ocr"]["engine"] == "dummy":
            if not messagebox.askyesno(
                    "确认",
                    "当前 OCR 引擎是 dummy，只会输出内置合成数据，不会识别你的图片。\n\n"
                    "请在「识别参数」页换成 maaocr 或 rapidocr。\n仍要继续吗？"):
                return

        # Backend paths are applied in-process, so no shell/environment setup
        # is needed before launching the GUI.
        if not demo and cfg["ocr"]["engine"] == "maaocr":
            os.environ["OCR_MODULE_DIR"] = cfg["ocr"]["module_dir"]
            if cfg["ocr"]["model_dir"]:
                os.environ["OCR_MODEL_DIR"] = cfg["ocr"]["model_dir"]
            else:
                os.environ.pop("OCR_MODEL_DIR", None)

        params = {
            "config": cfg,
            "demo": demo,
            "input": self.input_var.get(),
            "output": self.output_var.get(),
            "demo_output": DEMO_OUTPUT,
        }
        self.running = True
        self.start_btn.config(state="disabled")
        self.status.set("处理中…")
        engine_label = "演示模式(dummy)" if demo else cfg["ocr"]["engine"]
        self._append(f"开始处理… 引擎={engine_label} 尺度={cfg['ocr']['scales']}")
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()

    def _worker(self, params):
        cfg = params["config"]
        try:
            if params["demo"]:
                output = params["demo_output"]
                stats = run_demo(output, cfg, cfg["ocr"]["scales"])
            else:
                output = params["output"]
                stats = run(params["input"], output, cfg,
                            cfg["ocr"]["engine"], cfg["ocr"]["scales"])
            message = (
                f"完成：{output}\n"
                f"文件 {stats.files} | 文本框 {stats.boxes} | 行 {stats.rows} | "
                f"需复核 {stats.flagged_rows} | 引擎 {stats.engine}"
            )
            self.queue.put(("ok", message))
        except Exception as exc:
            self.queue.put(("error", f"{type(exc).__name__}: {exc}"))

    def _poll(self):
        try:
            kind, message = self.queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._append(("[完成] " if kind == "ok" else "[失败] ") + message)
            self.running = False
            self.start_btn.config(state="normal")
            self.status.set("完成" if kind == "ok" else "失败")
            if kind == "error":
                messagebox.showerror("处理失败", message)
        self.root.after(120, self._poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
