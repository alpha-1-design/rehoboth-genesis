"""Nexus Automation - Browser and API automation for web tasks."""

from .api_client import ApiAutomation, ApiFlow
from .browser import (
    BrowserAutomation,
    BrowserConfig,
    BrowserManager,
    get_browser_manager,
    is_browser_available,
)

__all__ = [
    "BrowserAutomation",
    "BrowserManager",
    "BrowserConfig",
    "get_browser_manager",
    "is_browser_available",
    "ApiAutomation",
    "ApiFlow",
]
