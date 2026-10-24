"""PNG 归一化。

所有渲染产物（本机 takumi / typst、远端 mermaid.ink）都过这里一次：压成
128 色自适应调色板，体积回到 pillow 时代的水平，而语法高亮的颜色数远不到
128，肉眼无差。
"""
from __future__ import annotations

import struct
from io import BytesIO

from PIL import Image

from render import canvas

_COLORS = 128
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


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


def header_size(png: bytes) -> tuple[int, int]:
    """读 PNG 头拿尺寸，不解码像素。

    渲染器只需要宽高排版（如表格格内公式），为这个把整张图解码一遍是浪费。

    Args:
        png: PNG 字节。

    Returns:
        (宽, 高)，单位像素。

    Raises:
        ValueError: 不是 PNG，或缺 IHDR 块。
    """
    if len(png) < 24 or not png.startswith(_PNG_MAGIC) or png[12:16] != b"IHDR":
        raise ValueError("不是 PNG 数据，无法读取尺寸")
    width, height = struct.unpack(">II", png[16:24])
    return width, height


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
        backdrop = Image.new("RGBA", rgba.size, canvas.BG + "FF")
        backdrop.alpha_composite(rgba)
        return backdrop.convert("RGB")
    return image.convert("RGB")
