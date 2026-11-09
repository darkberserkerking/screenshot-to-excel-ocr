# screenshot-to-excel-ocr

把截图 / 扫描件里的表格数据，批量提取成结构化 Excel 报表。

一个面向 Windows / macOS / Linux 的小工具链：输入一批图片，输出一份列顺序固定、
低置信度自动标黄、可直接人工复核的 `.xlsx`。OCR 引擎是可插拔的，核心流程不依赖
任何模型文件，`clone` 之后即可跑通完整链路。

---

## 特性

- **多尺度扫描 + 跨尺度投票**：整图按 1x / 2x / 3x 扫描，坐标归一化回原图后按行、按列聚类，同一单元格的文本按「出现票数优先、其次平均置信度」投票，抑制单尺度的误识别。
- **配置驱动**：列名、类型、正则校验、是否必填、列宽全部写在 JSON 里，换一种表格不用改代码。
- **复核友好**：置信度低或校验未通过的单元格标黄，鼠标悬停可看 OCR 原文；另附「运行说明」sheet 记录参数与统计。
- **引擎可插拔**：内置 `dummy`（零依赖）、可选 `rapidocr`（pip 即装）、可选 `maaocr`（自带模块与模型，环境变量注入路径）。
- **可交付**：单文件 CLI，支持 PyInstaller 打包为免环境安装的 exe。

> 为什么不逐行裁剪小图再识别：不少检测型 OCR 会对短边低于固定阈值的输入做强制等比拉伸，一行 20px 高的文字条会被拉到严重变形，检测反而全挂。整图多尺度 + 坐标投票是更稳的做法。

## 快速开始

```bash
pip install -r requirements.txt
python cli.py --demo
# -> output/demo_report.xlsx  (合成数据，零模型依赖，用于验证链路)
```

处理真实图片：

```bash
pip install -r requirements-ocr.txt
python cli.py --input ./samples --output ./output/report.xlsx \
              --config config.example.json --engine rapidocr
```

图形界面（基于 Python 标准库 tkinter，无需额外依赖）：

```bash
python gui.py
```

界面里可以选择图片文件夹、配置文件、输出路径、OCR 引擎与扫描尺度；勾选「演示模式」即可零素材跑通全流程。耗时任务在后台线程执行，结果通过队列回到主线程刷新日志，窗口不会卡死。

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--input` | 图片文件夹，支持 png / jpg / jpeg / bmp / webp / tif |
| `--output` | 输出 xlsx 路径 |
| `--config` | 列定义与规则，默认 `config.example.json` |
| `--engine` | `dummy` / `rapidocr` / `maaocr`，覆盖配置里的值 |
| `--scales` | 扫描尺度，如 `1,2,3` |
| `--demo` | 用内置合成数据跑全流程，不需要任何图片或 OCR 模型 |

## 处理流程

```mermaid
flowchart LR
    A[图片批量输入] --> B[整图多尺度扫描]
    B --> C[OCR 引擎<br/>可插拔]
    C --> D[坐标归一化<br/>除以 scale]
    D --> E[按 y 聚类成行<br/>按 x 聚类成单元格]
    E --> F[跨尺度投票<br/>票数 + 平均置信度]
    F --> G[配置驱动清洗<br/>类型 / 正则 / 必填]
    G --> H[Excel 导出<br/>低置信标黄 + 原文批注]
```

各阶段都是独立模块，可单独替换或复用：

```
根目录另有：`cli.py`（命令行入口）、`gui.py`（Tkinter 图形界面）、`config.example.json`（列定义）、`tests/`（单元测试）

src/
├── models.py       数据容器（OCRItem / Cell / FieldResult / RowRecord）
├── preprocess.py   图片载入、整图多尺度
├── ocr/            后端注册表与三种实现（懒加载）
├── cluster.py      坐标归一化、行列聚类、投票
├── extract.py      清洗、类型转换、字段映射、复核标记
├── excel.py        报表写出
└── pipeline.py     编排与运行统计
```

## 配置说明

`config.example.json`：

| 键 | 含义 |
| --- | --- |
| `columns[].name` | 输出列名，决定 Excel 列顺序 |
| `columns[].type` | `str` / `int` / `float` / `date` |
| `columns[].pattern` | 正则校验；不匹配则标黄并把置信度减半 |
| `columns[].required` | 缺失时强制标黄 |
| `columns[].index` | 可选，把该列绑定到第几个聚类单元格；不填则按列顺序从左到右消费 |
| `columns[].width` | 可选，Excel 列宽 |
| `ocr.engine` / `ocr.scales` / `ocr.min_score` | 默认引擎、扫描尺度、识别分数下限 |
| `row_tolerance_ratio` | 行聚类容差 = 相邻框垂直间距中位数 × 该系数 |
| `low_confidence_threshold` | 低于此置信度标黄 |
| `strip_emoji` / `normalize_fullwidth` | 文本清洗开关 |

建议把本地实际使用的配置存成 `config.json`（已在 `.gitignore` 中），不要提交含路径或凭据的配置。

## 接入自己的 OCR 模块

`maaocr` 后端只约定接口，不绑定任何具体项目目录：

```bash
export OCR_MODULE_DIR=/path/to/dir/containing/maa_ocr.py
export OCR_MODEL_DIR=/path/to/ocr/model
python cli.py --engine maaocr --input ./samples
```

约定：模块暴露 `MaaOCR(model_dir=...)`，其 `recognize(image)` 返回
`(text, box, score)` 元组；传入的是 `PIL.Image` 对象而不是路径字符串。
`src/ocr/base.py` 里的 `parse_raw()` 兼容 `(text, box, score)`、
`(box, text, score)` 和字典三种返回格式，新增后端只需实现一个 `recognize()`。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试只依赖核心依赖，覆盖坐标归一化、多尺度投票纠错、文本清洗、类型转换、
Excel 写出与端到端 demo，不需要任何图片素材或 OCR 模型。

## 打包为可执行文件（可选）

```bash
pip install pyinstaller
pyinstaller --onefile --name screenshot-to-excel cli.py
```

交付给非技术使用者时，建议同时附上 `config.example.json`、一份「使用前必读」和
一张运行截图。

## 合规说明

- 仓库内不含任何第三方图片、模型权重、账号或凭据；`--demo` 使用的是合成数据。
- 使用者需自行确认输入数据的来源合法、且遵守数据来源方的相关条款。
- 识别结果仅供辅助整理，低置信度条目应以人工复核为准。

## License

[MIT](LICENSE)
