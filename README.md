# screenshot-to-excel-ocr

把截图里的文字提取成 Excel，支持两种输出模式：

- **表格提取**：适用于规整的行列表格，按你定义的列输出，低置信度自动标黄。
- **文本清单**：适用于应用界面截图这类**没有表格**的画面，输出每条识别文字及其在原图中的坐标，可直接用于 UI 元素定位。

**内置 RapidOCR**，安装后开箱即用，不用另装 OCR 包或填模型路径；同时保留 MaaOCR 风格适配器与**可自定义添加任意 OCR 引擎的插件接口**。所有设置都能在图形界面里完成，不需要命令行。

---

## 图形界面（推荐）

```bash
python gui.py
```

Windows 下也可以创建一个内容为 `python gui.py` 的 `.bat` 双击启动，或直接下载 Releases 里的单文件 exe。界面基于 **customtkinter 5.2**（已列在 `requirements.txt`），采用浅色卡片风格：`#f5f7fa` 灰蓝底、白色圆角卡片、`#3b82f6` 蓝主色、白色顶栏 + 蓝色图标块、彩色分级日志。

| 区域 | 内容 |
| --- | --- |
| **顶栏** | 蓝色图标块 + 标题 / 副标题、右侧「检查环境」和状态徽标 |
| **左列** | 「运行设置」卡片：图片文件夹、输出 xlsx、输出模式、去重网格、演示模式、主按钮；下方「当前状态」卡片显示引擎 / 模式 / 列数 |
| **右列** | 标签页「识别参数」（**引擎下拉会自动列出内置引擎与已发现插件**、尺度、分数下限、模块/模型目录、聚类容差、低置信阈值、文本清洗）与「列定义」；下方常驻「运行日志」卡片 |
| **底栏** | 配置文件路径 + 浏览 / 加载 / 保存 / 另存为 / 恢复示例；最底部状态栏 |

「检查环境」会列出所有可用引擎、依赖是否齐全，以及已发现的自定义插件。日志按类型着色（配置蓝、数据紫、警告橙、成功绿、失败红），可一键清空。

## OCR 引擎与插件

| 引擎 | 来源 | 说明 |
| --- | --- | --- |
| `dummy` | 内置 | 合成数据，仅用于演示与测试，不识别图片 |
| `rapidocr` | **内置**（默认） | RapidOCR 1.4 / ONNX Runtime，Apache-2.0，pip 包自带模型权重，随 exe 一起分发，开箱即用 |
| `maaocr` | 内置适配器 | 运行时加载你提供的 `maa_ocr.py` 与模型权重，见下方自动发现 |
| 自定义名称 | 插件 | 在 `engines/` 放一个 `.py` + 一个 `.json` 声明，重启即出现在引擎下拉里 |

### 让 maaocr 自动发现本地模块

按下面结构放好，**界面里的「模块目录 / 模型目录」留空即可**：

```
<程序目录>/engines/maaocr/
├── maa_ocr.py
└── model/ocr/{det.onnx, rec.onnx, keys.txt}
```

查找顺序：环境变量 `OCR_MODULE_DIR` / `OCR_MODEL_DIR` → 界面填写的路径 → `engines/maaocr/` → `<模块目录>/model/ocr/`。

### 添加任意自定义引擎（插件接口）

在 `<程序目录>/engines/` 放两个文件（源码运行时即仓库根目录的 `engines/`）：

```json
// engines/my_ocr.json
{
  "name": "my_ocr",
  "module": "my_ocr.py",
  "class": "MyOCR",
  "kwargs": {"model_dir": "models/my"},
  "description": "我的自定义引擎"
}
```

```python
# engines/my_ocr.py
class MyOCR:
    def __init__(self, **kwargs):
        ...                       # 加载你的模型

    def recognize(self, image):   # image 是 PIL.Image
        return [("文本", [(10, 10), (90, 10), (90, 30), (10, 30)], 0.99)]
```

`recognize()` 兼容 `(text, box, score)`、`(box, text, score)`、字典三种格式，box 可为四个角点或 `(x1,y1,x2,y2)`；坐标归一化、多尺度投票、去重都由主程序接管。可复制 `engines/_template.py.example` 与 `engines/_template.json.example` 改名使用。详细约定见 [engines/README.md](engines/README.md)。

> 内置引擎之外，模块源码与模型权重均由使用者自行提供，**不随本仓库或可执行程序分发**；请自行确认对这些文件拥有使用权并遵守其原始许可。仓库只保留中性接口与适配器。

## 两种输出模式

**表格提取**假设截图里有一张行列表格：整图多尺度扫描 → 坐标归一化 → 按 y 聚类成行、按 x 聚类成单元格 → 跨尺度投票 → 按 `columns` 定义清洗与校验 → 写出 `.xlsx`。如果截图是应用界面、按钮和标题散落各处，这个模式会把文字聚成「伪行」，结果不可用，应改选文本清单。

**文本清单**不做列映射，直接报告每个识别框：

| 列 | 含义 |
| --- | --- |
| `来源文件` | 来自哪张截图 |
| `序号` | 按文件 → y → x（从上到下、从左到右）排序后的序号 |
| `识别文本` | OCR 结果 |
| `置信度` | 识别分数，低于「低置信阈值」时标黄 |
| `中心X` / `中心Y` | 文本框中心点，已归一化回原图尺寸 |
| `尺度` | 该结果来自哪个扫描尺度 |

多尺度产生的重复框按 `(文件, 文本, 网格化坐标)` 合并，只保留分数最高的一条；网格大小由「去重网格(px)」控制，默认 12。这个模式不要求定义列，适合做 UI 自动化里的文字定位与断言。

## 命令行（可选）

```bash
pip install -r requirements.txt
python cli.py --demo
python cli.py --input ./samples --output ./output/report.xlsx --scales 1,2,3
python cli.py --input ./samples --output ./output/text_dump.xlsx --mode text_dump
```

| 参数 | 说明 |
| --- | --- |
| `--input` | 图片文件夹，支持 png / jpg / jpeg / bmp / webp / tif |
| `--output` | 输出 xlsx 路径 |
| `--config` | 列定义与全部规则 |
| `--engine` | 内置引擎名或 `engines/` 里声明的插件名 |
| `--mode` | `table`（表格提取）/ `text_dump`（文本清单） |
| `--scales` | 扫描尺度，如 `1,2,3` |
| `--demo` | 内置合成数据，不需要图片或 OCR 模型 |

## 特性

- **内置 OCR + 插件接口**：RapidOCR 开箱即用，任意新引擎放两个文件即可接入，无需改主程序。
- **多尺度扫描 + 跨尺度投票**：整图按 1x / 2x / 3x 扫描，坐标归一化回原图后按行、按列聚类，同一单元格按「出现票数优先、其次平均置信度」投票。
- **双输出模式**：规整表格走结构化列，非表格界面走文字 + 坐标清单。
- **浅色卡片 UI**：customtkinter 分栏布局、圆角卡片、彩色分级日志、状态徽标。
- **配置驱动且可视化**：全部参数都能在界面里编辑并保存。
- **复核友好**：低置信度标黄；表格模式鼠标悬停可看 OCR 原文；两份输出都附「运行说明」sheet。

> 为什么不逐行裁剪小图再识别：不少检测型 OCR 会对短边低于固定阈值的输入做强制等比拉伸，一行 20px 高的文字条会被拉到严重变形。整图多尺度 + 坐标投票是更稳的做法。

## 处理流程

```mermaid
flowchart LR
    A[图片批量输入] --> B[整图多尺度扫描]
    B --> C[OCR 引擎<br/>内置 / 插件]
    C --> D[坐标归一化<br/>除以 scale]
    D --> E{输出模式}
    E -->|表格提取| F[按 y/x 聚类 + 投票]
    F --> G[配置驱动清洗<br/>类型 / 正则 / 必填]
    G --> H[Excel 表格<br/>低置信标黄]
    E -->|文本清单| I[按坐标网格去重]
    I --> J[Excel 清单<br/>文字 + 坐标 + 置信度]
```

```
根目录：gui.py（图形界面）、cli.py（命令行）、config.example.json、tests/、engines/
src/
├── config_io.py    配置加载 / 保存 / 校验
├── dump.py         文本清单模式：收集、去重、写出
├── models.py       数据容器
├── preprocess.py   图片载入、整图多尺度
├── ocr/
│   ├── base.py         统一接口与结果格式转换
│   ├── registry.py     内置引擎注册 + 插件发现/动态加载
│   ├── dummy.py        演示引擎
│   ├── rapidocr.py     内置 RapidOCR
│   └── maaocr.py       MaaOCR 风格适配器（自动发现）
├── cluster.py      坐标归一化、行列聚类、投票
├── extract.py      清洗、类型转换、字段映射
├── excel.py        表格模式报表写出
└── pipeline.py     编排与运行统计
```

## 配置说明

`config.example.json`（界面里的设置与之逐项对应）：

| 键 | 含义 |
| --- | --- |
| `columns[].name` / `type` / `pattern` / `required` / `index` / `width` | 表格提取模式的列定义 |
| `output.mode` | `table` / `text_dump` |
| `dump.dedup_grid` | 文本清单去重网格（像素），默认 12 |
| `ocr.engine` | 默认 `rapidocr`；可填内置名或插件名 |
| `ocr.scales` / `ocr.min_score` | 扫描尺度、识别分数下限 |
| `ocr.module_dir` / `ocr.model_dir` | 仅 maaocr 用，**留空即自动发现** `engines/maaocr/` |
| `row_tolerance_ratio` / `col_tolerance_ratio` | 行 / 列聚类容差系数 |
| `low_confidence_threshold` | 低于此置信度标黄 |
| `strip_emoji` / `normalize_fullwidth` | 文本清洗开关 |

本地配置存成 `config.json`（已在 `.gitignore` 中），不要提交含路径或凭据的配置。

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖坐标归一化、多尺度投票、文本清洗、配置往返与校验、双输出模式 Excel 写出、插件发现与动态加载、端到端 demo；不需要图片素材或外部模型。

## 打包与下载

已发布版本可直接从仓库 **Releases** 下载单文件 exe，双击即用，无需 Python 环境或命令行。配置文件 `config.json`、`engines/`、`output/` 都生成/放置在 exe 同目录。

从源码自行构建（Windows）：

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --clean --noconfirm \
  --name screenshot-to-excel --icon assets/icon.ico \
  --collect-all customtkinter --collect-data rapidocr_onnxruntime \
  --exclude-module matplotlib --exclude-module torch \
  --exclude-module torchvision --exclude-module onnxscript \
  --add-data "config.example.json;." \
  --add-data "engines/README.md;engines" \
  --hidden-import src.ocr.registry --hidden-import src.ocr.rapidocr gui.py
```

图标位于 `assets/icon.ico`：透明圆角蓝色卡片，含 16 / 32 / 48 / 64 / 128 / 256 六档尺寸；
`assets/icon.png` 是 256px 预览图。构建环境若装有 torch 等无关大包，需按上面示例排除，
否则单文件体积会异常膨胀。产物在 `dist/screenshot-to-excel.exe`，运行时没有控制台窗口。

## 合规说明

- 仓库内不含任何第三方图片、模型权重、账号或凭据；演示模式使用合成数据。内置 RapidOCR 为 Apache-2.0，其模型随 pip 包分发。
- `engines/` 下由使用者放入的引擎代码与模型不随仓库分发，版权与许可由提供者负责。
- 使用者需自行确认输入数据来源合法、遵守数据来源方的相关条款。
- 识别结果仅供辅助整理，低置信度条目应以人工复核为准。

## License

[MIT](LICENSE)
