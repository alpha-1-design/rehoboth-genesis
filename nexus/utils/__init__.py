"""Utilities for Nexus."""

import asyncio
import logging
import re
import sys
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger


def run_async(coro: Any) -> Any:
    """Run an async function in a sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to a maximum length."""
    if len(text) <= length:
        return text
    return text[: length - len(suffix)] + suffix


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Return singular or plural form based on count."""
    if count == 1:
        return singular
    return plural or singular + "s"


SENSITIVE_PATTERNS = [
    (
        re.compile(r'\b([a-zA-Z0-9_-]*key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{8,})', re.I),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\b(bearer\s+)([a-zA-Z0-9_\-\.]{10,})", re.I), r"\1[REDACTED]"),
    (re.compile(r"\b(ghp_[a-zA-Z0-9]{36})\b"), "[GITHUB_TOKEN]"),
    (re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"), "[API_KEY]"),
    (re.compile(r"\b(xai-[a-zA-Z0-9_-]{20,})\b"), "[XAI_KEY]"),
    (re.compile(r"/home/[a-zA-Z0-9_]+/"), "/home/[USER]/"),
    (re.compile(r"C:\\Users\\[a-zA-Z0-9_]+\\"), r"C:\\Users\\[USER]\\"),
]


def sanitize_error(error: str | Exception, max_length: int = 200) -> str:
    """Sanitize an error message to prevent information disclosure."""
    if isinstance(error, Exception):
        error = str(error)

    sanitized = error
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized


from ..errors import NexusError

def format_error(error: Exception | str) -> str:
    """Format an exception or error string into a user-friendly message."""
    if isinstance(error, NexusError):
        return error.user_friendly
    if isinstance(error, Exception):
        msg = str(error)
        if "timeout" in msg.lower():
            return "The request timed out. Please check your connection and try again."
        elif "not found" in msg.lower():
            return "The requested resource was not found."
        return f"An unexpected error occurred: {truncate(msg, 50)}"
    return str(error)
