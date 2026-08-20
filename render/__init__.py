"""Markdown 渲染子包。

parser        : 解析 Plain 文本，提取代码块/表格/表达式/分隔线。
code_render   : pygments + pillow 渲染代码块。
table_render  : Pillow 手绘表格。
expr_render   : pillowlatex 渲染数学表达式。
chain         : 异步并发组装消息链。
font          : 字体发现与缓存。
config        : 渲染/分段/清洗配置。
"""
