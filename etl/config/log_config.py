"""
Logging configuration for ETL scripts.

Loguru writes to stderr by default, which causes Kestra UI to label
all log output as ERROR regardless of actual level. This module
redirects loguru to stdout so Kestra displays correct log levels.

Usage (call once at script entry point):
    from etl.config.log_config import setup_logging
    setup_logging()
"""
from __future__ import annotations

import sys

from loguru import logger


def setup_logging(level: str = "DEBUG") -> None:
    """Configure loguru to write to stdout instead of stderr.

    Args:
        level: Minimum log level to display (default: DEBUG).
    """
    # Remove default stderr handler
    logger.remove()

    # Add stdout handler with clean format
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        ),
        colorize=False,  # No ANSI colors in container logs
    )
