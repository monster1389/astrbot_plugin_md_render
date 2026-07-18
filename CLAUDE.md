# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AstrBot 插件，拦截 QQ 消息中的 markdown **代码块**、**表格**和**数学表达式**，渲染为图片/文件后替换到消息链，并清洗剩余文本中的 markdown 格式标记（加粗、斜体、删除线等）。

管道位置：`OnDecoratingResultEvent`（priority=1000），在 RespondStage 之前修改 `result.chain`。

## 常用命令

```bash
# 所有命令用绝对路径直接调用 .venv 内的二进制，无需 source activate
# （避免审批步骤，一条命令完成）

# 代码检查
.venv/bin/ruff check .

# 运行全部测试
.venv/bin/pytest

# 运行单个测试文件/用例
.venv/bin/pytest tests/test_xxx.py
.venv/bin/pytest tests/test_xxx.py::test_func_name -v

# 安装依赖
.venv/bin/pip install -r requirements.txt
```

## 环境约束

- **所有 Python 操作必须走 `.venv` 内的二进制**：用 `.venv/bin/pytest`、`.venv/bin/ruff`、`.venv/bin/pip` 等绝对路径
- **禁止向系统 Python 安装包**：不得 `pip install` 到全局环境，subagent 也必须用 `.venv/bin/pip`
- **依赖已在 requirements.txt 声明**：新增依赖先加文件再 install

## 编码规范

- **无兜底**：错误直接暴露，不静默吞掉
- **无死代码、无冗余**：不写用不到的代码，高度复用、解耦
- **Docstring**：中文，Google Style（`"""一句话概述。\n\nArgs:\n    x: ...\nReturns:\n    ...\n"""`）
- **类型注解**：所有函数签名必须有完整类型注解
- **测试**：ruff 零告警 + pytest 覆盖核心逻辑
- **Superpowers 文档**：不提交到 git（已在 `.gitignore` 排除 `docs/superpowers/`）
- **Superpowers spec**：用中文写，写完自审后交出（自查：TBD/占位符、内部矛盾、范围过大、歧义表述）

## 架构

### 入口

`main.py` — AstrBot Star Plugin，类继承 `Star`，`@register` 注册。

### 插件生命周期

```
__init__(context) → initialize() → [事件处理] → terminate()
```

### 事件处理链

```
LLM/Star 生成消息
    │
    ▼
OnDecoratingResultEvent (priority=1000)  ← 本插件
    │  收集所有 Plain 文本，拼接后解析为 Segment 列表
    │  按配置模式将各 Segment 渲染为 Image(png) / File(.md) / Plain
    │  组装为新 chain，通过 result.chain = built 整链替换
    │
    ▼
RespondStage 发送最终 chain
```

### 配置中心

`render/utils.py` — `RenderConfig` dataclass + 四个工具函数：
- `load_config(raw)` — 从 AstrBot 配置字典构造配置对象
- `parse_color(value)` — 提取纯 hex 颜色
- `find_font_path(data_dir)` — 发现可用中文字体，优先使用捆绑的更纱等宽黑体
- `build_temp_path(data_dir, prefix, ext)` — 在 temp/ 下建带时间戳的文件路径

### 模块

| 模块 | 职责 |
|------|------|
| `render/parser.py` | markdown-it-py 解析，输出 CodeBlock/Table/InlineExpr/BlockExpr/Segment/Divider |
| `render/code.py` | pygments → pillow 渲染代码块，返回 PNG bytes + md 文本 |
| `render/table.py` | Pillow 手绘表格为 PNG bytes，支持格内加粗/斜体/删除线/行内代码/链接混排 |
| `render/expr.py` | pillowlatex 渲染 LaTeX 表达式（行内/块级），返回 PNG bytes |
| `render/chain.py` | async 并发组装，asyncio.gather 收集渲染结果，按原序构建消息链 |
| `render/clean/md_cleaner.py` | markdown-it-py token 遍历清洗 markdown 格式标记 |
| `render/clean/temp_cleaner.py` | 周期性扫描 temp/，按配置存活时长删过期临时文件 |
| `render/utils.py` | `RenderConfig` + `CleanConfig` dataclass + 配置加载/颜色解析/字体发现/临时路径 |

### 关键 API

- `StarTools.get_data_dir("astrbot_plugin_md_render")` — 获取插件数据目录，临时文件放 `temp/` 子目录
- `event.get_result().chain` — 获取/修改消息链
- `@filter.on_decorating_result(priority=1000)` — 注册装饰结果事件

### 依赖

`pygments`, `pillow`, `markdown-it-py`, `pillowlatex`, `py7zr`

### 配置

通过 AstrBot 内置配置系统，`_conf_schema.json` 提供嵌套配置块：

**渲染**（`raw["渲染"]`）：
- 代码块：不处理 / 渲染图像 / 渲染且保留原文 / 渲染且md文件 / 仅md文件
- 表格：不处理 / 渲染图像 / 渲染且保留原文 / 渲染且md文件 / 仅md文件
- 表达式：不处理 / 渲染图像 / 渲染且保留原文
- 分隔线：不处理 / 切分
- 字体颜色、背景颜色：多种预设
- 临时文件存活（分钟）：0=即时删除（默认），-1=永久保留

**清洗**（`raw["清洗"]`）：
- 加粗/斜体/删除线/行内代码/链接/标题/无序列表/有序列表/引用/图片：bool 开关，默认全部开启
- 清洗基于 markdown-it-py token 树，颜表情中的 `*` `_` `~` 不会被误杀

### 设计文档

历史设计文档见 `docs/designs/`（如存在），注意部分内容可能过时，以当前代码为准。
