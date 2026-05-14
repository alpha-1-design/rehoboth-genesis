"""Register Termux-specific tools."""

from ..termux.clipboard import ClipboardTool
from ..termux.notifications import NotificationTool
from ..tools.base import ToolRegistry


def register_termux_tools(registry: ToolRegistry) -> None:
    """Register Termux-specific tools."""
    registry.register(ClipboardTool())
    registry.register(NotificationTool())
