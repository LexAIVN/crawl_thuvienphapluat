"""Main entry point for the law document crawler."""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from src.config import CrawlerConfig
from src.crawler import AuthHandler, DocumentDownloader
from src.extractors import extract_hyperlinks_from_txt
from src.models import DownloadStatus, LawDocument
from src.storage import ProgressTracker
from src.utils import setup_logging, get_logger, random_delay

logger = get_logger(__name__)


def extract_urls_with_order(txt_path: Path) -> list[tuple[int, LawDocument]]:
    """Extract URLs from text file with their order numbers.

    Args:
        txt_path: Path to the text file

    Returns:
        List of (order_number, LawDocument) tuples
    """
    from src.models import extract_id_from_url

    documents = []

    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Parse line format: "1. https://..."
            match = re.match(r"^(\d+)\.\s*(https?://[^\s]+)", line)
            if not match:
                continue

            order_num = int(match.group(1))
            url = match.group(2)

            if "thuvienphapluat.vn" not in url:
                continue

            # Extract display text from URL
            path = url.split("/")[-1]
            name = path.replace(".aspx", "")
            parts = name.rsplit("-", 1)
            if len(parts) == 2 and parts[1].isdigit():
                name = parts[0]
            display_text = name.replace("-", " ")

            doc_id = extract_id_from_url(url)

            doc = LawDocument(
                url=url,
                display_text=display_text,
                document_id=doc_id,
            )
            documents.append((order_num, doc))

    return documents


async def test_auth(config: CrawlerConfig) -> bool:
    """Test authentication with the website.

    Returns:
        True if authentication successful
    """
    logger.info("Testing authentication...")

    async with AuthHandler(config) as auth:
        try:
            await auth.get_authenticated_context()
            logger.info("Authentication successful!")
            return True
        except Exception as e:
            logger.error("Authentication failed", error=str(e))
            return False


async def run_crawler(
    config: CrawlerConfig,
    source_path: Path,
    limit: int | None = None,
) -> None:
    """Run the document crawler.

    Args:
        config: Crawler configuration
        source_path: Path to source file (txt or docx)
        limit: Optional limit on number of documents to download
    """
    # Extract URLs with order numbers from txt file
    logger.info("Extracting URLs from file", path=str(source_path))
    ordered_docs = extract_urls_with_order(source_path)
    logger.info("Extracted documents", count=len(ordered_docs))

    if not ordered_docs:
        logger.error("No documents found in file")
        return

    # Apply limit if specified
    if limit:
        ordered_docs = ordered_docs[:limit]
        logger.info("Limited to documents", count=limit)

    print(f"\n=== Starting Download ===")
    print(f"Total: {len(ordered_docs)} documents")
    print("========================\n")

    # Initialize authentication and downloader
    async with AuthHandler(config) as auth:
        context = await auth.get_authenticated_context()
        downloader = DocumentDownloader(config)

        completed = 0
        failed = 0
        skipped = 0

        for i, (order_num, doc) in enumerate(ordered_docs, 1):
            logger.info(
                "Processing document",
                index=i,
                total=len(ordered_docs),
                order_num=order_num,
                doc_id=doc.document_id,
            )

            # Download document with order number
            result = await downloader.download_document(context, doc, order_num)

            # Log result
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
                f"[{i}/{len(ordered_docs)}] {status_icon}: "
                f"{order_num}_{doc.display_text[:50]}..."
            )

            # Add delay between requests
            if i < len(ordered_docs):
                await random_delay(
                    config.request_delay_min,
                    config.request_delay_max,
                )

    # Print final summary
    print(f"\n=== Download Complete ===")
    print(f"Completed: {completed}")
    print(f"Failed:    {failed}")
    print(f"Skipped:   {skipped}")
    print(f"Total:     {len(ordered_docs)}")
    print("========================\n")


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Download Vietnamese legal documents from thuvienphapluat.vn"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("src/data.txt"),
        help="Path to source file with URLs (default: src/data.txt)",
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
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window",
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
        config = CrawlerConfig()
    except Exception as e:
        logger.error(
            "Failed to load configuration. "
            "Make sure .env file exists with CRAWLER_USERNAME and CRAWLER_PASSWORD",
            error=str(e),
        )
        return 1

    # Override headless setting
    if args.no_headless:
        config.headless = False

    # Ensure directories exist
    config.ensure_directories()

    # Run appropriate command
    try:
        if args.test_auth:
            success = asyncio.run(test_auth(config))
            return 0 if success else 1
        else:
            if not args.source.exists():
                logger.error("Source file not found", path=str(args.source))
                return 1

            asyncio.run(run_crawler(config, args.source, args.limit))
            return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error("Crawler failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
