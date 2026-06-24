# Markdown 渲染插件设计文档

## 一句话描述

拦截 QQ 消息中 markdown 的 **代码块** 和 **表格**，渲染为图片/文件，原样替换到消息链。其余一概不碰。

---

## 边界（做什么 / 不做什么）

### 做什么

| 元素 | 输入 | 输出 | 方式 |
|------|------|------|------|
| 代码块 | ` ```lang ... ``` ` | Image(PNG) + File(.txt) | pygments → pillow |
| 表格 | `\| 表头 \| ...` | Image(PNG) | matplotlib.table |
| 表达式 | `$...$` / `$$...$$` | Image(PNG) | pillowlatex |
| 分隔线 | `---` | 切分点 | 断开 chain |

代码块双发：图可预览，txt 可下载复制。

### 不做什么

- ❌ 不做文字切分 — 只在渲染点/分隔线处断开 chain，不按句号/长度/换行切字
- ❌ 不清洗 markdown 标签 — `#` `**` `>` 原样穿过
- ❌ 不碰正文格式 — 非代码块/表格的任意文本不动

---

## 技术路线

### 管道位置

```
Process (LLM/Star生成消息)
         │
         ▼
ResultDecorateStage
    ├── OnDecoratingResultEvent ← 【本插件】priority=1000
    │                                  代码块/表格/表达式 → png → 替换 chain
         │
         ▼
RespondStage 发送最终 chain
```

### 代码块识别：行内 ``` 不会被误判

本插件在解析 markdown 时会遵循同样的原则——``` 只在行首或换行后行首才被视为代码块分隔符。避免类似「颜文字请用 ``` 包裹」这种行内文本被误判。

### 渲染引擎（已确认）

| 元素 | 引擎 | 验证 |
|------|------|------|
| 表达式 | pillowlatex | 矩阵/分段/组合/装饰/上下标全部通过 |
| 表格 | matplotlib.table | 中文（文泉驿微米黑）+ 符号 ✅ |
| 代码块 | pygments + pillow | Python/Bash material 主题 ✅ |

所有引擎纯 Python，零浏览器依赖，毫秒级渲染。

### 新增依赖

`pillowlatex`（已在环境，随 pillowmd 安装）。其余 `pygments` `pillow` `matplotlib` `markdown-it-py` 均已有。

## 自然分段（默认行为）

渲染完成后，chain 在渲染替换点自然断开。不需要额外切分逻辑。

```
原始 Plain: "看这段:
```python
def f():pass
```
|A|B|
|---|---|
结束"
               │
               ▼ 渲染替换
[
  Plain("看这段:
"),
  Image("code.png"), File("code.txt"),   ← 代码块→ Image+File
  Plain("
"),
  Image("table.png"),                    ← 表格→ Image
  Plain("
结束")
]
               │
               ▼ 自然分段：以 Plain 为锚点，紧跟的非 Plain 组件归入同段
发送段1: Plain("看这段:
") + Image("code.png") + File("code.txt")
发送段2: Plain("
") + Image("table.png")
链末段:  Plain("
结束")  → 留给 RespondStage
```

每段以 Plain 起始，其后紧跟的 Image/File 视为同段附属。段之间在 Plain 边界切开，仅此而已——不做长度阈值、不做句号/换行断句。最后一段留在 `result.chain` 交给 RespondStage 发送。

---

## 插件形态

- AstrBot Star Plugin
- 注册 `@filter.on_decorating_result(priority=1000)`
- 入口：`on_decorating_result(event: AstrMessageEvent)`
- 修改 `event.get_result().chain`，替换 Plain 中的代码块/表格为 Image + File
- 代码路径：`/AstrBot/data/plugins/astrbot_plugin_md_render/main.py`

---

## 配置设计

每种 markdown 元素独立下拉菜单，`_conf_schema.json` 结构：

```json
{
  "代码块": {
    "type": "select", "label": "代码块处理",
    "options": ["不处理", "渲染图像", "渲染且保留原文", "渲染且txt"],
    "default": "渲染且txt"
  },
  "表格": {
    "type": "select", "label": "表格处理",
    "options": ["不处理", "渲染图像", "渲染且保留原文"],
    "default": "渲染图像"
  },
  "表达式": {
    "type": "select", "label": "数学表达式处理",
    "options": ["不处理", "渲染图像", "渲染且保留原文"],
    "default": "渲染图像"
  },
  "分隔线": {
    "type": "select", "label": "分隔线 --- 处理",
    "options": ["不处理", "切分"],
    "default": "不处理"
  },
  "临时文件存活": {
    "type": "number", "label": "临时文件存活时间（分钟）",
    "default": 5,
    "description": "0=即时删除, -1=永久保留"
  }
}
```

### 各模式在消息链中的行为

| 模式 | 代码块 | 表格 | 表达式 | 分隔线 |
|------|--------|------|--------|--------|
| 不处理 | 原样 Plain | 原样 Plain | 原样 Plain | 原样 Plain |
| 渲染图像 | → Image(png) | → Image(png) | → Image(png) | — |
| 渲染且保留原文 | Image 插原文后 | Image 插原文后 | Image 插原文后 | — |
| 渲染且txt | → Image + File(.txt) | — | — | — |
| 切分 | — | — | — | `---` 处断 chain |

### 字形回退映射

每种元素渲染前，先检测目标字体对每个字符的字形覆盖。若缺失，则查映射表找替代字符。

```json
"字形映射": {
  "type": "object",
  "label": "缺失字形替代映射",
  "default": {
    "✗": "✕",
    "✓": "✔",
    "—": "-",
    "–": "-",
    "…": "...",
    "　": " "
  }
}
```

原理：`PIL.ImageFont.getmask(char)` 判字形是否存在，不存在则按映射表替换；映射表无匹配则保留原字符（可能显示为豆腐块）。映射表可在配置中扩展。

### Chain 变换示例

```
原始: Plain("看:
```python
def f():pass
```
|A|B|
|---|---|
完")
         │
         ▼ 渲染图像 (表格) + 渲染且txt (代码块)
[
  Plain("看:
"),
  Image("code.png"),    ← 替换代码块
  File("code.txt"),     ← txt 可复制，紧跟 Image
  Image("table.png"),   ← 替换表格
  Plain("
完")
]

         ▼ 渲染且保留原文 (代码块)
[
  Plain("看:
```python
def f():pass
```"),
  Image("code.png"),    ← 插在原文后面
  Plain("
完")
]
```

文件位置：图/文本均紧贴原位置插入，不改变消息流的先后顺序。


## 待定

- [ ] pygments theme 调优（material 或自定义深色，与天气图风格对齐）
- [ ] matplotlib table 间距/边框粗细调优
- [ ] 代码块图片宽度/padding 调优
- [ ] ` ``` ` 只认行首的实现方式（markdown-it-py 或手写正则）
- [ ] 字形回退映射的初始化检测逻辑（`getmask` + 默认映射表加载）

---

## 数据目录

渲染文件存放在 AstrBot 标准数据目录下：

```
plugin_data/astrbot_plugin_md_render/
└── temp/
    ├── code_20260623_230500.png
    ├── code_20260623_230500.txt
    ├── table_20260623_230500.png
    └── expr_20260623_230502.png
```

路径通过 `StarTools.get_data_dir("astrbot_plugin_md_render") + "/temp/"` 获取。临时文件命名格式：`{类型}_{yyyyMMdd_HHmmss}.{png|txt}`。存活时间由「临时文件存活」配置控制：0=发送后即刻删除、-1=永久保留、正数=到期清理（分钟）。
