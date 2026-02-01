"""Main entry point for crawling Nghi dinh (decrees) from luatvietnam.vn."""

import argparse
import asyncio
import sys

from src.config import LuatVietnamConfig
from src.crawler.luatvietnam_auth import LuatVietnamAuthHandler
from src.crawler.luatvietnam_scraper import LuatVietnamScraper
from src.crawler.luatvietnam_downloader import LuatVietnamDownloader
from src.models import DownloadStatus
from src.utils import setup_logging, get_logger, random_delay

logger = get_logger(__name__)


async def test_auth(config: LuatVietnamConfig) -> bool:
    """Test authentication with luatvietnam.vn.

    Returns:
        True if authentication succeeds
    """
    logger.info("Testing authentication...")

    async with LuatVietnamAuthHandler(config) as auth:
        try:
            await auth.get_authenticated_context()
            logger.info("Authentication successful!")
            return True
        except Exception as e:
            logger.error("Authentication failed", error=str(e))
            return False


async def scrape_only(
    config: LuatVietnamConfig,
    max_pages: int | None = None,
) -> None:
    """Run scraper only — collect and print URLs without downloading.

    Args:
        config: LuatVietnam configuration
        max_pages: Optional cap on pages to scrape
    """
    async with LuatVietnamAuthHandler(config) as auth:
        context = await auth.get_authenticated_context()
        scraper = LuatVietnamScraper(config)
        documents = await scraper.collect_all_documents(
            context, max_pages=max_pages
        )

    print(f"\n=== Scraped {len(documents)} documents ===")
    for i, doc in enumerate(documents, 1):
        print(f"  {i}. [{doc.document_id}] {doc.display_text[:70]}")
        print(f"     {doc.url}")
    print("=" * 50)


async def run_crawler(
    config: LuatVietnamConfig,
    limit: int | None = None,
    scrape_max_pages: int | None = None,
) -> None:
    """Run the full scrape-then-download pipeline.

    Args:
        config: LuatVietnam configuration
        limit: Optional cap on number of documents to download
        scrape_max_pages: Optional cap on scraping pages (for testing)
    """
    async with LuatVietnamAuthHandler(config) as auth:
        context = await auth.get_authenticated_context()

        # Phase 1: Scrape all document URLs
        logger.info("Phase 1: Scraping document URLs from search results")
        scraper = LuatVietnamScraper(config)
        documents = await scraper.collect_all_documents(
            context, max_pages=scrape_max_pages
        )

        if not documents:
            logger.error("No documents scraped from search results")
            return

        logger.info("Scraping complete", total_documents=len(documents))

        # Apply download limit
        if limit:
            documents = documents[:limit]
            logger.info("Download limited", count=limit)

        print(f"\n=== Starting Download ===")
        print(f"Total: {len(documents)} documents")
        print("========================\n")

        # Phase 2: Download each document
        downloader = LuatVietnamDownloader(config)
        completed = 0
        failed = 0
        skipped = 0

        for i, doc in enumerate(documents, 1):
            logger.info(
                "Processing document",
                index=i,
                total=len(documents),
                doc_id=doc.document_id,
            )

            result = await downloader.download_document(
                context, doc, order_num=i
            )

            if result.status == DownloadStatus.COMPLETED:
                status_icon = "OK"
                completed += 1
            elif result.status == DownloadStatus.SKIPPED:
                status_icon = "SKIP"
                skipped += 1
            else:
                status_icon = "FAIL"
                failed += 1

            print(
                f"[{i}/{len(documents)}] {status_icon}: "
                f"{doc.display_text[:60]}..."
            )

            # Delay between downloads
            if i < len(documents):
                await random_delay(
                    config.request_delay_min,
                    config.request_delay_max,
                )

    # Summary
    print(f"\n=== Download Complete ===")
    print(f"Completed: {completed}")
    print(f"Failed:    {failed}")
    print(f"Skipped:   {skipped}")
    print(f"Total:     {len(documents)}")
    print("========================\n")


def main() -> int:
    """Entry point.

    Returns:
        Exit code (0 success, 1 failure)
    """
    parser = argparse.ArgumentParser(
        description="Download Nghi dinh (decrees) from luatvietnam.vn"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of documents to download",
    )
    parser.add_argument(
        "--test-auth",
        action="store_true",
        help="Test authentication only",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Scrape URLs only, do not download",
    )
    parser.add_argument(
        "--scrape-max-pages",
        type=int,
        default=None,
        help="Cap number of search result pages to scrape (for testing)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window (for debugging)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    import logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level)

    # Load configuration
    try:
        config = LuatVietnamConfig()
    except Exception as e:
        logger.error(
            "Failed to load configuration. "
            "Make sure .env has LUATVIETNAM_USER and LUATVIETNAM_PASSWORD",
            error=str(e),
        )
        return 1

    # Override headless if requested
    if args.no_headless:
        config.headless = False

    # Ensure directories exist
    config.ensure_directories()

    # Dispatch command
    try:
        if args.test_auth:
            success = asyncio.run(test_auth(config))
            return 0 if success else 1
        elif args.scrape_only:
            asyncio.run(
                scrape_only(config, max_pages=args.scrape_max_pages)
            )
            return 0
        else:
            asyncio.run(
                run_crawler(
                    config,
                    limit=args.limit,
                    scrape_max_pages=args.scrape_max_pages,
                )
            )
            return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error("Crawler failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
