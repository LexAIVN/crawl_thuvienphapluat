"""Document downloader for thuvienphapluat.vn."""

import asyncio
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, Download, TimeoutError

from ..config import CrawlerConfig
from ..models import LawDocument, DownloadStatus, sanitize_filename
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DocumentDownloader:
    """Download legal documents from thuvienphapluat.vn."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def download_document(
        self,
        context: BrowserContext,
        doc: LawDocument,
        order_num: int | None = None,
    ) -> LawDocument:
        """Download a single Vietnamese legal document.

        Args:
            context: Authenticated browser context
            doc: Document to download
            order_num: Optional order number for filename (e.g., 1, 2, 3...)

        Returns:
            Updated LawDocument with download status
        """
        async with self._semaphore:
            page = await context.new_page()
            try:
                return await self._download_with_page(page, doc, order_num)
            finally:
                await page.close()

    async def _download_with_page(
        self,
        page: Page,
        doc: LawDocument,
        order_num: int | None = None,
    ) -> LawDocument:
        """Perform download using the given page.

        Args:
            page: Browser page to use
            doc: Document to download
            order_num: Optional order number for filename

        Returns:
            Updated LawDocument with download status
        """
        logger.info(
            "Downloading document",
            doc_id=doc.document_id,
            url=str(doc.url),
        )

        try:
            # Navigate to document page
            await page.goto(
                str(doc.url),
                timeout=self.config.page_timeout,
                wait_until="networkidle",
            )

            # Wait for page to fully load
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)

            # Find and click the download tab
            download_tab = await self._find_download_tab(page)
            if not download_tab:
                logger.warning("Download tab not found", doc_id=doc.document_id)
                return doc.with_status(
                    DownloadStatus.SKIPPED,
                    error_message="Download tab not found",
                )

            await download_tab.click()
            await page.wait_for_timeout(500)

            # Find and click Vietnamese download button
            download_button = await self._find_vietnamese_download_button(page)
            if not download_button:
                logger.warning(
                    "Vietnamese download button not found",
                    doc_id=doc.document_id,
                )
                return doc.with_status(
                    DownloadStatus.SKIPPED,
                    error_message="Vietnamese download button not found",
                )

            # Start download
            async with page.expect_download(timeout=60000) as download_info:
                await download_button.click()

            download: Download = await download_info.value

            # Generate filename and save
            filename = self._generate_filename(doc, download.suggested_filename, order_num)
            save_path = self.config.download_dir / filename

            await download.save_as(str(save_path))

            logger.info(
                "Download complete",
                doc_id=doc.document_id,
                filename=filename,
            )

            return doc.with_status(
                DownloadStatus.COMPLETED,
                local_filename=filename,
            )

        except TimeoutError as e:
            logger.error(
                "Download timeout",
                doc_id=doc.document_id,
                error=str(e),
            )
            return doc.with_status(
                DownloadStatus.FAILED,
                error_message=f"Timeout: {e}",
                increment_retry=True,
            )

        except Exception as e:
            logger.error(
                "Download failed",
                doc_id=doc.document_id,
                error=str(e),
            )
            return doc.with_status(
                DownloadStatus.FAILED,
                error_message=str(e),
                increment_retry=True,
            )

    async def _find_download_tab(self, page: Page) -> Optional[any]:
        """Find the download tab on the page.

        Returns:
            Locator for download tab or None if not found
        """
        tab_selectors = [
            'text="Tải về"',
            'a:has-text("Tải về")',
            'li:has-text("Tải về")',
            '.tab-download',
            'a[href*="download"]',
            '#tab-download',
        ]

        for selector in tab_selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                continue

        return None

    async def _find_vietnamese_download_button(self, page: Page) -> Optional[any]:
        """Find the Vietnamese text download button.

        Returns:
            Locator for download button or None if not found
        """
        button_selectors = [
            'text="Tải Văn bản tiếng Việt"',
            'a:has-text("Tải Văn bản tiếng Việt")',
            'button:has-text("Tải Văn bản tiếng Việt")',
            'a:has-text("Văn bản tiếng Việt")',
            'text="Văn bản tiếng Việt"',
            '.download-vietnamese',
            'a[href*=".doc"]',
            'a[href*="download"][href*="vn"]',
        ]

        for selector in button_selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                continue

        return None

    def _generate_filename(
        self,
        doc: LawDocument,
        suggested: Optional[str],
        order_num: int | None = None,
    ) -> str:
        """Generate unique filename for downloaded document.

        Format: {order_num}_{sanitized_title}.{extension}
        Example: 1_Luat_Thue_gia_tri_gia_tang.doc

        Args:
            doc: Document being downloaded
            suggested: Browser-suggested filename
            order_num: Order number for sequential naming

        Returns:
            Generated filename
        """
        # Get extension from suggested filename or default to .doc
        ext = ".doc"
        if suggested:
            path = Path(suggested)
            if path.suffix:
                ext = path.suffix

        # Sanitize display text for filename
        sanitized = sanitize_filename(doc.display_text, max_length=80)

        # Use order number if provided, otherwise use document_id
        if order_num is not None:
            return f"{order_num}_{sanitized}{ext}"
        return f"{doc.document_id}_{sanitized}{ext}"

    async def add_random_delay(self) -> None:
        """Add random delay between requests to avoid rate limiting."""
        delay = random.uniform(
            self.config.request_delay_min,
            self.config.request_delay_max,
        )
        await asyncio.sleep(delay)


async def check_rate_limit(page: Page) -> bool:
    """Check if we've been rate limited.

    Returns:
        True if rate limited, False otherwise
    """
    indicators = [
        'text="Bạn đã gửi quá nhiều yêu cầu"',
        'text="Too many requests"',
        'text="Vui lòng thử lại sau"',
        'text="Rate limit"',
    ]

    for indicator in indicators:
        try:
            if await page.locator(indicator).count() > 0:
                return True
        except Exception:
            continue

    return False
