"""PNG 归一化测试。"""
import io
import base64

import pytest
from PIL import Image

from render.chain import build_chain
from render.config import RenderConfig
from render.elements import FAMILIES
from render.parser import CodeBlock
from render.png import header_size, quantize

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOQk5MDAAC4AFuF"
    "/QUSAAAAAElFTkSuQmCC"
)


class TestQuantize:
    def test_output_is_png_of_same_size(self):
        image = Image.new("RGB", (40, 20), (26, 26, 46))
        buf = io.BytesIO()
        image.save(buf, "PNG")

        result = quantize(buf.getvalue())

        assert result.startswith(b"\x89PNG")
        assert Image.open(io.BytesIO(result)).size == (40, 20)

    def test_transparent_input_is_flattened(self):
        """带透明通道的产物先合成到底色，不留 alpha。"""
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        buf = io.BytesIO()
        image.save(buf, "PNG")

        result = quantize(buf.getvalue())

        out = Image.open(io.BytesIO(result))
        assert out.mode == "P"
        assert "transparency" not in out.info
        assert out.convert("RGB").getpixel((0, 0)) == (30, 30, 30)

    def test_solid_image_shrinks(self):
        """平色图量化后体积明显小于原图。"""
        image = Image.new("RGB", (400, 200), (26, 26, 46))
        buf = io.BytesIO()
        image.save(buf, "PNG")
        assert len(quantize(buf.getvalue())) < len(buf.getvalue())


class TestHeaderSize:
    def test_reads_ihdr_without_decoding(self):
        """尺寸直接从 PNG 头读，不解码像素。"""
        assert header_size(_PNG_1PX) == (1, 1)

    def test_rejects_non_png(self):
        with pytest.raises(ValueError):
            header_size(b"not a png at all")


class TestChainQuantizesProduct:
    """链出口对所有产物统一量化（不经 no_quantize 夹具）。"""

    def test_result_is_quantized(self, tmp_path):
        import asyncio
        from unittest.mock import MagicMock

        fake = MagicMock(return_value=_PNG_1PX)
        cfg = RenderConfig(
            modes={key: "不处理" for key in FAMILIES} | {"code": "渲染图像"},
            temp_ttl=0,
        )
        result = asyncio.run(
            build_chain(
                [CodeBlock(lang="py", code="x=1")],
                cfg,
                None,
                str(tmp_path),
                renderers={CodeBlock: fake},
            )
        )
        assert result[0].png != _PNG_1PX
        assert result[0].png == quantize(_PNG_1PX)
