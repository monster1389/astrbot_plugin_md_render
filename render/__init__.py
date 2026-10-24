"""Markdown 渲染子包。

parser         : 解析 Plain 文本，提取代码块/HTML 文档/Mermaid/表格/表达式/分隔线。
renderer       : takumi 渲染器的唯一出图口（代码块/表格/HTML 文档共用）。
theme          : 自绘图片共用的底色与页面骨架。
png            : 渲染产物统一量化。
font           : 字体发现、族名、度量与注册清单。
code_render    : pygments 高亮 + pytakumi 出图。
table_render   : 表格测量与 flex 布局 + pytakumi 出图。
html_render    : 抽 <style> 后交 pytakumi 出图。
expr_render    : Typst 渲染数学表达式。
mermaid_render : mermaid.ink 远端渲染。
chain          : 异步并发组装消息链。
config         : 渲染/分段/清洗配置。
"""
