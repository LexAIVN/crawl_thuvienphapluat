"""Logging configuration."""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog


def setup_logging(
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
) -> None:
    """Configure structured logging.

    Args:
        log_dir: Directory for log files (optional)
        level: Logging level
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Use different renderer based on environment
    if sys.stderr.isatty():
        # Pretty output for terminal
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON output for files/CI
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set up file handler if log_dir provided
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / "crawler.log",
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger
    """
    return structlog.get_logger(name)
