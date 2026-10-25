# CLAUDE.md

AstrBot 插件：拦截 QQ 消息里的 markdown 代码块、HTML 文档、Mermaid 图表、表格与数学表达式，渲染成图片或文件后替换到消息链，并清洗剩余文本中的格式标记。管道位置 `OnDecoratingResultEvent`（priority=1000），在 RespondStage 之前改 `result.chain`。

## 文档分工（先读这段）

**只写机器查不出来的东西**：意图、约束、为什么这么做、查不到的操作步骤、词汇的裁决。
`ls`、`git log`、`requirements.txt`、`_conf_schema.json`、代码 docstring 能回答的，不写第二份。

| 文档 | 负责 | 该放 | 不该放 |
|---|---|---|---|
| `README.md` | 使用者视角 | 装法、AstrBot 侧前置设置、每种模式的语义、外发声明、字体放置步骤、一张职责层模块地图 | 逐文件职责表、内部类型、变更历史、测试 |
| `GLOSSARY.md` | 领域语言 | 本项目独有的名词与命名裁决（每条 1–2 句，带 `_Avoid_`） | 机制描述、类名、模块路径、计数、默认值 |
| `CLAUDE.md`（本文） | agent 守则与不变量 | 命令、环境约束、编码规范、不可违反的架构约束 | 模块目录树、逐文件职责表、依赖清单、版本号、测试数、变更流水 |
| `CHANGELOG.md` | 时间轴 | 对使用者有影响的行为、依赖、平台变化 | 现状描述——它本来就该腐烂 |
| `docs/fonts.md` | 查不到的操作步骤 | 字体从哪来、放哪、怎么验证 | 候选字体清单与 ttc face 序号 |
| `_conf_schema.json` | 配置的机器真相 | 默认值、可选值、UI 文案 | 语义解释 |
| 代码 docstring | 接口契约 | Args / Returns / Raises、不变量、一行“为什么” | 教程、历史、跨模块全景 |
| `docs/adr/` | 难逆 + 反直觉 + 真有取舍的决定 | 见文末 | 每次重构都写一条 |

## 操作

```bash
# 全部检查：ruff + pytest（pre-commit 跑同一份）
scripts/check.sh

# 新 clone 后启用 pre-commit（只需一次）
git config core.hooksPath .githooks

# 单个测试文件 / 单个用例
docker exec -w /AstrBot/data/plugins/astrbot_plugin_md_render astrbot python3 -m pytest tests/test_xxx.py
docker exec -w /AstrBot/data/plugins/astrbot_plugin_md_render astrbot python3 -m pytest tests/test_xxx.py::test_func_name -v

# 安装/更新依赖（容器内全局环境）
docker exec -w /AstrBot/data/plugins/astrbot_plugin_md_render astrbot python3 -m pip install -r requirements.txt

# 改动生效
docker restart astrbot
```

容器名 `astrbot`，容器内路径 `/AstrBot/data/plugins/astrbot_plugin_md_render` 与宿主机本目录 bind mount 同步。

**动手与提交的门槛**：改代码等「动手 / 可以 / 按默认」；`git commit` 等「提交」。讨论的产出留在回复里，跟着对话走。

## 环境约束

- **所有 Python 操作一律在 `astrbot` 容器内执行**：宿主机不建 .venv、不向宿主机/系统 Python 装包，subagent 同样如此
- **容器内即插件运行环境**：`pip install` 直接作用于容器全局，只装 `requirements.txt` 声明的依赖，不随意升降级已装包
- **新增依赖先写进 `requirements.txt` 再装**（`astrbot` 的传递依赖不算已声明）
- **代码/配置/依赖改动后重启容器**才生效

## 编码规范

- **无兜底**：错误直接暴露，不静默吞掉；唯一例外是架构不变量第 8 条（渲染失败降级为产物），且降级必须打日志
- **日志**：一律 `from astrbot.api import logger`，不用标准库 `logging.getLogger(__name__)`（插件市场审核要求）
- **无死代码、无冗余**：不写用不到的代码，高度复用、解耦
- **Docstring**：中文，Google Style（`"""一句话概述。\n\nArgs:\n    x: ...\nReturns:\n    ...\n"""`）
- **类型注解**：所有函数签名必须有完整类型注解
- **测试**：ruff 零告警 + pytest 覆盖核心逻辑；换实现时重写测试面，旧接口的测试跟着删，不留两层

## 架构不变量

1. **三段管线**：解析 → 流水线 → 送达。`main.py` 只接线，不放业务判断。
2. **产物是唯一出口形态**：`Text` / `Picture` / `SourceFile`（`render/artifacts.py`）。流水线与送达之间只传产物，不传消息组件。
3. **组件只在桥接层**：`render/bridge.py` 是全插件唯一 import `astrbot.api.message_components` 的模块。新增产物类型必须同时改桥接层，否则翻译会抛错（这是有意的）。
4. **元素注册表是唯一登记处**：加一种 markdown 元素只改 `render/elements.py`（渲染函数、两种文本配方、配置身份、清洗开关、是否块级、是否自带超时预算）。分组、模式查表、产物前缀、配置读取、日志汇总全部派生自它，不得另维护并行表。
5. **配置载入即校验**：模式名与默认值来自注册表；未知配置项或该元素不可达的模式，`load_config` 直接 `ValueError`，不猜、不降级。
6. **渲染器替换走覆盖层**：`plan_chain` / `build_chain` 的 `renderers` 参数是替换与测试的缝，生产传 `None`。渲染器签名是「segment → PNG bytes」，同步或协程都行。
7. **超时预算分层**：本机渲染器共用一个 15s 保险丝；自带预算的渲染器（走外部 HTTP）不套它，自己管超时与重试。
8. **失败必须降级为产物**：渲染失败 → 该模式可写文件则出 `.md`，否则回退原文文本。异常绝不抛给 RespondStage。
9. **临时文件只有一个主人**：`render/tempstore.py` 管命名、删除、刷新与 TTL 清扫；落盘路径随产物走，不从组件属性反推。
10. **严格保序**：任何并发优化都不得让后面的消息越过前面的组。
11. **流式结束不处理**：`STREAMING_FINISH` 一律跳过——流式阶段已把原文发出，再渲染会经送达重复发送。
12. **测试在容器内跑，优先真组件**：`tests/conftest.py` 能 import 真 AstrBot 组件就不装桩；渲染器测试经 `renderers` 覆盖层注入假的，`no_quantize` 夹具只关量化。

## 配置

`_conf_schema.json` 是默认值与可选值的唯一真相；各模式的语义见 README。
代码侧：`load_config(raw)` 把根级开关与 `渲染` / `分段` / `清洗` 三块转成 dataclass，元素模式按注册表校验。

## 内置技能

`skills/show-me/` 由 AstrBot 扫描 `<plugin>/skills/<name>/SKILL.md` 自动加载；frontmatter 只读 `description`（`disable-model-invocation` 之类无效）。`data/skills/` 下同名技能优先，会遮住插件内置版本。

## 设计文档

ADR 只在三个条件同时成立时写：难逆、不读就反直觉、真有替代方案被否掉；写进 `docs/adr/`（首次需要时创建）。
