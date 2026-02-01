"""Pagination scraper for luatvietnam.vn search results.

Collects all Nghi dinh (decree) document URLs from the paginated search
results page and returns them as LawDocument objects.
"""

import re
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from playwright.async_api import BrowserContext, Page

from ..config import LuatVietnamConfig
from ..models import LawDocument
from ..utils.logger import get_logger
from ..utils.retry import random_delay

logger = get_logger(__name__)


class LuatVietnamScraper:
    """Scrape paginated search results from luatvietnam.vn.

    Iterates through pages of search results, extracting document URLs
    and titles. Stops when a page yields no new documents.
    """

    def __init__(self, config: LuatVietnamConfig):
        self.config = config

    async def collect_all_documents(
        self,
        context: BrowserContext,
        max_pages: Optional[int] = None,
    ) -> list[LawDocument]:
        """Scrape all pages of search results.

        Args:
            context: Authenticated browser context
            max_pages: Optional safety cap on pages to scrape (None = no limit)

        Returns:
            Deduplicated list of LawDocument objects
        """
        all_documents: list[LawDocument] = []
        page_number = 1
        seen_urls: set[str] = set()

        while True:
            if max_pages is not None and page_number > max_pages:
                logger.info("Reached max_pages cap", max_pages=max_pages)
                break

            search_url = self._build_paginated_url(page_number)
            logger.info("Scraping search results", page=page_number, url=search_url)

            page = await context.new_page()
            try:
                documents_on_page = await self._scrape_page(page, search_url)
            finally:
                await page.close()

            # Deduplicate by URL
            new_documents: list[LawDocument] = []
            for doc in documents_on_page:
                url_str = str(doc.url)
                if url_str not in seen_urls:
                    seen_urls.add(url_str)
                    new_documents.append(doc)

            if not new_documents:
                logger.info(
                    "No new documents found, scraping complete",
                    total_pages=page_number - 1,
                )
                break

            all_documents.extend(new_documents)
            logger.info(
                "Page scraped",
                page=page_number,
                new_on_page=len(new_documents),
                total_so_far=len(all_documents),
            )

            page_number += 1

            # Polite delay between pagination requests
            await random_delay(
                self.config.scrape_delay_min,
                self.config.scrape_delay_max,
            )

        logger.info("Scraping complete", total_documents=len(all_documents))
        return all_documents

    async def _scrape_page(self, page: Page, url: str) -> list[LawDocument]:
        """Scrape a single search results page.

        Args:
            page: Browser page to use
            url: Full paginated search URL

        Returns:
            List of LawDocument objects found on this page
        """
        try:
            await page.goto(
                url, timeout=self.config.page_timeout, wait_until="domcontentloaded"
            )
            await page.wait_for_timeout(3000)
        except Exception as e:
            logger.error("Failed to load search page", url=url, error=str(e))
            return []

        # luatvietnam.vn document detail URLs follow patterns like:
        #   /can-bo/nghi-dinh-138-2020-...-194910-d1.html
        #   /phan-van-ban/nghi-dinh-...-NNNNNN-dN.html
        # Links are filtered to only those whose href contains a numeric
        # document ID (pattern: -NNNNNN-dN.html or -NNNNNN.html).
        link_selectors = [
            'a[href$=".html"][href*="nghi-dinh"]',
            'a[href$=".html"][href*="Nghi-dinh"]',
            'a[href*="/can-bo/"][href$=".html"]',
            'a[href*="/phan-van-ban/"][href$=".html"]',
            'a[href*="/ca-phan-van-ban/"][href$=".html"]',
        ]

        extracted_links: list[tuple[str, str]] = []

        for selector in link_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                if count > 0:
                    for i in range(count):
                        element = locator.nth(i)
                        href = await element.get_attribute("href")
                        title = await element.text_content()
                        if href and title:
                            # Only keep document detail links (numeric ID in href)
                            if re.search(r"-\d+-d\d+\.html$", href) or re.search(r"-\d+\.html$", href):
                                extracted_links.append((href.strip(), title.strip()))
                    if extracted_links:
                        logger.debug(
                            "Links extracted",
                            selector=selector,
                            count=len(extracted_links),
                        )
                        break
            except Exception:
                continue

        # Build LawDocument for each link
        documents: list[LawDocument] = []
        base_url = self.config.base_url

        for href, title in extracted_links:
            absolute_url = _make_absolute_url(base_url, href)
            doc_id = _extract_luatvietnam_id(absolute_url)
            clean_title = _clean_title(title)

            if not doc_id or not clean_title:
                continue

            documents.append(
                LawDocument(
                    url=absolute_url,
                    display_text=clean_title,
                    document_id=doc_id,
                )
            )

        return documents

    def _build_paginated_url(self, page_number: int) -> str:
        """Build the search URL with PageIndex and PageSize parameters.

        Args:
            page_number: 1-based page number

        Returns:
            Full URL string with pagination parameters
        """
        parsed = urlparse(self.config.search_url)
        params = parse_qs(parsed.query, keep_blank_values=True)

        params["PageIndex"] = [str(page_number)]
        params["PageSize"] = ["20"]

        new_query = urlencode(params, doseq=True)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        ))


def _make_absolute_url(base_url: str, href: str) -> str:
    """Convert a relative href to an absolute URL.

    Args:
        base_url: e.g. "https://luatvietnam.vn"
        href: Relative or absolute path

    Returns:
        Absolute URL string
    """
    if href.startswith("http://") or href.startswith("https://"):
        return href
    base = base_url.rstrip("/")
    href = href.lstrip("/")
    return f"{base}/{href}"


def _extract_luatvietnam_id(url: str) -> str:
    """Extract numeric document ID from a luatvietnam.vn URL.

    Supported patterns:
        .../nghi-dinh-138-2020-ND-CP-194910-d1.html  -> "194910"
        .../nghi-dinh-138-2020-ND-CP-199498.html     -> "199498"

    The site uses -NNNNNN-dN.html (with version suffix) as primary format.
    Falls back to hash if no pattern matches.

    Args:
        url: Full document URL

    Returns:
        Document ID string
    """
    # Primary: -NNNNNN-dN.html (versioned document ID)
    match = re.search(r"-(\d+)-d\d+\.html$", url)
    if match:
        return match.group(1)

    # Fallback: -NNNNNN.html (non-versioned)
    match = re.search(r"-(\d+)\.html$", url)
    if match:
        return match.group(1)

    return str(hash(url) & 0xFFFFFFFF)


def _clean_title(raw_title: str) -> str:
    """Clean extracted title text for use as display_text.

    Collapses whitespace, strips numbering prefixes and bullet characters.

    Args:
        raw_title: Raw text content from the link element

    Returns:
        Cleaned title string
    """
    title = " ".join(raw_title.split())
    title = re.sub(r"^\d+\.\s*", "", title)
    title = re.sub(r"^[-\u2013\u2022]\s*", "", title)
    return title.strip()
