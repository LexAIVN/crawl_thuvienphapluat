"""Unit tests for LuatVietnamDownloader ZIP extraction."""

import zipfile

import pytest

from src.crawler.luatvietnam_downloader import _extract_zip


def _make_zip(zip_path, entries: dict[str, bytes]):
    """Helper: create a ZIP file with the given name→content mapping."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


class TestExtractZip:
    def test_extracts_flat_files(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {
            "decree.doc": b"doc content",
            "appendix.doc": b"appendix content",
        })

        result = _extract_zip(zip_path, tmp_path)

        assert sorted(result) == ["appendix.doc", "decree.doc"]
        assert (tmp_path / "decree.doc").read_bytes() == b"doc content"
        assert (tmp_path / "appendix.doc").read_bytes() == b"appendix content"

    def test_extracts_nested_files_flat(self, tmp_path):
        """Files inside a subfolder in the ZIP are extracted flat."""
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {
            "subfolder/decree.doc": b"doc content",
            "subfolder/appendix.doc": b"appendix content",
        })

        result = _extract_zip(zip_path, tmp_path)

        assert sorted(result) == ["appendix.doc", "decree.doc"]
        assert (tmp_path / "decree.doc").read_bytes() == b"doc content"

    def test_order_num_prefix(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {
            "decree.doc": b"content",
            "phu_luc.doc": b"appendix",
        })

        result = _extract_zip(zip_path, tmp_path, order_num=5)

        assert sorted(result) == ["5_decree.doc", "5_phu_luc.doc"]
        assert (tmp_path / "5_decree.doc").read_bytes() == b"content"

    def test_no_order_num_no_prefix(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {"decree.doc": b"content"})

        result = _extract_zip(zip_path, tmp_path, order_num=None)

        assert result == ["decree.doc"]

    def test_skips_directory_entries(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {
            "folder/": b"",           # directory entry
            "folder/file.doc": b"x",
        })

        result = _extract_zip(zip_path, tmp_path)

        assert result == ["file.doc"]

    def test_empty_zip_returns_empty(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        _make_zip(zip_path, {})

        result = _extract_zip(zip_path, tmp_path)

        assert result == []

    def test_mixed_extensions_preserved(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        _make_zip(zip_path, {
            "decree.docx": b"docx",
            "decree.doc": b"doc",
            "decree.pdf": b"pdf",
        })

        result = _extract_zip(zip_path, tmp_path, order_num=1)

        assert sorted(result) == ["1_decree.doc", "1_decree.docx", "1_decree.pdf"]
