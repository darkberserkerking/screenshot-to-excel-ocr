# engines/ — 自定义 OCR 引擎与本地模型

这个目录用于**放置你自己的 OCR 引擎和模型文件**。它随程序运行被自动扫描，
不需要改动主程序，也不需要重新安装。目录里的实际文件不会被提交到仓库。

## 1. 添加任意自定义引擎（插件）

放两个文件：

```
engines/
├── my_ocr.py       # 你的实现
└── my_ocr.json     # 声明文件
```

`my_ocr.json`：

```json
{
  "name": "my_ocr",
  "module": "my_ocr.py",
  "class": "MyOCR",
  "kwargs": {"model_dir": "models/my"},
  "description": "我的自定义引擎"
}
```

| 字段 | 说明 |
| --- | --- |
| `name` | 引擎名，会出现在界面的引擎下拉里；不要与内置名 `dummy` / `rapidocr` / `maaocr` 重复 |
| `module` | 相对本目录的 `.py` 文件路径 |
| `class` | 类名，缺省 `Engine` |
| `kwargs` | 传给构造函数的参数，缺省 `{}` |
| `description` | 界面里显示的说明，可选 |

`my_ocr.py` 只需暴露一个带 `recognize()` 的类：

```python
class MyOCR:
    def __init__(self, **kwargs):
        ...                      # 加载你的模型

    def recognize(self, image):  # image 是 PIL.Image
        # 返回 [(text, box, score), ...]，box 为 4 个角点或 (x1,y1,x2,y2)
        return [("示例", [(10, 10), (80, 10), (80, 30), (10, 30)], 0.99)]
```

也兼容 `(box, text, score)` 和 `{"text":..., "box":..., "score":...}` 三种返回格式，
由 `src/ocr/base.py` 的 `parse_raw()` 统一转换。程序会按扫描尺度自动做坐标归一化、去重和投票。

可复制 `engines/_template.json.example` 与 `engines/_template.py.example` 改名使用。
启动程序后，新引擎会自动出现在「识别参数」页的下拉里；「检查环境」会列出所有已发现的引擎。

## 2. 让 maaocr 引擎自动发现本地模块

按下面结构放好，界面里的「模块目录 / 模型目录」**留空即可**：

```
engines/
└── maaocr/
    ├── maa_ocr.py
    └── model/
        └── ocr/
            ├── det.onnx
            ├── rec.onnx
            └── keys.txt
```

程序按以下顺序查找：环境变量 `OCR_MODULE_DIR` / `OCR_MODEL_DIR` → 界面填写的路径 →
上面的 `engines/maaocr/` → `<模块目录>/model/ocr/`。

> 该模块与模型权重由使用者自行提供，**不随本仓库或可执行程序分发**；请自行确认
> 你对这些文件拥有使用权，并遵守其原始许可。仓库内只保留中性接口与适配器。

## 3. 目录可见性

`.gitignore` 排除了 `engines/` 下除本说明、`.gitkeep` 和 `*.example` 模板之外的所有文件，
所以你放入的引擎代码、模型权重、配置都不会被提交。
