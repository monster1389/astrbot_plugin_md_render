"""Markdown 渲染子包。

parser         : 解析 Plain 文本，提取代码块/HTML 文档/Mermaid/表格/表达式/分隔线。
artifacts      : 产物模型：纯文本/图片/源文件 + 待发送消息。
bridge         : 消息组件 ↔ 产物（全插件唯一认识组件类型处）。
renderer       : takumi 渲染器的唯一出图口（代码块/表格/HTML 文档共用）。
canvas         : 自绘图共用的底色、字号阶梯、调色板与页面骨架。
png            : 渲染产物统一量化。
font           : 字体发现、族名、度量与注册清单。
code_render    : pygments 高亮 + pytakumi 出图。
table_render   : 表格测量与 flex 布局 + pytakumi 出图。
html_render    : 抽 <style> 后交 pytakumi 出图。
expr_render    : Typst 渲染数学表达式。
mermaid_render : mermaid.ink 远端渲染。
elements       : 元素注册表：一种元素怎么渲染、怎么还原文本、走哪个配置项。
chain          : 异步并发渲染，按分组逐条产出产物。
config         : 渲染/分段/清洗配置。
"""
