"""生成 README 效果图。需在 AstrBot 运行时环境中执行。"""
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

from astrbot.api.star import StarTools

from render.code import render_code
from render.expr import render_inline_expr, render_block_expr
from render.parser import CodeBlock, BlockExpr, InlineExpr, Table
from render.table import render_table
from render.utils import RenderConfig, load_config


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
        glyph_mapping={"✗": "✕", "✓": "✔", "✅": "✔", "—": "-", "–": "-", "…": "...", "　": " "},
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
    png, _ = render_code(cb, cfg, data_dir)
    os.rename(png, os.path.join(out, "code.png"))
    print("code.png done")

    # 表格
    t = Table(
        headers=["方案", "可行", "原因"],
        rows=[
            ["minutely API", "❌", "免费 key 无权限"],
            ["升级付费 key", "⚠️", "能拿，要钱"],
            ["仅用逐小时降水", "✅", "已接入 fill_between"],
        ],
    )
    png = render_table(t, cfg, data_dir)
    os.rename(png, os.path.join(out, "table.png"))
    print("table.png done")

    # 行内表达式
    ie = InlineExpr(expr="E=mc^2")
    png = render_inline_expr(ie, cfg, data_dir)
    os.rename(png, os.path.join(out, "inline_expr.png"))
    print("inline_expr.png done")

    # 块级表达式
    be = BlockExpr(expr=r"\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}")
    png = render_block_expr(be, cfg, data_dir)
    os.rename(png, os.path.join(out, "block_expr.png"))
    print("block_expr.png done")

    print("\n效果图已生成:", sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
