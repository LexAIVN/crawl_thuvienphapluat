"""Unit tests for luatvietnam scraper pure functions and scraper methods."""

import pytest

from src.crawler.luatvietnam_scraper import (
    _make_absolute_url,
    _extract_luatvietnam_id,
    _clean_title,
    LuatVietnamScraper,
)
from src.config import LuatVietnamConfig


# --- _make_absolute_url ---


class TestMakeAbsoluteUrl:
    def test_relative_path(self):
        result = _make_absolute_url(
            "https://luatvietnam.vn",
            "/ca-phan-van-ban/Nghi-dinh-138-199498.html",
        )
        assert result == (
            "https://luatvietnam.vn"
            "/ca-phan-van-ban/Nghi-dinh-138-199498.html"
        )

    def test_relative_path_no_leading_slash(self):
        result = _make_absolute_url(
            "https://luatvietnam.vn",
            "ca-phan-van-ban/Nghi-dinh-138-199498.html",
        )
        assert result == (
            "https://luatvietnam.vn"
            "/ca-phan-van-ban/Nghi-dinh-138-199498.html"
        )

    def test_already_absolute_url(self):
        url = "https://luatvietnam.vn/ca-phan-van-ban/doc-199498.html"
        result = _make_absolute_url("https://luatvietnam.vn", url)
        assert result == url

    def test_base_url_trailing_slash_stripped(self):
        result = _make_absolute_url(
            "https://luatvietnam.vn/",
            "/path/doc.html",
        )
        assert result == "https://luatvietnam.vn/path/doc.html"


# --- _extract_luatvietnam_id ---


class TestExtractLuatVietnamId:
    def test_versioned_url(self):
        # Primary pattern: -NNNNNN-dN.html
        url = (
            "https://luatvietnam.vn/can-bo/"
            "nghi-dinh-138-2020-tuyen-dung-194910-d1.html"
        )
        assert _extract_luatvietnam_id(url) == "194910"

    def test_versioned_url_d2(self):
        url = (
            "https://luatvietnam.vn/can-bo/"
            "nghi-dinh-56-2020-ND-CP-200001-d2.html"
        )
        assert _extract_luatvietnam_id(url) == "200001"

    def test_non_versioned_url(self):
        # Fallback pattern: -NNNNNN.html
        url = (
            "https://luatvietnam.vn/ca-phan-van-ban/"
            "Nghi-dinh-138-2020-ND-CP-199498.html"
        )
        assert _extract_luatvietnam_id(url) == "199498"

    def test_short_numeric_id(self):
        url = "https://luatvietnam.vn/path/Nghi-dinh-42.html"
        assert _extract_luatvietnam_id(url) == "42"

    def test_non_matching_url_returns_hash(self):
        url = "https://luatvietnam.vn/some/path/without-id"
        result = _extract_luatvietnam_id(url)
        assert result.isdigit()
        assert result == _extract_luatvietnam_id(url)

    def test_aspx_url_does_not_match(self):
        # .aspx URLs are for thuvienphapluat — should fall through to hash
        url = "https://thuvienphapluat.vn/van-ban/doc-375519.aspx"
        result = _extract_luatvietnam_id(url)
        assert result != "375519"
        assert result.isdigit()


# --- _clean_title ---


class TestCleanTitle:
    def test_collapse_whitespace(self):
        result = _clean_title("  Nghị  định   138/2020  ")
        assert result == "Nghị định 138/2020"

    def test_strip_numbered_prefix(self):
        result = _clean_title("1. Nghị định 138/2020")
        assert result == "Nghị định 138/2020"

    def test_strip_bullet_dash(self):
        result = _clean_title("- Nghị định 138/2020")
        assert result == "Nghị định 138/2020"

    def test_strip_bullet_unicode_dash(self):
        result = _clean_title("\u2013 Nghị định 138/2020")
        assert result == "Nghị định 138/2020"

    def test_strip_bullet_unicode_dot(self):
        result = _clean_title("\u2022 Nghị định 138/2020")
        assert result == "Nghị định 138/2020"

    def test_no_prefix_unchanged(self):
        result = _clean_title("Nghị định 138/2020/NĐ-CP")
        assert result == "Nghị định 138/2020/NĐ-CP"

    def test_empty_string(self):
        assert _clean_title("") == ""

    def test_only_whitespace(self):
        assert _clean_title("   ") == ""


# --- LuatVietnamScraper._build_paginated_url ---


class TestBuildPaginatedUrl:
    @pytest.fixture
    def scraper(self, monkeypatch):
        monkeypatch.setenv("LUATVIETNAM_USER", "test@example.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "testpass")
        config = LuatVietnamConfig()
        return LuatVietnamScraper(config)

    def test_page_1_contains_pageindex(self, scraper):
        url = scraper._build_paginated_url(1)
        assert "PageIndex=1" in url

    def test_page_5_contains_pageindex(self, scraper):
        url = scraper._build_paginated_url(5)
        assert "PageIndex=5" in url

    def test_pagesize_present(self, scraper):
        url = scraper._build_paginated_url(1)
        assert "PageSize=20" in url

    def test_base_path_preserved(self, scraper):
        url = scraper._build_paginated_url(1)
        assert "luatvietnam.vn/tim-van-ban.html" in url

    def test_keywords_preserved(self, scraper):
        url = scraper._build_paginated_url(1)
        assert "Keywords=" in url
