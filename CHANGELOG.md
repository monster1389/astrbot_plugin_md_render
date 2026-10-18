# 更新日志

本文件记录 astrbot_plugin_md_render 的版本更新。

## [1.6.0] - 2026-10-18

### 变更
- **公式引擎由 pillowlatex 换成 Typst**（`typst` + `tylax`）。`aligned` 的 `&` 对齐、矩阵、`\text{中文}`、`\phantom` 由排版引擎处理，不再用替换表把命令改成 Unicode 字符。
- 转换层只补已知缺口：`\hbar`、`\frac{1}{\rho}\oint` 粘词、`\&`、`\_`、`\nleq`、`\mathscr`，以及表格里的 `\wp`/`\Finv`；其余转换或编译失败直接回退原文，不再静默剥命令。
- 删除 `normalize_latex` 及其替换表；依赖体积增加约 79MB（typst wheel 35MB），公式字形改为 New Computer Modern。
- `render/font.py` 新增 `font_family` / `font_search_dir`：系统字体交给 Typst，手动放置的 Sarasa 显式注册目录。

## [1.5.4] - 2026-10-18

### 修复
- **块级公式不再吞掉整段回复**。此前 `_pre_extract_block_math` 用 `$$(.+?)$$` 全局匹配：正文里只要出现一个被反引号包住的 `$$`，就会一路匹配到几段之后的 `$$`，把中间内容全塞进一张公式图，后面的公式块又因为分隔符被吃掉而降级成裸 LaTeX 文本。现在块级公式只认行首 `$$`（或同一行内成对），行内代码先遮蔽，找不到闭合就原样保留。
- **行内代码里的 `$...$` 不再被渲染**。识别公式前先遮住反引号代码 span，代码内容原样交给清洗。
- **`$\$9.99$` 这类带转义美元符的公式能识别了**。闭合 `$` 也要求前面不是反斜杠，内容允许 `\$`。
- **LaTeX 归一化**：pillowlatex 只覆盖常用子集，`\begin{aligned}`、`\dfrac`、`\mathcal`、`\bigoplus` 这类没注册的写法会被逐字画成命令名。新增 `normalize_latex`：等价命令换写法、缺失符号换 Unicode 字符、`\mathcal`/`\mathfrak`/`\mathbb`/`\mathscr` 换 Unicode 数学字母；仍然不支持的命令记警告后剥掉，不把命令名画进图里。
- **公式里的中文**：给数学字体挂上中文回退 face，`\text{中文}` 不再显示为方块。
- **表格格内公式**：`$...$` 现在渲染成小图嵌入单元格，不再把 `$\alpha\ \beta$` 源码画进表格。表格与清洗的文本/文件产物不受影响。

## [1.5.3] - 2026-10-18

### 变更
- 日志统一改用 `from astrbot.api import logger`，不再用标准库 `logging.getLogger(__name__)`（插件市场审核要求）。`table_render` / `html_render` 原本没打过日志，未使用的 logger 直接删除。
- `render_mermaid` 改为原生异步（`httpx.AsyncClient` + `asyncio.sleep`），不再占线程池线程；`build_chain` 识别协程渲染器直接 await，同步渲染器仍走 `asyncio.to_thread`。

## [1.5.2] - 2026-10-18

### 变更
- `skills/show-me` 的 description 改为强制语气：删掉英文触发词清单，改成 `You MUST use this skill whenever…` 的类别式条件，覆盖面按 system / paper / protocol / algorithm / API / data model 列举。
- 明确「用户用中文提问时，英文描述同样适用」，堵住「描述是英文所以中文请求不算匹配」这条推理；末句把只用散文回答定义为该 skill 的失败。
- 只改系统提示里那一行路由文本，SKILL.md 正文未变。

### 注意
- description 里出现 `: ` 会被 YAML 当作映射键，`_parse_frontmatter_description` 静默返回空串，技能描述直接变成 `No description`。这行必须避开冒号，或整体加引号。

## [1.5.1] - 2026-10-17

### 变更
- **渲染与发送流水线化**：`process_chain` 拆成 `plan_chain`（解析、分组、一次性提交全部渲染任务）+ `Pipeline`（按序逐条产出 `Message`），`deliver` 改为消费流水线、每条就绪即发。首条消息不再等最慢的元素渲染完成——实测一条多元素回复的首屏延迟从约 2.7 秒降到首条产出即发（该条本身为纯文本时约 0.1 秒）。
- 流水线严格保序：慢的组挡住它后面的消息，绝不越过；末条由 `Pipeline` 的 `is_tail` 标记，交付语义不变（仍留作 `result.chain`）。
- 防风控延时与渲染重叠：两条消息的间隔按上一条实际发出时刻起算，渲染耗时已消耗的部分不再叠加，不足下限才补。
- 单个元素的渲染加 15 秒保险丝（`_RENDER_TIMEOUT`），超时走既有失败降级（该模式含 md 文件仍写文件，否则回退原文），最坏停顿有界。
- `已渲染 N 项` 汇总日志改为流水线跑完后输出；逐条发送日志不再带总条数（流式送出，条数在首条发出时未知）。

### 文档
- README 按使用顺序重排：定位、效果图、启用、默认行为、配置、常见问题、字体、架构。补「启用」章节，把原先藏在提示块里的两个 AstrBot 开关并进安装步骤；字体教程移到 `docs/fonts.md`；渲染效果合成一张横排总览图 `docs/demo/overview.png`，聊天截图裁为纵条并配两栏版面，均由 `docs/demo/make_overview.py` 生成。
- `_conf_schema.json` 的 hint 改为陈述句：去掉补充性括号与解释性从句，与 README 用同一套笔法。

## [1.5.0] - 2026-10-17

### 新增
- 根级配置「仅处理模型回复」（默认关）：开启后只处理 LLM / Agent 回复（`result.is_model_result()`），其它插件与内置命令的普通消息原样放过。

### 变更
- **字体不再依赖手动安装**：`render/font.py` 的发现结果由路径升级为 `FontSpec(path, index)`，按「`data_dir/fonts/SarasaMonoSC-Regular.ttf` → 系统 Noto Sans Mono CJK SC（`NotoSansCJK-Regular.ttc` 第 7 个 face，AstrBot 官方镜像自带）→ 文泉驿等宽（第 1 个 face）→ DejaVu Sans Mono」取第一个存在的。ttc 必须指定 face：第 0 个是比例字体，直接按路径取会让代码列对齐歪掉。
- 代码块渲染改用 `ImageFormatter` 子类注入 face index（`_FaceFormatter` / `_FaceFontManager`），不新增依赖。
- README：手动安装 Sarasa 由「必读」降为「可选、观感更佳」，补字体发现顺序表；配置章节补根级开关；补流式输出相关说明。
- `skills/show-me/SKILL.md` 说明改为全英文，frontmatter 描述保留中文触发词。

### 修复
- 流式输出开启且平台不支持流式（默认策略「实时分段回复」）时，跳过 `STREAMING_FINISH` 结果。此前该结果仍会触发渲染并经 `deliver` 把非末条消息再次发出，造成内容重复，而末条又被 RespondStage 丢弃。

## [1.4.0] - 2026-10-17

### 新增
- **HTML 文档渲染**：` ```html ` 围栏且含 `<!DOCTYPE`/`<html>` 时，用 pytakumi（Rust 布局引擎，无浏览器）渲染为 PNG；抽取 `<style>` 经 `stylesheets` 传入，注册 Noto Sans CJK / 文泉驿 / 插件字体。新增配置「HTML」与「HTML 宽度」（默认 1000）。
- **Mermaid 图表渲染**：` ```mermaid ` 经 mermaid.ink 渲染为暗底 PNG（`bgColor=1E1E1E`），5 秒超时、5xx 重试一次，失败回退源码文本。配置对齐代码/表格的五种模式，`仅md文件` 交给 QQ 原生渲染。新增配置「Mermaid」，需联网（仅图片模式）。
- **插件内置技能**：`skills/show-me/SKILL.md`，改写为可被模型主动触发，第 7 种表达改为输出 ` ```html ` 文档而非写文件。

### 修复
- 未知语言的代码块不再 `guess_lexer`（会把 mermaid 认成 ECLLexer、调用树认成 ScdocLexer），改为 TextLexer 纯文本渲染。
- `渲染且md文件` 模式下图渲染失败时，不再连 `.md` 一起丢掉：仍写文件，不回退原文。
- 临时文件命名白名单补上 `html`/`mermaid` 前缀，否则新渲染器产出的文件不会被发送后删除，也不会被 TTL 清扫。

### 其他
- 依赖新增 `pytakumi>=0.1.5`；README/CLAUDE/架构图同步。

## [1.3.7] - 2026-09-07

### 其他
- README 效果展示改为四张小图一行表并前置；配置按渲染/分段/清洗三分块整理，说明集中末尾，修正分段默认值（默认切分）；关闭官方分段回复提示移至字体安装节前；文末补架构 mermaid 图与聊天效果大图。
- CLAUDE.md 同步三分块配置描述与模块结构图。

## [1.3.6] - 2026-09-07

### 其他
- metadata 描述改为单行、分号分隔（商店只显示一行），并新增「安装字体看README.md」。
- README 建议关闭 AstrBot 官方配置中的「分段发送」，避免对插件已切分的消息再次拆分。

## [1.3.5] - 2026-09-07

### 移除
- 移除启动时自动下载并解压「更纱等宽黑体」的逻辑及 `py7zr` 依赖（通过安全审查：不再于运行时下载外部 7z 压缩包并解包）。字体改为手动安装：下载 `SarasaMonoSC-Regular.ttf` 放入 `<AstrBot 数据目录>/plugin_data/astrbot_plugin_md_render/fonts/`，README 顶部附完整下载/解压/放置/重启命令，安装后重启 AstrBot 生效。

### 其他
- `typing.Callable` 迁移到 `collections.abc`，全量清理 import 排序，容器内 ruff 0.15.22 零告警。
- CLAUDE.md 开发环境由宿主机 `.venv` 改为容器内 `docker exec` 执行；README/metadata 改为手动安装字体指引。

## [1.3.4] - 2026-08-20

### 重构
- 表格子域提炼为 `render/table_domain.py`：Span/RichCell/Table 模型、inline 格式栈遍历、`cell_to_markdown`/`table_to_markdown`/`table_to_plain` 还原与 `parse_table` 从 parser 迁出，与类型同居。
- 行内格式状态机提炼为 `render/inline_format.py`：表格 `_extract_spans_from_children` 与清洗 `_walk_inline` 共用同一 `FormatState`/`advance`。
- 字体服务提炼为 `render/font.py` 深模块：`find_font_path`/`get_font` 自 `utils` 迁出，按字号缓存并回退默认字体；`utils.py` 改名 `config.py` 只留配置对象。
- 三个渲染器改名 `code_render`/`expr_render`/`table_render`，签名统一为 `(元素) → bytes`，不再自取字体；`render/clean/` 子包拍平，`md_cleaner.py` 上移至 `render/`。
- 元素原文序列化与类型同居：`codeblock_to_markdown`/`codeblock_to_plain`、`expr_to_markdown`/`expr_to_plain` 移入 `parser.py`，配方表 `_ELEMENT_SPECS` 换薄选择器（沿用 table_domain 模式）。
- 删除 `md_cleaner._walk` 块级 link 跟踪死代码。

> 本版本为纯内部重构，用户可见行为与 1.3.3 一致。

## [1.3.3] - 2026-08-20

### 修复
- 修复 `$$...$$` 在表格单元格与代码围栏中泄漏占位符（`\x01MATHBLOCK{n}\x01` 作为可见文本漏出）。块级数学预提取改为逐行识别 ``` / ~~~ 围栏，围栏内 `$$...$$` 不再预提取，代码内容字节级原样保留；表格单元格路径新增还原，占位符恢复为 `$expr$`。
- 修复表达式渲染器签名与 `build_chain` 契约不匹配导致从不渲染的问题。`render_expr` 原只接收单参数，构建时按两参统一调用，每次渲染表达式都抛 TypeError 被静默回退为原文文本，现已统一为两参契约并补回归测试。

### 新增
- 行内表达式不拆条：纯文本段与行内表达式组成的内联组整组合并成一条消息，表达式图片插在文字原位；代码块/表格/块级表达式仍作为消息边界各自独立成条，保持阅读顺序。

### 重构
- 临时文件生命周期聚合为 `render/tempstore.py` 单点主人。`build_temp_path`/`is_temp_file` 自 `utils`、`delete`/`touch` 自 `deliver`、清扫循环自 `temp_cleaner` 全部收口到新模块，与 AstrBot 无关；消除「谁活着、活多久」四散四个模块的归属不清。纯搬家，行为零变化。

## [1.3.2] - 2026-08-20

### 重构
- 元素配方表 `_ELEMENT_SPECS` 统一覆盖全部元素类型（含纯文本段、分隔线），按 `(类型, mode_key)` 单一模型查产物配方，删除 `_mode_for` 的静默兜底。
- 表格还原函数 `cell_to_markdown` / `table_to_markdown` / `table_to_plain` 移入 `parser.py`，与表格数据模型同住。
- `build_chain` 移除无用的 `seg_cfg` 参数（分隔线切分由 `group_segments` 先行消费）。
- 修正 `process_chain` 的元素判断，避免纯文本段纳入配方表后被误判为结构性元素。

> 本版本为纯内部重构，用户可见行为与 1.3.1 一致。

## [1.3.1] - 2026-08-19

### 修复
- 修复「临时文件存活=0」时 md 文件（渲染且md文件 / 仅md文件）在发送前被清理线程删除的问题。清理不再按构建时刻算存活，改为按文件实际写盘时间；`0` 改义为「发送完成后立即删除」。
- 每条消息发送完成后立即删除其临时文件（图片/文件在发送时已读走），临时文件不会残留到下一个清扫周期。
- 末条消息（QQ 在插件返回后才发送）交棒前刷新其临时文件时间戳，保证至少再保留 1 分钟，不被清理线程误删；`0` 档同样按至少 1 分钟兜底。
- 只删除匹配本插件临时文件命名模式的产物，消息链中的用户/LLM 原始图片等外部文件不受影响。

## [1.3.0] - 2026-08-19

### 重构
- 配置拆为「渲染 / 分段 / 清洗」三大块：分隔线、连续换行、发送延时移入新增的「分段」块，`RenderConfig` 拆出独立的 `SegmentConfig`。
- 插件描述改为三行（渲染 / 分段 / 清洗）。

### 新增
- 清洗新增「分隔线」：去除独立 `---` 标记，保留段落分隔。分段=切分时分隔线先作消息断点被消费，清洗不重复作用（切分优先于清洗）。
- 清洗新增「连续换行」：将连续空行压为单个换行。分段=切分时同样由切分优先处理。

## [1.2.3] - 2026-08-17

### 其他
- 更新插件描述为「无浏览器 Markdown / LaTeX 转图片 + Markdown 杀手 + 分段」，补充分段 tag。

## [1.2.2] - 2026-08-16

### 重构
- 抽取 `process_chain` 完整管线，`main.py` 瘦身为接线适配器；送达逻辑迁入独立 `deliver` seam。
- 元素渲染/文本配方集中为 `ElementSpec` 单表，清洗改为结构直取，删除三处正则清洗函数。
- 渲染器改为经 `renderers` 参数注入，测试从 `@patch` 全局魔法迁移为显式传 seam。
- 清理迁移垫片与无人引用的重导出。

> 本版本为纯内部重构，用户可见行为与 1.2.1 一致。

## [1.2.1] - 2026-08-16

### 修复
- 修复「渲染且保留原文」时消息拆分错乱。原先按类型粗暴切成「所有文本 / 所有媒体」，导致代码原文互相粘连、渲染图互相粘连，阅读顺序错乱。现在组内含媒体时**逐组件独立成条**，保持阅读顺序（正常文本 / 代码原文 / 渲染图 / 表格原文 / 表格图各自一条）；纯文本组保持单条不拆；「渲染图像」的连续多图也不再合并。
- 字体下载增加 gh-proxy 镜像前置兜底，GitHub 直连失败自动回退。

### 改进
- 发送延时分级：图片/文件之间随机 1~3 秒，纯文本之间随机 0.3~1 秒，防风控的同时缩短整条回复的等待时间。

## [1.2.0] - 2026-08-16

### 新增
- 切分后的分段作为独立 QQ 消息发送（分隔线/连续换行切分、渲染且保留原文拆分）。
- 发送延时开关：切分后的多条消息之间随机延时 1~3 秒，避免连续发送触发风控。

### 其他
- 补充插件 tags。

## [1.1.0] - 2026-08-16

### 新增
- Markdown 格式清洗：基于 markdown-it-py token 树去除加粗、斜体、删除线、行内代码、链接、标题、列表、引用、图片等格式标记，颜表情中的 `*` `_` `~` 不会被误杀。
- 已渲染元素清洗：代码块、表格、表达式在以文本形式保留时（不处理 / 渲染且保留原文）可独立开关去除其 markdown 标记。
- 代码块、表格新增「渲染且md文件」「仅md文件」模式。
- 配置项改为嵌套分组（渲染 / 清洗），并补全提示文案。

### 修复
- 清洗后段落换行（`\n\n`）的保留、分隔线与歌词 `---` 的误判、非 Plain 组件（图片/文件/回复）在整链替换时的保留等若干问题。
