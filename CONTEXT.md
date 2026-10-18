# 领域词汇表

## 概览

AstrBot 插件，在 `OnDecoratingResultEvent` 阶段把消息中的 markdown **代码块**、**HTML 文档**、**Mermaid 图表**、**表格**、**数学表达式**渲染为图片/文件，并按切分配置拆成多条消息发送。

处理流水线由三个阶段组成，每一阶段是一个独立的深模块：

```
解析 parse → 流水线 pipeline → 送达 deliver
```

## 解析（parse）

- **Segment**：markdown-it 解析产物。`CodeBlock`（代码块）、`HtmlDoc`（完整 HTML 文档）、`MermaidBlock`（Mermaid 图表）、`Table`（表格）、`InlineExpr`/`BlockExpr`（行内/块级表达式）、`Divider`（分隔线 `---`）、`Segment`（纯文本段）。
- **块级表达式**：`$$` 独占行首开块、行尾闭合，或同一行内成对；正文里零散的 `$$` 不开启匹配，代码围栏与行内代码里的 `$` 不参与识别。
- **消息链 chain**：AstrBot 的原始组件列表，Plain 文本是解析的输入。
- **占位符**：解析表达式时先把内容替换为 `\x01MATHBLOCK{n}\x01` 等占位符，绕过 markdown-it 对特殊字符的处理。

模块：`render/parser.py`。

## 流水线（pipeline）

- **渲染模式 mode**：每类元素可达的产物配方，中文配置串是唯一解释处。code/table/mermaid 支持全部 5 种（不处理 / 渲染图像 / 渲染且保留原文 / 渲染且md文件 / 仅md文件），表达式与 HTML 只支持前 3 种。
- **模式配方 ModeSpec**：一个模式对应 text/image/file 三个插槽是否填充（联合能力表 `_MODE_SPECS`）。
- **元素配方 ElementSpec**：一个 segment 类型对应渲染函数、原文还原、清洗键、产物前缀（分发表 `_ELEMENT_SPECS`）。
- **分组 group**：按切分配置（分隔线=切分 / 连续换行=切分 / 块级元素）把 Segment 列表拆成多条消息。纯文本段 + 行内表达式组成的内联组带 `keep_whole` 标记。
- **内联组 keep_whole**：只含纯文本段 + 行内表达式的组整组合并成一条消息，表达式图片插在文字原位。
- **拆条 split**：块级组（代码块/HTML 文档/Mermaid 图表/表格/块级表达式）逐组件拆成独立消息，保持阅读顺序。
- **流水线 Pipeline**：`plan_chain` 解析分组后一次性提交全部渲染任务，`Pipeline` 按序逐组等待结果、组装、逐条产出。
- **产出消息 Message**：流水线产出的带 `is_tail` 标记的消息，`chain` 为组件列表；`is_tail` 即留尾语义，送达侧因此不必向前多取一条。
- **保序**：严格按分组顺序产出，某组渲染慢时它后面的消息一律等它，绝不越过。

模块：`render/chain.py`。

## 渲染（render）

- **公式转换 to_typst**：tylax 把 LaTeX 转成 Typst 语法；`\hbar`、`\&`、`\_`、`\mathscr`、`\wp` 等已知缺口在转换前后修补，转换或编译失败直接回退原文。词义：把「用户写的 LaTeX」翻译成「Typst 能排的写法」。
- **数学字体 math font**：Typst 内置 New Computer Modern；公式里的中文走 `font.py` 发现的字体（手动 Sarasa 优先，系统 Noto 兜底）。
- **格内公式 cell expr**：表格里 `$...$` 渲染为小图嵌入单元格，格内文字与公式图分开度量、垂直居中。

## 送达（deliver）

- **送达 deliver**：消费流水线，除末条外每条就绪即发；末条（`is_tail`）留作 `result.chain` 原地展示。
- **留尾 tail**：末条消息不发送，替换到结果链中，保证回复可见。
- **发送延时**：防风控，媒体消息间隔 1~3 秒，纯文本间隔 0.3~1 秒；从上一 条实际发出时刻起算，渲染耗时已消耗的部分不再叠加，不足下限才补。
- **实质内容**：非 Plain 组件，或非空白的 Plain 文本。

模块：`render/deliver.py`（AstrBot 无关，通过 send 回调注入）。
