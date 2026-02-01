"""Document downloader for luatvietnam.vn."""

import asyncio
import zipfile
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, Download, TimeoutError

from ..config import LuatVietnamConfig
from ..models import LawDocument, DownloadStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LuatVietnamDownloader:
    """Download legal documents from luatvietnam.vn.

    Download flow per document:
        1. Navigate to detail URL with #taive hash (scrolls to download section)
        2. Click "Tải tất cả" button → receives a ZIP containing the decree + appendices
        3. Extract ZIP contents into download_dir
    """

    def __init__(self, config: LuatVietnamConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def download_document(
        self,
        context: BrowserContext,
        doc: LawDocument,
        order_num: int | None = None,
    ) -> LawDocument:
        """Download a single document with semaphore-controlled concurrency.

        Args:
            context: Authenticated browser context
            doc: Document to download
            order_num: Optional order number for filename prefix

        Returns:
            New LawDocument with updated status (immutable)
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
        """Execute the download flow on a single page.

        Args:
            page: Browser page to use
            doc: Document to download
            order_num: Optional order number for filename prefix

        Returns:
            New LawDocument with updated status
        """
        logger.info(
            "Downloading document",
            doc_id=doc.document_id,
            url=str(doc.url),
        )

        try:
            # Navigate to detail page with #taive hash
            detail_url = str(doc.url).split("#")[0] + "#taive"
            await page.goto(
                detail_url,
                timeout=self.config.page_timeout,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)

            # Click "Tải tất cả" (Download All) button
            download_all = page.locator('[data-role="download-all"]')
            if await download_all.count() == 0:
                logger.warning(
                    "Tải tất cả button not found", doc_id=doc.document_id
                )
                return doc.with_status(
                    DownloadStatus.SKIPPED,
                    error_message="Tải tất cả button not found",
                )

            # Click and capture ZIP download
            async with page.expect_download(timeout=60000) as download_info:
                await download_all.first.click()

            download: Download = await download_info.value

            # Save ZIP to a temp location, then extract
            zip_path = self.config.download_dir / f"_tmp_{doc.document_id}.zip"
            await download.save_as(str(zip_path))

            extracted = _extract_zip(zip_path, self.config.download_dir, order_num)
            zip_path.unlink()

            logger.info(
                "Download and extraction complete",
                doc_id=doc.document_id,
                files=extracted,
            )

            return doc.with_status(
                DownloadStatus.COMPLETED,
                local_filename="; ".join(extracted),
            )

        except TimeoutError as e:
            logger.error(
                "Download timeout", doc_id=doc.document_id, error=str(e)
            )
            return doc.with_status(
                DownloadStatus.FAILED,
                error_message=f"Timeout: {e}",
                increment_retry=True,
            )

        except Exception as e:
            logger.error(
                "Download failed", doc_id=doc.document_id, error=str(e)
            )
            return doc.with_status(
                DownloadStatus.FAILED,
                error_message=str(e),
                increment_retry=True,
            )


def _extract_zip(
    zip_path: Path,
    dest_dir: Path,
    order_num: int | None = None,
) -> list[str]:
    """Extract ZIP contents into dest_dir, optionally prefixing filenames.

    Files inside the ZIP may be nested in a single subfolder (common with
    "download all" ZIPs). Contents are extracted flat into dest_dir.

    Args:
        zip_path: Path to the downloaded ZIP file
        dest_dir: Target directory for extracted files
        order_num: Optional prefix number for extracted filenames

    Returns:
        List of extracted filenames (relative to dest_dir)
    """
    extracted: list[str] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            # Skip directories
            if name.endswith("/"):
                continue

            # Use only the filename part (strip any folder prefix inside ZIP)
            filename = Path(name).name
            if not filename:
                continue

            if order_num is not None:
                filename = f"{order_num}_{filename}"

            target = dest_dir / filename
            with zf.open(name) as src, open(target, "wb") as dst:
                dst.write(src.read())

            extracted.append(filename)

    return extracted
