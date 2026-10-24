"""产物模型测试：文件名派生、媒体判定、临时路径收集。"""
from render.artifacts import Picture, SourceFile, Text, has_media, temp_paths


class TestSourceFile:
    def test_name_from_path(self):
        """文件名取自路径末段。"""
        assert SourceFile(path="/data/temp/code_1.md").name == "code_1.md"


class TestHasMedia:
    def test_text_only(self):
        """纯文本没有媒体。"""
        assert has_media([Text(text="a"), Text(text="b")]) is False

    def test_picture_counts_even_without_path(self):
        """不落盘的图片仍是媒体。"""
        assert has_media([Text(text="a"), Picture(png=b"p")]) is True

    def test_source_file_counts(self):
        """源文件是媒体。"""
        assert has_media([SourceFile(path="/tmp/x.md")]) is True


class TestTempPaths:
    def test_collects_landed_paths_only(self):
        """只收集落盘产物的路径。"""
        paths = temp_paths([
            Text(text="a"),
            Picture(png=b"p"),
            Picture(png=b"p", path="/tmp/a.png"),
            SourceFile(path="/tmp/b.md"),
        ])
        assert paths == ["/tmp/a.png", "/tmp/b.md"]

    def test_dedupes_in_order(self):
        """重复路径只保留首次出现。"""
        paths = temp_paths([
            Picture(png=b"p", path="/tmp/a.png"),
            SourceFile(path="/tmp/a.png"),
        ])
        assert paths == ["/tmp/a.png"]
