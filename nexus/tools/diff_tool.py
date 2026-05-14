import difflib
from pathlib import Path

from ..tools.base import BaseTool, ToolDefinition, ToolResult


class InteractiveDiffTool(BaseTool):
    """Generates a unified diff for a file change and awaits human approval."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="diff_edit",
            description="Propose a change to a file. Generates a diff for the user to review and approve before applying.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to edit"},
                    "new_content": {"type": "string", "description": "The complete new content of the file"},
                },
                "required": ["path", "new_content"],
            },
            requires_permission=True,
            category="filesystem",
        )

    async def execute(self, path: str, new_content: str, **kwargs) -> ToolResult:
        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(success=False, content="", error=f"File not found: {path}")

            with open(file_path, encoding="utf-8") as f:
                old_content = f.read()

            # Generate Unified Diff
            diff = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
            diff_text = "".join(diff)

            if not diff_text:
                return ToolResult(success=True, content="No changes detected. File is already up to date.")

            # Push to the orchestrator's "pending approval" queue
            return ToolResult(
                success=True,
                content=f"PROPOSED_CHANGE\nPath: {path}\nDiff:\n{diff_text}",
                metadata={
                    "action": "require_approval",
                    "path": path,
                    "old_content": old_content,
                    "new_content": new_content,
                    "diff": diff_text
                }
            )
        except Exception as e:
            from ..utils import sanitize_error
            return ToolResult(success=False, content="", error=sanitize_error(e))
