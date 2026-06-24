"""临时文件清理测试。"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from render.cleaner import _parse_file_ts


class TestParseFileTs:
    """测试 _parse_file_ts 文件名时间戳解析。"""

    def test_valid_filename(self):
        """正确的文件名格式能解析出时间戳。"""
        ts = _parse_file_ts("table_20260624_114940.png")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 6
        assert ts.day == 24
        assert ts.hour == 11
        assert ts.minute == 49

    def test_invalid_filename(self):
        """非渲染产物文件名返回 None。"""
        assert _parse_file_ts("random.txt") is None
        assert _parse_file_ts("markdown_it_py.md") is None

    def test_code_filename(self):
        """代码块文件名也能解析。"""
        ts = _parse_file_ts("code_20260624_114940.txt")
        assert ts is not None
        assert ts.minute == 49


class TestCleaner:
    """测试 _scan_and_clean 清理逻辑。"""

    @patch("render.cleaner.os.remove")
    @patch("render.cleaner.os.listdir")
    def test_cleanup_skip_permanent(self, mock_listdir, mock_remove):
        """TTL=-1 不删除任何文件。"""
        temp_dir = "/tmp/test_temp"
        mock_listdir.return_value = ["table_20260624_114940.png"]

        from render.cleaner import _scan_and_clean

        _scan_and_clean(temp_dir, ttl_minutes=-1)
        mock_remove.assert_not_called()

    @patch("render.cleaner.os.remove")
    @patch("render.cleaner.os.listdir")
    def test_cleanup_immediate(self, mock_listdir, mock_remove):
        """TTL=0 删除所有解析成功的文件。"""
        temp_dir = "/tmp/test_temp"
        mock_listdir.return_value = [
            "table_20260624_114940.png",
            "expr_20260624_114940.png",
            "random.txt",
        ]

        from render.cleaner import _scan_and_clean

        _scan_and_clean(temp_dir, ttl_minutes=0)
        assert mock_remove.call_count == 2  # random.txt skipped

    @patch("render.cleaner.os.remove")
    @patch("render.cleaner.os.listdir")
    def test_cleanup_expired(self, mock_listdir, mock_remove):
        """TTL>0 只删除过期文件。

        table_20260624_114940.png → datetime(2026,6,24,11,49,40)
        _now = 12:00:00 → age ≈ 10.33min > 5min TTL → 应删除。
        """
        temp_dir = "/tmp/test_temp"
        mock_listdir.return_value = ["table_20260624_114940.png"]

        from render.cleaner import _scan_and_clean

        _scan_and_clean(
            temp_dir,
            ttl_minutes=5,
            _now=datetime(2026, 6, 24, 12, 0, 0),
        )

        mock_remove.assert_called_once()

    @patch("render.cleaner.os.remove")
    @patch("render.cleaner.os.listdir")
    def test_cleanup_not_expired(self, mock_listdir, mock_remove):
        """TTL>0 不删除未过期文件。

        table_20260624_114940.png → datetime(2026,6,24,11,49,40)
        _now = 11:50:00 → age ≈ 0.33min < 5min TTL → 不删除。
        """
        temp_dir = "/tmp/test_temp"
        mock_listdir.return_value = ["table_20260624_114940.png"]

        from render.cleaner import _scan_and_clean

        _scan_and_clean(
            temp_dir,
            ttl_minutes=5,
            _now=datetime(2026, 6, 24, 11, 50, 0),
        )

        mock_remove.assert_not_called()
