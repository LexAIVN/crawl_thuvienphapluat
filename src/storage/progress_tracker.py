"""Progress tracking for resume capability."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..models import LawDocument, DownloadStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ProgressTracker:
    """Track download progress with persistence for resume capability."""

    def __init__(self, progress_file: str | Path = "progress.json"):
        self.progress_file = Path(progress_file)
        self._documents: Dict[str, LawDocument] = {}
        self._load()

    def _load(self) -> None:
        """Load progress from file."""
        if not self.progress_file.exists():
            logger.info("No existing progress file found")
            return

        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._documents = {
                url: LawDocument(**doc_data) for url, doc_data in data.items()
            }
            logger.info(
                "Loaded progress",
                total=len(self._documents),
                completed=self.completed_count,
            )
        except Exception as e:
            logger.error("Failed to load progress", error=str(e))
            self._documents = {}

    def save(self) -> None:
        """Persist progress to file."""
        try:
            data = {
                url: self._serialize_document(doc)
                for url, doc in self._documents.items()
            }
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            logger.debug("Progress saved", total=len(self._documents))
        except Exception as e:
            logger.error("Failed to save progress", error=str(e))

    def _serialize_document(self, doc: LawDocument) -> dict:
        """Serialize document for JSON storage."""
        return {
            "url": str(doc.url),
            "display_text": doc.display_text,
            "document_id": doc.document_id,
            "status": doc.status.value,
            "local_filename": doc.local_filename,
            "error_message": doc.error_message,
            "retry_count": doc.retry_count,
            "last_attempt": doc.last_attempt.isoformat() if doc.last_attempt else None,
        }

    def initialize(self, documents: List[LawDocument]) -> None:
        """Initialize tracker with documents.

        Only adds documents that don't already exist in tracker.

        Args:
            documents: List of documents to track
        """
        added = 0
        for doc in documents:
            url_key = str(doc.url)
            if url_key not in self._documents:
                self._documents[url_key] = doc
                added += 1

        logger.info(
            "Initialized progress tracker",
            new_documents=added,
            existing_documents=len(documents) - added,
            total=len(self._documents),
        )
        self.save()

    def has_documents(self) -> bool:
        """Check if tracker has any documents."""
        return len(self._documents) > 0

    def get_document(self, url: str) -> Optional[LawDocument]:
        """Get document by URL."""
        return self._documents.get(url)

    def update_document(self, doc: LawDocument) -> None:
        """Update document status (immutable pattern).

        Args:
            doc: Updated document
        """
        url_key = str(doc.url)
        self._documents = {
            **self._documents,
            url_key: doc,
        }
        self.save()

    def get_pending_documents(self, max_retries: int = 3) -> List[LawDocument]:
        """Get documents that need processing.

        Args:
            max_retries: Maximum retry attempts before giving up

        Returns:
            List of documents pending download
        """
        return [
            doc
            for doc in self._documents.values()
            if doc.status in (DownloadStatus.PENDING, DownloadStatus.FAILED)
            and doc.retry_count < max_retries
        ]

    def all_documents(self) -> List[LawDocument]:
        """Get all documents."""
        return list(self._documents.values())

    @property
    def total_count(self) -> int:
        """Total number of documents."""
        return len(self._documents)

    @property
    def completed_count(self) -> int:
        """Number of completed downloads."""
        return sum(
            1 for doc in self._documents.values()
            if doc.status == DownloadStatus.COMPLETED
        )

    @property
    def failed_count(self) -> int:
        """Number of failed downloads (max retries reached)."""
        return sum(
            1 for doc in self._documents.values()
            if doc.status == DownloadStatus.FAILED and doc.retry_count >= 3
        )

    @property
    def skipped_count(self) -> int:
        """Number of skipped downloads."""
        return sum(
            1 for doc in self._documents.values()
            if doc.status == DownloadStatus.SKIPPED
        )

    @property
    def pending_count(self) -> int:
        """Number of pending downloads."""
        return sum(
            1 for doc in self._documents.values()
            if doc.status == DownloadStatus.PENDING
        )

    def get_summary(self) -> Dict[str, int]:
        """Get progress summary.

        Returns:
            Dictionary with status counts
        """
        return {
            "total": self.total_count,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "skipped": self.skipped_count,
            "pending": self.pending_count,
        }

    def print_summary(self) -> None:
        """Print progress summary to console."""
        summary = self.get_summary()
        print("\n=== Download Progress ===")
        print(f"Total:     {summary['total']}")
        print(f"Completed: {summary['completed']}")
        print(f"Failed:    {summary['failed']}")
        print(f"Skipped:   {summary['skipped']}")
        print(f"Pending:   {summary['pending']}")
        print("========================\n")
