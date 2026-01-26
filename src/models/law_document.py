"""Data models for law documents."""

import re
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class DownloadStatus(str, Enum):
    """Status of document download."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class LawDocument(BaseModel):
    """Represents a legal document to be downloaded."""

    url: HttpUrl
    display_text: str
    document_id: str

    # Download state
    status: DownloadStatus = DownloadStatus.PENDING
    local_filename: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    last_attempt: Optional[datetime] = None

    @field_validator("document_id", mode="before")
    @classmethod
    def extract_document_id(cls, v: str, info) -> str:
        """Extract or validate document ID."""
        if v:
            return v
        # Extract from URL if not provided
        url = info.data.get("url", "")
        return extract_id_from_url(str(url))

    def with_status(
        self,
        status: DownloadStatus,
        *,
        local_filename: Optional[str] = None,
        error_message: Optional[str] = None,
        increment_retry: bool = False,
    ) -> "LawDocument":
        """Return new document with updated status (immutable)."""
        return LawDocument(
            url=self.url,
            display_text=self.display_text,
            document_id=self.document_id,
            status=status,
            local_filename=local_filename or self.local_filename,
            error_message=error_message,
            retry_count=self.retry_count + 1 if increment_retry else self.retry_count,
            last_attempt=datetime.now(),
        )


def extract_id_from_url(url: str) -> str:
    """Extract document ID from thuvienphapluat.vn URL.

    Examples:
        https://thuvienphapluat.vn/van-ban/Doanh-nghiep/Luat-Doanh-nghiep-2020-68-2020-QH14-375519.aspx
        -> 375519
    """
    # Try to extract numeric ID from end of URL path
    match = re.search(r"-(\d+)\.aspx$", url)
    if match:
        return match.group(1)

    # Try to extract from URL slug
    match = re.search(r"/([^/]+)\.aspx$", url)
    if match:
        return match.group(1)

    # Fallback: use hash of URL
    return str(hash(url) & 0xFFFFFFFF)


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Sanitize string for use as filename.

    Args:
        name: Original string
        max_length: Maximum length of result

    Returns:
        Sanitized string safe for filesystem
    """
    # Remove/replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    result = name
    for char in invalid_chars:
        result = result.replace(char, "_")

    # Replace spaces and special chars
    result = result.replace(" ", "_")

    # Remove consecutive underscores
    while "__" in result:
        result = result.replace("__", "_")

    # Limit length and strip underscores
    return result[:max_length].strip("_")
