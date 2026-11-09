#!/usr/bin/env python3
"""Graphical front-end with a light card layout.

Light customtkinter theme: white rounded cards on a slate-grey canvas, a white
header bar with an accent icon block, a left settings column, a right tabbed
column with a persistent coloured log, and a configuration bar at the bottom.

All settings are editable in the window; no command line is needed. Two output
modes are supported (structured table / text list with coordinates). Long work
runs on a worker thread and results come back through a queue.

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
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError as exc:  # pragma: no cover - depends on local install
    raise SystemExit(
        "customtkinter not installed. Run: pip install -r requirements.txt"
    ) from exc

from src.config_io import (ENGINES, EXAMPLE_PATH, LOCAL_PATH, TYPES,
                           example_config, load_config, normalize,
                           save_config, validate)
from src.dump import run_text_dump
from src.pipeline import run, run_demo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "samples")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "report.xlsx")
DEMO_OUTPUT = os.path.join(HERE, "output", "demo_report.xlsx")

# ---- shared light-card palette -------------------------------------------
BG = "#f5f7fa"
BG_HEADER = "#ffffff"
BG_CARD = "#ffffff"
BG_INPUT = "#e2e8f0"
BG_BTN = "#eef1f5"
BG_BTN_HOVER = "#dfe4ea"
BG_LOG = "#f8fafc"
ACCENT = "#3b82f6"
ACCENT_DIM = "#2563eb"
TEXT = "#475569"
TEXT_DIM = "#94a3b8"
TEXT_BRIGHT = "#0f172a"
SUCCESS = "#10b981"
ORANGE = "#f59e0b"
DANGER = "#ef4444"
PURPLE = "#8b5cf6"

MODE_LABELS = ("表格提取", "文本清单")
MODE_TO_VALUE = {"表格提取": "table", "文本清单": "text_dump"}
VALUE_TO_MODE = {value: label for label, value in MODE_TO_VALUE.items()}


class App:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.running = False
        self.columns = []
        self.selected_column_index = None

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        root.title("截图转 Excel 报表工具")
        root.geometry("1100x740")
        root.minsize(1000, 660)
        root.configure(fg_color=BG)

        def font(size=12, bold=False):
            return ctk.CTkFont(family="Microsoft YaHei", size=size,
                               weight="bold" if bold else "normal")

        self.f = font
        self._build()
        initial = LOCAL_PATH if os.path.isfile(LOCAL_PATH) else EXAMPLE_PATH
        try:
            self._load_config(initial, initial=True)
        except Exception as exc:
            self._apply_config(example_config())
            self._append(f"[警告] 配置加载失败，已恢复示例：{exc}", "warn")
        self._refresh_status()
        self.root.after(120, self._poll)

    # ------------------------------------------------------------- helpers
    def _card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10, **kwargs)

    def _label(self, parent, text, size=12, bold=False, color=TEXT, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=self.f(size, bold),
                            text_color=color, **kwargs)

    def _button(self, parent, text, command, width=88, primary=False, **kwargs):
        if primary:
            return ctk.CTkButton(parent, text=text, command=command, width=width,
                                 height=38, corner_radius=10, font=self.f(12, True),
                                 fg_color=ACCENT, hover_color=ACCENT_DIM,
                                 text_color="#ffffff", **kwargs)
        return ctk.CTkButton(parent, text=text, command=command, width=width,
                             height=30, corner_radius=8, font=self.f(11),
                             fg_color=BG_BTN, hover_color=BG_BTN_HOVER,
                             text_color=TEXT, **kwargs)

    def _entry(self, parent, var, width=240):
        return ctk.CTkEntry(parent, textvariable=var, width=width, height=32,
                            corner_radius=8, fg_color=BG_INPUT, border_width=0,
                            text_color=TEXT_BRIGHT, font=self.f(11))

    # -------------------------------------------------------------- layout
    def _build(self):
        header = ctk.CTkFrame(self.root, fg_color=BG_HEADER, height=62,
                              corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=16)
        icon = ctk.CTkFrame(left, fg_color=ACCENT, width=38, height=38,
                            corner_radius=10)
        icon.pack(side="left", padx=(0, 12))
        icon.pack_propagate(False)
        self._label(icon, "OCR", 13, True, "#ffffff").place(relx=0.5, rely=0.5,
                                                            anchor="center")
        titles = ctk.CTkFrame(left, fg_color="transparent")
        titles.pack(side="left")
        self._label(titles, "截图转 Excel 报表工具", 16, True, TEXT_BRIGHT).pack(anchor="w")
        self._label(titles, "OCR 识别 · 表格提取 / 文本清单", 11, False, TEXT_DIM).pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=16)
        self._button(right, "检查环境", self._check_env, width=96).pack(side="right", padx=(8, 0))
        self.header_badge = self._label(right, "● 就绪", 11, True, SUCCESS)
        self.header_badge.pack(side="right", padx=8)

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=10)

        self._build_left(body)
        splitter = ctk.CTkFrame(body, fg_color=BG_BTN_HOVER, width=4,
                                corner_radius=2)
        splitter.pack(side="left", fill="y", padx=8)
        self._build_right(body)

        self._build_config_bar()
        self._build_status_bar()

    def _build_left(self, parent):
        column = ctk.CTkFrame(parent, fg_color="transparent", width=420)
        column.pack(side="left", fill="y")
        column.pack_propagate(False)

        run_card = self._card(column)
        run_card.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(run_card, fg_color="transparent")
        inner.pack(fill="both", padx=16, pady=14)
        inner.columnconfigure(1, weight=1)

        self._label(inner, "运行设置", 14, True, TEXT_BRIGHT).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        self.input_var = tk.StringVar(value=DEFAULT_INPUT)
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)
        self.mode_var = tk.StringVar(value="表格提取")
        self.dedup_var = tk.StringVar(value="12")
        self.demo_var = tk.BooleanVar(value=False)

        self._form_row(inner, 1, "图片文件夹", self.input_var, self._pick_input)
        self._form_row(inner, 2, "输出 xlsx", self.output_var, self._pick_output)

        self._label(inner, "输出模式", 11, False, TEXT).grid(
            row=3, column=0, sticky="w", pady=7)
        ctk.CTkOptionMenu(inner, variable=self.mode_var, values=MODE_LABELS,
                          width=240, height=32, corner_radius=8,
                          fg_color=BG_INPUT, button_color=BG_BTN_HOVER,
                          button_hover_color=BG_BTN_HOVER,
                          text_color=TEXT_BRIGHT, font=self.f(11),
                          command=lambda _v: self._refresh_status()).grid(
            row=3, column=1, sticky="w", pady=7)
        self._label(inner, "表格=按列成表 · 清单=文字+坐标", 10, False, TEXT_DIM).grid(
            row=4, column=1, columnspan=2, sticky="w")

        self._label(inner, "去重网格(px)", 11, False, TEXT).grid(
            row=5, column=0, sticky="w", pady=(10, 7))
        self._entry(inner, self.dedup_var, width=110).grid(
            row=5, column=1, sticky="w", pady=(10, 7))
        self._label(inner, "仅文本清单模式生效", 10, False, TEXT_DIM).grid(
            row=5, column=2, sticky="w", padx=8)

        ctk.CTkCheckBox(inner, text="演示模式（合成数据，忽略引擎与输出模式）",
                        variable=self.demo_var, font=self.f(11), text_color=TEXT,
                        fg_color=ACCENT, hover_color=ACCENT_DIM,
                        corner_radius=6).grid(row=6, column=0, columnspan=3,
                                              sticky="w", pady=(14, 12))

        self.start_btn = self._button(inner, "▶  开始处理", self._start,
                                      width=200, primary=True)
        self.start_btn.grid(row=7, column=0, columnspan=3, sticky="w")

        status_card = self._card(column)
        status_card.pack(fill="x")
        s = ctk.CTkFrame(status_card, fg_color="transparent")
        s.pack(fill="both", padx=16, pady=14)
        self._label(s, "当前状态", 13, True, TEXT_BRIGHT).pack(anchor="w")
        self.status_line = self._label(s, "就绪", 12, False, TEXT)
        self.status_line.pack(anchor="w", pady=(8, 2))
        self.mode_line = self._label(s, "", 11, False, TEXT_DIM)
        self.mode_line.pack(anchor="w")
        self.engine_line = self._label(s, "", 11, False, TEXT_DIM)
        self.engine_line.pack(anchor="w")

    def _form_row(self, parent, row, label, var, command):
        self._label(parent, label, 11, False, TEXT).grid(
            row=row, column=0, sticky="w", pady=7)
        self._entry(parent, var, width=240).grid(
            row=row, column=1, sticky="w", pady=7)
        self._button(parent, "浏览…", command, width=64).grid(
            row=row, column=2, sticky="w", padx=6)

    def _build_right(self, parent):
        column = ctk.CTkFrame(parent, fg_color="transparent")
        column.pack(side="left", fill="both", expand=True)

        tabs = ctk.CTkTabview(
            column, fg_color=BG_CARD, corner_radius=10,
            segmented_button_fg_color=BG_BTN,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_DIM,
            segmented_button_unselected_color=BG_BTN,
            segmented_button_unselected_hover_color=BG_BTN_HOVER,
            text_color=TEXT_BRIGHT)
        tabs.pack(fill="both", expand=True, pady=(0, 10))
        tab_ocr = tabs.add("  识别参数  ")
        tab_cols = tabs.add("  列定义  ")
        self._build_ocr_tab(tab_ocr)
        self._build_columns_tab(tab_cols)

        log_card = self._card(column, height=230)
        log_card.pack(fill="x")
        log_card.pack_propagate(False)
        head = ctk.CTkFrame(log_card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        self._label(head, "运行日志", 13, True, TEXT_BRIGHT).pack(side="left")
        self._button(head, "清空", lambda: self._clear_log(), width=56).pack(side="right")

        self.log_text = ctk.CTkTextbox(
            log_card, fg_color=BG_LOG, text_color=TEXT, corner_radius=8,
            font=self.f(11), activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_text.configure(state="disabled")
        for tag, color in (("ok", SUCCESS), ("err", DANGER), ("warn", ORANGE),
                           ("cfg", ACCENT_DIM), ("dim", TEXT_DIM),
                           ("data", PURPLE)):
            self.log_text.tag_config(tag, foreground=color)

    def _build_ocr_tab(self, parent):
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

        row = 0
        self._label(parent, "OCR 引擎", 11, False, TEXT).grid(
            row=row, column=0, sticky="w", padx=(14, 8), pady=6)
        ctk.CTkComboBox(parent, variable=self.engine_var, values=list(ENGINES),
                        state="readonly", width=180, height=32, corner_radius=8,
                        fg_color=BG_INPUT, border_width=0, button_color=BG_BTN_HOVER,
                        text_color=TEXT_BRIGHT, font=self.f(11)).grid(
            row=row, column=1, sticky="w", pady=6)
        self._label(parent, "dummy = 合成数据", 10, False, ORANGE).grid(
            row=row, column=2, sticky="w", padx=8)
        row += 1

        for label, var, hint, width in (
            ("扫描尺度", self.scales_var, "如 1,2,3；小图建议 2,3", 180),
            ("识别分数下限", self.min_score_var, "低于此分数的识别框丢弃", 180),
            ("行聚类容差", self.row_tol_var, "表格模式：行间距中位数 × 系数", 110),
            ("列聚类容差", self.col_tol_var, "表格模式：框宽中位数 × 系数", 110),
            ("低置信阈值", self.low_conf_var, "低于此值标黄", 110),
        ):
            self._label(parent, label, 11, False, TEXT).grid(
                row=row, column=0, sticky="w", padx=(14, 8), pady=5)
            self._entry(parent, var, width=width).grid(row=row, column=1, sticky="w", pady=5)
            self._label(parent, hint, 10, False, TEXT_DIM).grid(
                row=row, column=2, sticky="w", padx=8)
            row += 1

        self._label(parent, "模块目录", 11, False, TEXT).grid(
            row=row, column=0, sticky="w", padx=(14, 8), pady=5)
        self._entry(parent, self.module_dir_var, width=250).grid(
            row=row, column=1, sticky="w", pady=5)
        self._button(parent, "浏览…", self._pick_module_dir, width=64).grid(
            row=row, column=2, sticky="w", padx=8)
        row += 1
        self._label(parent, "模型目录", 11, False, TEXT).grid(
            row=row, column=0, sticky="w", padx=(14, 8), pady=5)
        self._entry(parent, self.model_dir_var, width=250).grid(
            row=row, column=1, sticky="w", pady=5)
        self._button(parent, "浏览…", self._pick_model_dir, width=64).grid(
            row=row, column=2, sticky="w", padx=8)
        row += 1

        switches = ctk.CTkFrame(parent, fg_color="transparent")
        switches.grid(row=row, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 4))
        ctk.CTkCheckBox(switches, text="去除表情符号", variable=self.strip_emoji_var,
                        font=self.f(11), text_color=TEXT, fg_color=ACCENT,
                        hover_color=ACCENT_DIM, corner_radius=6).pack(side="left", padx=(0, 18))
        ctk.CTkCheckBox(switches, text="全角转半角", variable=self.fullwidth_var,
                        font=self.f(11), text_color=TEXT, fg_color=ACCENT,
                        hover_color=ACCENT_DIM, corner_radius=6).pack(side="left")
        row += 1
        self._label(parent, "maaocr 路径在界面里填写即可，不需要命令行；不要提交到仓库",
                    10, False, TEXT_DIM).grid(row=row, column=0, columnspan=3,
                                              sticky="w", padx=14, pady=(4, 10))

    def _build_columns_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(8, 6))
        self._label(top, "仅「表格提取」模式需要；顺序即 Excel 列顺序",
                    11, False, TEXT_DIM).pack(side="left")
        self._button(top, "+ 新增列", self._add_column, width=88).pack(side="right")

        self.columns_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=BG_BTN_HOVER,
            scrollbar_button_hover_color=BG_INPUT)
        self.columns_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _build_config_bar(self):
        bar = self._card(self.root)
        bar.pack(fill="x", padx=12, pady=(0, 6))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        self._label(inner, "配置文件", 11, True, TEXT).pack(side="left", padx=(0, 8))
        self.config_path_var = tk.StringVar(value=EXAMPLE_PATH)
        path_entry = ctk.CTkEntry(inner, textvariable=self.config_path_var,
                                  height=30, corner_radius=8, fg_color=BG_INPUT,
                                  border_width=0, text_color=TEXT_BRIGHT,
                                  font=self.f(11))
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        for text, command in (("浏览", self._browse_config),
                              ("加载", lambda: self._load_config()),
                              ("保存", lambda: self._save_config(False)),
                              ("另存为", lambda: self._save_config(True)),
                              ("恢复示例", self._restore_example)):
            self._button(inner, text, command, width=72).pack(side="left", padx=3)

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color=BG_HEADER, height=28, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status_bar = self._label(bar, "就绪", 10, False, TEXT_DIM)
        self.status_bar.pack(side="left", padx=16)
        self._label(bar, "customtkinter · light", 10, False, TEXT_DIM).pack(side="right", padx=16)

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

    # ---------------------------------------------------------- columns UI
    def _refresh_columns(self):
        for child in self.columns_scroll.winfo_children():
            child.destroy()
        if not self.columns:
            self._label(self.columns_scroll, "暂无列定义，点右上「+ 新增列」",
                        11, False, TEXT_DIM).pack(anchor="w", pady=12, padx=6)
            return
        for index, column in enumerate(self.columns):
            row = ctk.CTkFrame(self.columns_scroll, fg_color=BG_LOG,
                               corner_radius=8)
            row.pack(fill="x", pady=3)
            row.columnconfigure(1, weight=1)
            chosen = self.selected_column_index == index
            dot = self._label(row, "●" if chosen else "○", 11, True,
                              ACCENT if chosen else TEXT_DIM)
            dot.grid(row=0, column=0, padx=(10, 6), pady=8)
            info = f"{column.get('name', '')}   ·   {column.get('type', 'str')}"
            if column.get("required"):
                info += "   ·   必填"
            pattern = column.get("pattern", "")
            if pattern:
                info += f"   ·   {pattern[:24]}"
            self._label(row, info, 11, False, TEXT_BRIGHT).grid(
                row=0, column=1, sticky="w", pady=8)
            for col, (text, command) in enumerate((
                ("编辑", lambda i=index: self._select_column(i, True)),
                ("删除", lambda i=index: self._select_column(i, False, "del")),
                ("↑", lambda i=index: self._select_column(i, False, "up")),
                ("↓", lambda i=index: self._select_column(i, False, "down")),
            ), start=2):
                self._button(row, text, command, width=44 if len(text) > 1 else 32).grid(
                    row=0, column=col, padx=2, pady=6)

    def _select_column(self, index, edit=False, action=None):
        self.selected_column_index = index
        if edit:
            self._refresh_columns()
            self._open_column_dialog(index)
            return
        if action == "del":
            if messagebox.askyesno("确认", f"删除列「{self.columns[index]['name']}」？"):
                self.columns.pop(index)
                self.selected_column_index = None
        elif action in ("up", "down"):
            target = index - 1 if action == "up" else index + 1
            if 0 <= target < len(self.columns):
                self.columns[index], self.columns[target] = \
                    self.columns[target], self.columns[index]
                self.selected_column_index = target
        self._refresh_columns()

    def _add_column(self):
        self._open_column_dialog(None)

    def _edit_column(self):
        index = self.selected_column_index
        if index is None:
            messagebox.showinfo("提示", "请先点选一列")
            return
        self._open_column_dialog(index)

    def _open_column_dialog(self, index):
        existing = self.columns[index] if index is not None else None
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("编辑列" if existing else "新增列")
        dialog.geometry("460x360")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=BG)

        name_var = tk.StringVar(value=(existing or {}).get("name", ""))
        type_var = tk.StringVar(value=(existing or {}).get("type", "str"))
        pattern_var = tk.StringVar(value=(existing or {}).get("pattern", ""))
        required_var = tk.BooleanVar(value=(existing or {}).get("required", False))
        index_var = tk.StringVar(value=str((existing or {}).get("index", "")))
        width_var = tk.StringVar(value=str((existing or {}).get("width", "")))

        card = self._card(dialog)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        card.columnconfigure(1, weight=1)
        self._label(card, "列定义", 14, True, TEXT_BRIGHT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for row, (label, var, widget) in enumerate((
            ("列名", name_var, "entry"), ("类型", type_var, "combo"),
            ("正则校验", pattern_var, "entry"),
            ("绑定位置 index", index_var, "entry"), ("列宽", width_var, "entry"),
        ), start=1):
            self._label(card, label, 11, False, TEXT).grid(
                row=row, column=0, sticky="w", padx=(12, 8), pady=6)
            if widget == "combo":
                ctk.CTkComboBox(card, variable=var, values=list(TYPES),
                                state="readonly", width=230, height=32,
                                corner_radius=8, fg_color=BG_INPUT,
                                border_width=0, text_color=TEXT_BRIGHT,
                                font=self.f(11)).grid(row=row, column=1, sticky="w", pady=6)
            else:
                self._entry(card, var, width=230).grid(row=row, column=1, sticky="w", pady=6)
        ctk.CTkCheckBox(card, text="必填（缺失时标黄）", variable=required_var,
                        font=self.f(11), text_color=TEXT, fg_color=ACCENT,
                        hover_color=ACCENT_DIM, corner_radius=6).grid(
            row=6, column=1, sticky="w", pady=8)

        def commit():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("输入有误", "列名不能为空", parent=dialog)
                return
            column = {"name": name, "type": type_var.get(),
                      "pattern": pattern_var.get(),
                      "required": bool(required_var.get())}
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

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=7, column=0, columnspan=2, pady=(10, 4))
        self._button(buttons, "确定", commit, width=90, primary=True).pack(side="left", padx=6)
        self._button(buttons, "取消", dialog.destroy, width=90).pack(side="left", padx=6)
        dialog.wait_window()

    def _delete_column(self):
        index = self.selected_column_index
        if index is None:
            return
        self._select_column(index, False, "del")

    def _move_column(self, delta):
        index = self.selected_column_index
        if index is None:
            return
        self._select_column(index, False, "up" if delta < 0 else "down")

    # ------------------------------------------------------------- config IO
    def _apply_config(self, cfg):
        cfg = normalize(cfg)
        ocr = cfg["ocr"]
        self.engine_var.set(ocr["engine"])
        self.scales_var.set(",".join(str(s) for s in ocr["scales"]))
        self.min_score_var.set(str(ocr["min_score"]))
        self.module_dir_var.set(ocr.get("module_dir", ""))
        self.model_dir_var.set(ocr.get("model_dir", ""))
        self.mode_var.set(VALUE_TO_MODE.get(cfg["output"]["mode"], "表格提取"))
        self.dedup_var.set(str(cfg["dump"]["dedup_grid"]))
        self.row_tol_var.set(str(cfg["row_tolerance_ratio"]))
        self.col_tol_var.set(str(cfg["col_tolerance_ratio"]))
        self.low_conf_var.set(str(cfg["low_confidence_threshold"]))
        self.strip_emoji_var.set(bool(cfg["strip_emoji"]))
        self.fullwidth_var.set(bool(cfg["normalize_fullwidth"]))
        self.columns = copy.deepcopy(cfg["columns"])
        self.selected_column_index = None
        self._refresh_columns()
        self._refresh_status()

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
            "output": {"mode": MODE_TO_VALUE.get(self.mode_var.get(), "table")},
            "dump": {"dedup_grid": self._number(self.dedup_var, "去重网格")},
            "row_tolerance_ratio": self._number(self.row_tol_var, "行聚类容差"),
            "col_tolerance_ratio": self._number(self.col_tol_var, "列聚类容差"),
            "low_confidence_threshold": self._number(self.low_conf_var, "低置信阈值"),
            "strip_emoji": bool(self.strip_emoji_var.get()),
            "normalize_fullwidth": bool(self.fullwidth_var.get()),
        })

    @staticmethod
    def _problems(cfg, ignore_columns=False):
        problems = [p for p in validate(cfg) if "模块目录" not in p]
        if ignore_columns:
            problems = [p for p in problems
                        if "列定义" not in p and "列名" not in p]
        return problems

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
        self._append(f"[配置] {'启动加载' if initial else '已加载'} {os.path.basename(path)}", "cfg")

    def _restore_example(self):
        self._apply_config(example_config())
        self.config_path_var.set(EXAMPLE_PATH)
        self._append("[配置] 已恢复示例（保存时会要求另存为）", "cfg")

    def _save_config(self, save_as):
        try:
            cfg = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc))
            return
        problems = self._problems(cfg, ignore_columns=True)
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
        self._append(f"[配置] 已保存 {path}", "cfg")

    # ---------------------------------------------------------------- actions
    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _append(self, text, tag=None):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag or "dim")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _refresh_status(self):
        try:
            cfg = self._collect_config()
        except ValueError:
            return
        mode = VALUE_TO_MODE.get(cfg["output"]["mode"], "表格提取")
        self.mode_line.configure(text=f"输出模式：{mode}  ·  尺度 {cfg['ocr']['scales']}")
        self.engine_line.configure(text=f"OCR 引擎：{cfg['ocr']['engine']}  ·  列数 {len(self.columns)}")

    def _check_env(self):
        lines = [f"Python: {sys.version.split()[0]}", f"工作目录: {HERE}"]
        for module, label in (("openpyxl", "openpyxl"), ("PIL", "Pillow"),
                              ("tkinter", "tkinter"), ("customtkinter", "customtkinter"),
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
        self._append("---- 环境检查 ----", "cfg")
        for line in lines:
            self._append(line, "data")
        self._set_status("环境检查完成", SUCCESS)

    def _set_status(self, text, color=TEXT):
        self.status_line.configure(text=text, text_color=color)
        self.status_bar.configure(text=text)
        badge = "● " + text
        self.header_badge.configure(text=badge, text_color=color)

    def _start(self):
        if self.running:
            return
        try:
            cfg = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc))
            return

        demo = bool(self.demo_var.get())
        text_dump_mode = cfg["output"]["mode"] == "text_dump"
        problems = self._problems(cfg, ignore_columns=text_dump_mode) if not demo else []
        if demo and not cfg["columns"]:
            problems = ["演示模式至少需要一列"]
        if problems:
            messagebox.showerror("设置有误", "\n".join(problems))
            return
        if not demo and cfg["ocr"]["engine"] == "dummy":
            if not messagebox.askyesno(
                    "确认",
                    "当前 OCR 引擎是 dummy，只会输出内置合成数据，不会识别你的图片。\n\n"
                    "请在「识别参数」页换成 maaocr 或 rapidocr。\n仍要继续吗？"):
                return

        if not demo and cfg["ocr"]["engine"] == "maaocr":
            os.environ["OCR_MODULE_DIR"] = cfg["ocr"]["module_dir"]
            if cfg["ocr"]["model_dir"]:
                os.environ["OCR_MODEL_DIR"] = cfg["ocr"]["model_dir"]
            else:
                os.environ.pop("OCR_MODEL_DIR", None)

        params = {"config": cfg, "demo": demo,
                  "input": self.input_var.get(), "output": self.output_var.get(),
                  "demo_output": DEMO_OUTPUT}
        self.running = True
        self.start_btn.configure(state="disabled", text="处理中…")
        self._set_status("处理中…", ORANGE)
        engine_label = "演示模式(dummy)" if demo else cfg["ocr"]["engine"]
        mode_label = "演示" if demo else VALUE_TO_MODE.get(cfg["output"]["mode"], "表格提取")
        self._append(f"开始处理… 引擎={engine_label} 模式={mode_label} "
                     f"尺度={cfg['ocr']['scales']}", "cfg")
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()

    def _worker(self, params):
        cfg = params["config"]
        try:
            if params["demo"]:
                output = params["demo_output"]
                stats = run_demo(output, cfg, cfg["ocr"]["scales"])
            elif cfg["output"]["mode"] == "text_dump":
                output = params["output"]
                stats = run_text_dump(params["input"], output, cfg,
                                      cfg["ocr"]["engine"], cfg["ocr"]["scales"],
                                      cfg["dump"]["dedup_grid"])
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
            self._append(("[完成] " if kind == "ok" else "[失败] ") + message,
                         "ok" if kind == "ok" else "err")
            self.running = False
            self.start_btn.configure(state="normal", text="▶  开始处理")
            self._set_status("完成" if kind == "ok" else "失败",
                             SUCCESS if kind == "ok" else DANGER)
            if kind == "error":
                messagebox.showerror("处理失败", message)
        self.root.after(120, self._poll)


def main():
    try:
        root = ctk.CTk()
        App(root)
        root.mainloop()
    except Exception:
        # pythonw.exe has no console, so persist startup errors for diagnosis.
        import traceback
        log_dir = os.path.join(HERE, "output")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "startup_error.log"), "w",
                  encoding="utf-8") as handle:
            traceback.print_exc(file=handle)
        raise


if __name__ == "__main__":
    main()
