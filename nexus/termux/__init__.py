"""Termux integration for Nexus.

Provides access to Termux API tools (notifications, clipboard, sensors, etc.)
when running on Android/Termux. Gracefully degrades on other platforms.
"""

from .api import TermuxAPI, get_termux_api
from .battery import BatteryStatus
from .clipboard import ClipboardTool
from .notifications import NotificationTool

__all__ = [
    "TermuxAPI",
    "get_termux_api",
    "ClipboardTool",
    "NotificationTool",
    "BatteryStatus",
]
