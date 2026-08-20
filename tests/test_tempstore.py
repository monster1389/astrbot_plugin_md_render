"""render/tempstore.py 测试：临时文件命名匹配、路径生成、删除/刷新、周期清扫。"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call, patch

from render.tempstore import (
    _scan_and_clean,
    build_temp_path,
    delete,
    is_temp_file,
    touch,
)


class TestScanAndClean:
    """测试 _scan_and_clean 清理逻辑。"""

    def _clean(self, ttl_minutes, names, mtime_epoch, now=None):
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.listdir", return_value=names), \
                patch("render.tempstore.os.path.getmtime", return_value=mtime_epoch):
            _scan_and_clean("/tmp/test_temp", ttl_minutes, _now=now)
        return mock_remove

    def test_cleanup_skip_permanent(self):
        """TTL=-1 不删除任何文件。"""
        mock_remove = self._clean(-1, ["code_20260624_114940_123456.png"], 0.0)
        mock_remove.assert_not_called()

    def test_cleanup_ttl_zero_deletes_expired(self):
        """TTL=0：文件超过 1 分钟下限则删除。"""
        now = datetime(2026, 6, 24, 12, 0, 0)
        epoch = datetime(2026, 6, 24, 11, 58, 0).timestamp()  # 2 分钟前
        mock_remove = self._clean(0, ["table_20260624_114940_123456.png"], epoch, now)
        mock_remove.assert_called_once()

    def test_cleanup_ttl_zero_keeps_fresh(self):
        """TTL=0：文件未满 1 分钟不删除，避免误删尚未发送的产物。"""
        now = datetime(2026, 6, 24, 12, 0, 0)
        epoch = datetime(2026, 6, 24, 11, 59, 30).timestamp()  # 30 秒前
        mock_remove = self._clean(0, ["table_20260624_114940_123456.png"], epoch, now)
        mock_remove.assert_not_called()

    def test_cleanup_expired(self):
        """TTL>0 只删除过期文件。"""
        now = datetime(2026, 6, 24, 12, 0, 0)
        epoch = datetime(2026, 6, 24, 11, 49, 40).timestamp()  # 10.3 分钟前
        mock_remove = self._clean(5, ["table_20260624_114940_123456.png"], epoch, now)
        mock_remove.assert_called_once()

    def test_cleanup_not_expired(self):
        """TTL>0 不删除未过期文件。"""
        now = datetime(2026, 6, 24, 12, 0, 0)
        epoch = datetime(2026, 6, 24, 11, 59, 40).timestamp()  # 0.3 分钟前
        mock_remove = self._clean(5, ["table_20260624_114940_123456.png"], epoch, now)
        mock_remove.assert_not_called()

    def test_skip_non_temp_files(self):
        """非渲染产物文件名跳过，即使很旧。"""
        now = datetime(2026, 6, 24, 12, 0, 0)
        epoch = datetime(2026, 6, 24, 0, 0, 0).timestamp()
        mock_remove = self._clean(
            0,
            ["random.txt", "code_20260624_114940_123456.png"],
            epoch,
            now,
        )
        assert mock_remove.call_count == 1  # random.txt skipped


class TestBuildTempPath:
    @patch("render.tempstore.os.makedirs")
    def test_creates_dir_and_returns_path(self, mock_makedirs):
        path = build_temp_path("/data", "table", ".png")
        assert path.startswith("/data/temp/table_")
        assert path.endswith(".png")
        mock_makedirs.assert_called_once()


class TestIsTempFile:
    def test_matches_plugin_patterns(self):
        assert is_temp_file("code_20260624_114940_123456.png")
        assert is_temp_file("table_20260624_114940_123456.md")
        assert is_temp_file("expr_20260624_114940_123456.png")

    def test_matches_basename_of_full_path(self):
        assert is_temp_file("/data/temp/code_20260624_114940_123456.png")

    def test_rejects_foreign_names(self):
        assert not is_temp_file("random.txt")
        assert not is_temp_file("code_20260624.png")  # 时间戳不完整
        assert not is_temp_file("user_photo.png")


class TestDelete:
    def test_removes_each_path(self):
        with patch("render.tempstore.os.remove") as mock_remove:
            delete(["/tmp/a.png", "/tmp/b.md"])
        assert mock_remove.call_args_list == [call("/tmp/a.png"), call("/tmp/b.md")]

    def test_ignores_missing(self):
        mock_remove = MagicMock()
        mock_remove.side_effect = [FileNotFoundError, None]
        with patch("render.tempstore.os.remove", mock_remove):
            delete(["/tmp/a.png", "/tmp/b.md"])  # 不抛异常
        assert mock_remove.call_count == 2


class TestTouch:
    def test_updates_mtime_of_each_path(self):
        with patch("render.tempstore.os.utime") as mock_utime:
            touch(["/tmp/a.png", "/tmp/b.md"])
        assert mock_utime.call_args_list == [
            call("/tmp/a.png", None),
            call("/tmp/b.md", None),
        ]

    def test_ignores_missing(self):
        mock_utime = MagicMock()
        mock_utime.side_effect = [FileNotFoundError, None]
        with patch("render.tempstore.os.utime", mock_utime):
            touch(["/tmp/a.png", "/tmp/b.md"])  # 不抛异常
        assert mock_utime.call_count == 2
