"""桥接层测试：消息组件与产物之间的双向翻译。"""
import pytest
from astrbot.api.message_components import File as AstrFile
from astrbot.api.message_components import Image, Plain

from render.artifacts import Picture, SourceFile, Text
from render.bridge import split_chain, to_components


class TestSplitChain:
    def test_joins_plain_texts_with_newline(self):
        """多个 Plain 以换行拼接，过境组件为空。"""
        assert split_chain([Plain("a"), Plain("b")]) == ("a\nb", [])

    def test_extras_keep_order(self):
        """非 Plain 组件按原顺序过境，不进文本。"""
        img = Image.fromFileSystem("/tmp/a.png")
        text, extras = split_chain([img, Plain("正文"), img])
        assert text == "正文"
        assert extras == [img, img]

    def test_empty_chain(self):
        """空链得到空文本与空过境。"""
        assert split_chain([]) == ("", [])

    def test_plain_with_empty_text(self):
        """空文本的 Plain 不产生内容。"""
        assert split_chain([Plain("")]) == ("", [])


class TestToComponents:
    def test_text_becomes_plain(self):
        """文本产物翻成 Plain。"""
        comps = to_components([Text(text="正文")])
        assert isinstance(comps[0], Plain)
        assert comps[0].text == "正文"

    def test_landed_picture_uses_filesystem(self):
        """有落盘路径的图片走文件系统引用。"""
        comps = to_components([Picture(png=b"png", path="/tmp/code_1.png")])
        assert isinstance(comps[0], Image)
        assert comps[0].path == "/tmp/code_1.png"

    def test_unlanded_picture_uses_bytes(self):
        """不落盘的图片以字节发送。"""
        comps = to_components([Picture(png=b"png")])
        assert isinstance(comps[0], Image)
        assert comps[0].file.startswith("base64://")

    def test_source_file_keeps_name_and_path(self):
        """源文件产物的文件名由路径派生。"""
        comps = to_components([SourceFile(path="/tmp/table_1.md")])
        assert isinstance(comps[0], AstrFile)
        assert comps[0].name == "table_1.md"
        assert comps[0].file_ == "/tmp/table_1.md"

    def test_order_preserved(self):
        """翻译保持产物顺序。"""
        comps = to_components([Text(text="a"), Picture(png=b"p"), Text(text="b")])
        assert [type(c) for c in comps] == [Plain, Image, Plain]

    def test_unknown_type_is_loud(self):
        """未登记的产物类型直接抛错，不静默放过。"""
        with pytest.raises(TypeError):
            to_components([Plain("不是产物")])
