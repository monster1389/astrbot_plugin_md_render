# 领域词汇表

## 概览

AstrBot 插件，在 `OnDecoratingResultEvent` 阶段把消息中的 markdown **代码块**、**表格**、**数学表达式**渲染为图片/文件，并按切分配置拆成多条消息发送。

处理流水线由三个阶段组成，每一阶段是一个独立的深模块：

```
解析 parse → 组装 assemble → 送达 deliver
```

## 解析（parse）

- **Segment**：markdown-it 解析产物。`CodeBlock`（代码块）、`Table`（表格）、`InlineExpr`/`BlockExpr`（行内/块级表达式）、`Divider`（分隔线 `---`）、`Segment`（纯文本段）。
- **消息链 chain**：AstrBot 的原始组件列表，Plain 文本是解析的输入。
- **占位符**：解析表达式时先把内容替换为 `\x01MATHBLOCK{n}\x01` 等占位符，绕过 markdown-it 对特殊字符的处理。

模块：`render/parser.py`。

## 组装（assemble）

- **渲染模式 mode**：每类元素可达的产物配方，中文配置串是唯一解释处。code/table 支持全部 5 种（不处理 / 渲染图像 / 渲染且保留原文 / 渲染且md文件 / 仅md文件），表达式只支持前 3 种。
- **模式配方 ModeSpec**：一个模式对应 text/image/file 三个插槽是否填充（联合能力表 `_MODE_SPECS`）。
- **元素配方 ElementSpec**：一个 segment 类型对应渲染函数、原文还原、清洗键、产物前缀（分发表 `_ELEMENT_SPECS`）。
- **分组 group**：按切分配置（分隔线=切分 / 连续换行=切分）把 Segment 列表拆成多条消息。
- **拆条 split**：含媒体的消息逐组件拆成独立消息，纯文本保持单条。
- **组装 assemble**：把各分组的构建结果拆条拼接为待发送消息列表，原链非 Plain 组件前置到首条。

模块：`render/chain.py`。

## 送达（deliver）

- **送达 deliver**：按序发送除末条外的所有消息，末条留作 `result.chain` 原地展示。
- **留尾 tail**：末条消息不发送，替换到结果链中，保证回复可见。
- **发送延时**：防风控，媒体消息间隔 1~3 秒，纯文本间隔 0.3~1 秒。
- **实质内容**：非 Plain 组件，或非空白的 Plain 文本。

模块：`render/deliver.py`（AstrBot 无关，通过 send 回调注入）。
