"""PNG 归一化。

所有渲染产物（本机 takumi / typst、远端 mermaid.ink）都过这里一次：压成
128 色自适应调色板，体积回到 pillow 时代的水平，而语法高亮的颜色数远不到
128，肉眼无差。
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from render.theme import BG

_COLORS = 128


def quantize(png: bytes) -> bytes:
    """把 PNG 量化到调色板并重新编码。

    带透明通道的产物先合成到主题底色上：QQ 客户端对透明底的处理不一致，
    插件所有图片都该是不透明底。
    Args:
        png: 原始 PNG 字节。

    Returns:
        量化后的 PNG 字节。
    """
    with Image.open(BytesIO(png)) as image:
        flat = _flatten(image)
    palette = flat.convert("P", palette=Image.Palette.ADAPTIVE, colors=_COLORS)
    buf = BytesIO()
    palette.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _flatten(image: Image.Image) -> Image.Image:
    """把任意模式转成不透明 RGB，透明处填主题底色。

    Args:
        image: 解码后的图片。

    Returns:
        RGB 图片。
    """
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, BG + "FF")
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")
    return image.convert("RGB")
