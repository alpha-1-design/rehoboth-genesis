"""Termux clipboard tool for Nexus tools system."""

from ..tools.base import BaseTool, ToolDefinition, ToolResult


class ClipboardTool(BaseTool):
    """Clipboard operations via Termux API or fallback."""

    name = "Clipboard"
    description = "Read or write the system clipboard"
    category = "system"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get", "set"],
                        "description": "get: read clipboard, set: write to clipboard",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to copy (required for action=set)",
                    },
                },
                "required": ["action"],
            },
        )

    async def execute(self, action: str, text: str | None = None, **kwargs) -> ToolResult:
        from ..termux import get_termux_api

        api = get_termux_api()

        if action == "get":
            success, content = api.clipboard_get()
            return ToolResult(
                success=success,
                content=content if success else "",
                error=None if success else content,
            )

        elif action == "set":
            if not text:
                return ToolResult(success=False, content="", error="No text provided")
            success, msg = api.clipboard_set(text)
            return ToolResult(
                success=success,
                content=msg if success else "",
                error=None if success else msg,
            )

        return ToolResult(success=False, content="", error=f"Unknown action: {action}")
