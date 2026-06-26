"""生成 README 效果图。需在 AstrBot 运行时环境中执行。"""
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

from astrbot.api.star import StarTools

from render.code import render_code
from render.expr import render_inline_expr, render_block_expr
from render.parser import CodeBlock, BlockExpr, InlineExpr, RichCell, Span, Table
from render.table import render_table
from render.utils import RenderConfig


def main():
    data_dir = StarTools.get_data_dir("astrbot_plugin_md_render")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "demo")
    os.makedirs(out, exist_ok=True)

    cfg = RenderConfig(
        code_mode="渲染图像",
        table_mode="渲染图像",
        expr_mode="渲染图像",
        divider_mode="不处理",
        font_color="#9CDCFE",
        bg_color="#1E1E1E",
        temp_ttl=5,
    )

    # 代码块
    cb = CodeBlock(lang="python", code="""def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

# 前 10 项
print([fibonacci(i) for i in range(10)])""")
    png_bytes, _ = render_code(cb, cfg, data_dir)
    with open(os.path.join(out, "code.png"), "wb") as f:
        f.write(png_bytes)
    print("code.png done")

    # 表格（含格内格式）
    t = Table(
        headers=[RichCell(spans=[Span(text="格式")]), RichCell(spans=[Span(text="示例")])],
        rows=[
            [
                RichCell(spans=[Span(text="加粗")]),
                RichCell(spans=[Span(text="重要数据", bold=True)]),
            ],
            [
                RichCell(spans=[Span(text="斜体")]),
                RichCell(spans=[Span(text="备注说明", italic=True)]),
            ],
            [
                RichCell(spans=[Span(text="删除线")]),
                RichCell(spans=[Span(text="已废弃", strike=True)]),
            ],
            [
                RichCell(spans=[Span(text="行内代码")]),
                RichCell(spans=[Span(text="config.py", code=True)]),
            ],
            [
                RichCell(spans=[Span(text="链接")]),
                RichCell(spans=[Span(text="文档", link_url="https://docs.x.com")]),
            ],
            [
                RichCell(spans=[Span(text="混合")]),
                RichCell(spans=[
                    Span(text="粗", bold=True),
                    Span(text="斜", italic=True),
                    Span(text="删", strike=True),
                    Span(text="码", code=True),
                ]),
            ],
        ],
    )
    png_bytes = render_table(t, cfg, data_dir)
    with open(os.path.join(out, "table.png"), "wb") as f:
        f.write(png_bytes)
    print("table.png done")

    # 行内表达式
    ie = InlineExpr(expr="E=mc^2")
    png_bytes = render_inline_expr(ie, cfg, data_dir)
    with open(os.path.join(out, "inline_expr.png"), "wb") as f:
        f.write(png_bytes)
    print("inline_expr.png done")

    # 块级表达式
    be = BlockExpr(expr=r"\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}")
    png_bytes = render_block_expr(be, cfg, data_dir)
    with open(os.path.join(out, "block_expr.png"), "wb") as f:
        f.write(png_bytes)
    print("block_expr.png done")

    print("\n效果图已生成:", sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
