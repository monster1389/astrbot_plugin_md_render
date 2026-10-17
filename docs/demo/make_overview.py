"""生成 README 用的效果图。

四张渲染结果合成一张横排总览 `docs/demo/overview.png`；聊天截图裁掉上半的
markdown 源码气泡，只留渲染后的实际效果 `docs/demo/chat-strip.jpg`。

用法：

    docker exec -w /AstrBot/data/plugins/astrbot_plugin_md_render astrbot \
        python3 docs/demo/make_overview.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageOps

_HERE = os.path.dirname(os.path.abspath(__file__))

# 总览图排版：与插件渲染图同底色，四格等宽等高、留缝、描边
_PANEL = (240, 160)
_GAP = 8
_BG = (30, 30, 30)
_BORDER = (60, 60, 60)
_SOURCES = ("code.png", "table.png", "inline_expr.png", "block_expr.png")

# 聊天截图裁切框：去掉上半的 markdown 源码气泡，止于最后一个完整气泡的底边
_CHAT_CROP = (0, 840, 600, 1816)


def _panel(path: str) -> Image.Image:
    """把一张渲染图缩放居中放进固定尺寸的格子。

    Args:
        path: 素材路径。

    Returns:
        带描边的格子图像。
    """
    box = Image.new("RGB", _PANEL, _BG)
    with Image.open(path) as src:
        img = ImageOps.contain(src.convert("RGB"), _PANEL)
    box.paste(img, ((_PANEL[0] - img.width) // 2, (_PANEL[1] - img.height) // 2))
    ImageDraw.Draw(box).rectangle(
        [0, 0, _PANEL[0] - 1, _PANEL[1] - 1], outline=_BORDER
    )
    return box


def build_overview() -> None:
    """合成四格横排总览图。"""
    count = len(_SOURCES)
    width = count * _PANEL[0] + (count - 1) * _GAP
    strip = Image.new("RGB", (width, _PANEL[1]), _BG)
    for index, name in enumerate(_SOURCES):
        strip.paste(_panel(os.path.join(_HERE, name)), (index * (_PANEL[0] + _GAP), 0))
    strip.save(os.path.join(_HERE, "overview.png"))


def build_chat_strip() -> None:
    """裁掉聊天截图上半的源码气泡，只留渲染结果。"""
    with Image.open(os.path.join(_HERE, "chat.jpg")) as src:
        cropped = src.convert("RGB").crop(_CHAT_CROP)
    cropped.save(os.path.join(_HERE, "chat-strip.jpg"), quality=90)


if __name__ == "__main__":
    build_overview()
    build_chat_strip()
