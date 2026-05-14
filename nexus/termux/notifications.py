"""Termux notification tool for Nexus."""

from ..tools.base import BaseTool, ToolDefinition, ToolResult


class NotificationTool(BaseTool):
    """Push notifications via Termux API."""

    name = "notify"
    description = "Show a notification on the phone (Termux only)"
    category = "system"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification title"},
                    "message": {"type": "string", "description": "Notification body"},
                    "id": {"type": "integer", "description": "Notification ID (optional)"},
                    "sound": {"type": "boolean", "description": "Play sound", "default": True},
                },
                "required": ["title", "message"],
            },
        )

    async def execute(self, title: str, message: str, id: int = 0,
                     sound: bool = True, **kwargs) -> ToolResult:
        from ..termux import get_termux_api

        api = get_termux_api()

        if not api.is_available:
            return ToolResult(
                success=False,
                content="",
                error="Not running in Termux",
            )

        success, msg = api.notify(title, message, id=id, sound=sound)
        return ToolResult(
            success=success,
            content=msg if success else "",
            error=None if success else msg,
        )
