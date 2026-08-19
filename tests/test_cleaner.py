"""临时文件清理测试。"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from render.clean.temp_cleaner import _scan_and_clean


class TestCleaner:
    """测试 _scan_and_clean 清理逻辑。"""

    def _clean(self, ttl_minutes, names, mtime_epoch, now=None):
        with patch("render.clean.temp_cleaner.os.remove") as mock_remove, \
                patch("render.clean.temp_cleaner.os.listdir", return_value=names), \
                patch("render.clean.temp_cleaner.os.path.getmtime", return_value=mtime_epoch):
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
