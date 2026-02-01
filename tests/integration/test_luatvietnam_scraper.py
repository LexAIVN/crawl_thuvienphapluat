"""Integration tests for LuatVietnamScraper with mocked Playwright."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.crawler.luatvietnam_scraper import LuatVietnamScraper
from src.config import LuatVietnamConfig


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("LUATVIETNAM_USER", "test@example.com")
    monkeypatch.setenv("LUATVIETNAM_PASSWORD", "testpass")
    return LuatVietnamConfig()


@pytest.fixture
def scraper(config):
    return LuatVietnamScraper(config)


def _make_mock_element(href: str, title: str):
    """Create a mock Playwright element with get_attribute and text_content."""
    element = AsyncMock()
    element.get_attribute = AsyncMock(return_value=href)
    element.text_content = AsyncMock(return_value=title)
    return element


def _make_mock_page(links: list[tuple[str, str]]):
    """Create a mock page that returns links for the first nghi-dinh selector.

    Args:
        links: List of (href, title) tuples to simulate on the page.
               hrefs must match the document ID pattern (-NNNNNN-dN.html
               or -NNNNNN.html) to pass the scraper's href filter.

    Returns:
        Mock Page object
    """
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    elements = [_make_mock_element(href, title) for href, title in links]

    def locator_factory(selector):
        loc = AsyncMock()
        # Match the first selector the scraper tries for nghi-dinh links
        if 'nghi-dinh' in selector or 'Nghi-dinh' in selector:
            loc.count = AsyncMock(return_value=len(elements))
            loc.nth = MagicMock(side_effect=lambda i: elements[i])
        else:
            loc.count = AsyncMock(return_value=0)
        return loc

    page.locator = MagicMock(side_effect=locator_factory)
    return page


class TestScrapePage:
    async def test_extracts_documents_from_page(self, scraper):
        links = [
            (
                "/can-bo/nghi-dinh-138-2020-tuyen-dung-194910-d1.html",
                "Nghị định 138/2020/NĐ-CP về tuyển dụng công chức",
            ),
            (
                "/can-bo/nghi-dinh-56-2020-ND-CP-200001-d1.html",
                "Nghị định 56/2020/NĐ-CP",
            ),
        ]
        page = _make_mock_page(links)

        documents = await scraper._scrape_page(page, "https://luatvietnam.vn/search")

        assert len(documents) == 2
        assert documents[0].document_id == "194910"
        assert "tuyển dụng" in documents[0].display_text
        assert "194910" in str(documents[0].url)
        assert documents[1].document_id == "200001"

    async def test_empty_page_returns_empty_list(self, scraper):
        page = _make_mock_page([])

        documents = await scraper._scrape_page(page, "https://luatvietnam.vn/search")

        assert documents == []

    async def test_page_navigation_failure_returns_empty(self, scraper):
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("Network error"))

        documents = await scraper._scrape_page(page, "https://luatvietnam.vn/search")

        assert documents == []

    async def test_relative_urls_made_absolute(self, scraper):
        links = [
            (
                "/can-bo/nghi-dinh-test-12345-d1.html",
                "Test Document",
            ),
        ]
        page = _make_mock_page(links)

        documents = await scraper._scrape_page(page, "https://luatvietnam.vn/search")

        assert len(documents) == 1
        assert str(documents[0].url).startswith("https://luatvietnam.vn/")
        assert "12345" in str(documents[0].url)


class TestCollectAllDocuments:
    async def test_stops_on_empty_page(self, scraper):
        """Scraper should stop when a page returns no new documents."""
        page1_links = [
            ("/ca-phan-van-ban/Doc-111.html", "Document One"),
            ("/ca-phan-van-ban/Doc-222.html", "Document Two"),
        ]
        page2_links = []  # Empty page signals end

        call_count = 0

        async def mock_scrape_page(page, url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return await _real_scrape(page1_links)
            return []

        async def _real_scrape(links):
            from src.models import LawDocument
            from src.crawler.luatvietnam_scraper import (
                _make_absolute_url,
                _extract_luatvietnam_id,
                _clean_title,
            )
            docs = []
            for href, title in links:
                url = _make_absolute_url("https://luatvietnam.vn", href)
                docs.append(LawDocument(
                    url=url,
                    display_text=_clean_title(title),
                    document_id=_extract_luatvietnam_id(url),
                ))
            return docs

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=AsyncMock())

        with patch.object(scraper, "_scrape_page", side_effect=mock_scrape_page):
            documents = await scraper.collect_all_documents(context, max_pages=5)

        assert len(documents) == 2
        assert documents[0].document_id == "111"
        assert documents[1].document_id == "222"

    async def test_max_pages_cap(self, scraper):
        """Scraper should not exceed max_pages."""
        pages_scraped = 0

        async def mock_scrape_page(page, url):
            nonlocal pages_scraped
            pages_scraped += 1
            from src.models import LawDocument
            return [LawDocument(
                url=f"https://luatvietnam.vn/ca-phan-van-ban/Doc-{pages_scraped}.html",
                display_text=f"Doc {pages_scraped}",
                document_id=str(pages_scraped),
            )]

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=AsyncMock())

        with patch.object(scraper, "_scrape_page", side_effect=mock_scrape_page):
            documents = await scraper.collect_all_documents(context, max_pages=3)

        assert pages_scraped == 3
        assert len(documents) == 3

    async def test_deduplication(self, scraper):
        """Duplicate URLs across pages should be deduplicated."""
        call_count = 0

        async def mock_scrape_page(page, url):
            nonlocal call_count
            call_count += 1
            from src.models import LawDocument
            if call_count == 1:
                return [
                    LawDocument(
                        url="https://luatvietnam.vn/ca-phan-van-ban/Doc-111.html",
                        display_text="Doc 111",
                        document_id="111",
                    ),
                ]
            elif call_count == 2:
                # Same doc repeated + one new
                return [
                    LawDocument(
                        url="https://luatvietnam.vn/ca-phan-van-ban/Doc-111.html",
                        display_text="Doc 111",
                        document_id="111",
                    ),
                    LawDocument(
                        url="https://luatvietnam.vn/ca-phan-van-ban/Doc-222.html",
                        display_text="Doc 222",
                        document_id="222",
                    ),
                ]
            return []  # Page 3 empty → stop

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=AsyncMock())

        with patch.object(scraper, "_scrape_page", side_effect=mock_scrape_page):
            documents = await scraper.collect_all_documents(context, max_pages=5)

        assert len(documents) == 2
        ids = [doc.document_id for doc in documents]
        assert "111" in ids
        assert "222" in ids
