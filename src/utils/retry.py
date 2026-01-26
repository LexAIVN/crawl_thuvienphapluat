"""Retry utilities with exponential backoff."""

import asyncio
import random
from functools import wraps
from typing import Callable, TypeVar, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)

from .logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def create_retry_decorator(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
):
    """Create a retry decorator with exponential backoff and jitter.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Configured retry decorator
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(
            initial=base_delay,
            max=max_delay,
            jitter=base_delay * 0.5,
        ),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
        before_sleep=lambda retry_state: logger.warning(
            "Retrying after error",
            attempt=retry_state.attempt_number,
            error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
        ),
    )


async def random_delay(min_seconds: float, max_seconds: float) -> None:
    """Add random delay to avoid rate limiting.

    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


def with_timeout(timeout_seconds: float):
    """Decorator to add timeout to async functions.

    Args:
        timeout_seconds: Maximum execution time in seconds

    Returns:
        Decorated function with timeout
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout_seconds,
            )
        return wrapper
    return decorator
