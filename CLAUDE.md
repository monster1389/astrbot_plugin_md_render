# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AstrBot 插件，拦截 QQ 消息中的 markdown **代码块**和**表格**，渲染为图片/文件后替换到消息链。其余 markdown 元素原样穿过。

管道位置：`OnDecoratingResultEvent`（priority=1000），在 RespondStage 之前修改 `result.chain`。

## 常用命令

```bash
# 激活虚拟环境（所有操作必须在 .venv 内执行）
source .venv/bin/activate

# 代码检查
ruff check .

# 运行全部测试
pytest

# 运行单个测试文件/用例
pytest tests/test_xxx.py
pytest tests/test_xxx.py::test_func_name -v

# 安装依赖
pip install -r requirements.txt
```

## 环境约束

- **所有 Python 操作必须在 `.venv` 内执行**：`source .venv/bin/activate` 后再跑任何 python/pip/pytest/ruff 命令
- **禁止向系统 Python 安装包**：不得 `pip install` 到全局环境，subagent 也必须先 activate .venv
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
    │  解析 Plain 中的代码块/表格
    │  渲染为 Image(png) + File(txt)
    │  替换到 result.chain
    │  自然分段：以 Plain 为锚点，紧跟的非 Plain 归入同段
    │  最后一段留在 chain 给 RespondStage
    │
    ▼
RespondStage 发送最终 chain
```

### 配置中心

`render/utils.py` — `RenderConfig` dataclass + 四个工具函数：
- `load_config(raw)` — 从 AstrBot 配置字典构造配置对象
- `parse_color(value)` — 提取纯 hex 颜色
- `find_font_path()` — 发现可用中文字体
- `build_temp_path(data_dir, prefix, ext)` — 在 temp/ 下建带时间戳的文件路径

### 渲染类型

| 输入 | 输出 | 工具 |
|------|------|------|
| ` ```lang ... ``` ` | Image(png) + 可选 File(.txt) | pygments → pillow |
| `\| 表头 \| ...` | Image(png) | matplotlib.table |
| — | 临时文件清理 | `render/cleaner.py` — 周期性扫描 temp/，按配置存活时长删过期文件 |

### 关键 API

- `StarTools.get_data_dir("astrbot_plugin_md_render")` — 获取插件数据目录，临时文件放 `temp/` 子目录
- `event.get_result().chain` — 获取/修改消息链
- `@filter.on_decorating_result(priority=1000)` — 注册装饰结果事件

### 依赖（已在环境内，零新增）

`pygments`, `pillow`, `matplotlib`, `markdown-it-py`

### 配置

通过 AstrBot 内置配置系统，`_conf_schema.json` 提供下拉菜单：
- 代码块：不处理 / 渲染图像 / 渲染且保留原文 / 渲染且txt
- 表格：不处理 / 渲染图像 / 渲染且保留原文
- 临时文件存活时间（分钟）：0=即时删除，-1=永久保留

### 设计文档

完整设计见 `docs/designs/md_render_plugin_final.md`。
