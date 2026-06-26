"""Markdown 渲染子包。

parser : 解析 Plain 文本，提取代码块/表格/表达式/分隔线。
code   : pygments + pillow 渲染代码块。
table  : Pillow 手绘表格。
expr   : pillowlatex 渲染数学表达式。
chain  : 异步并发组装消息链。
"""
from render.parser import (  # noqa: E402, F401
    BlockExpr,
    CodeBlock,
    Divider,
    InlineExpr,
    Segment,
    Table,
    parse,
)
