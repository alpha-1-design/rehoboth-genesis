"""Tool system for Nexus.

Tools are the capabilities that the agent can use to interact with the world.
Each tool has a name, description, schema, and execution function.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """Definition of a tool for the AI model."""

    name: str
    description: str
    input_schema: dict[str, Any]
    requires_permission: bool = False
    category: str = "general"


@dataclass
class ToolResult:
    """Result from executing a tool."""

    success: bool
    content: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Base class for all tools."""

    def __init__(self):
        self._execution_count = 0

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool definition for the AI model."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given arguments."""
        pass

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.definition.name,
                "description": self.definition.description,
                "parameters": self.definition.input_schema,
            },
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.definition.name,
            "description": self.definition.description,
            "input_schema": self.definition.input_schema,
        }

    @property
    def needs_permission(self) -> bool:
        """Whether this tool requires user permission before execution."""
        return self.definition.requires_permission


class ToolRegistry:
    """Registry of all available tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.definition.name] = tool
        category = tool.definition.category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(tool.definition.name)

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> list[ToolDefinition]:
        """List all tool definitions."""
        return [tool.definition for tool in self._tools.values()]

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """List tools in a specific category."""
        names = self._categories.get(category, [])
        return [self._tools[name].definition for name in names if name in self._tools]

    def get_categories(self) -> list[str]:
        """Get all tool categories."""
        return list(self._categories.keys())

    def to_openai_format(self) -> list[dict[str, Any]]:
        """Convert all tools to OpenAI format."""
        return [tool.to_openai_format() for tool in self._tools.values()]

    def to_anthropic_format(self) -> list[dict[str, Any]]:
        """Convert all tools to Anthropic format."""
        return [tool.to_anthropic_format() for tool in self._tools.values()]

    def filter_by_permission(
        self,
        allowed: set[str] | None = None,
        denied: set[str] | None = None,
        ask: set[str] | None = None,
    ) -> "ToolRegistry":
        """Filter tools based on permission rules."""
        filtered = ToolRegistry()

        for name, tool in self._tools.items():
            if denied and name in denied:
                continue
            if allowed and name not in allowed:
                continue
            filtered.register(tool)

        return filtered


# Global registry
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_core_tools(_registry)
    return _registry


def _register_core_tools(registry: ToolRegistry) -> None:
    """Register all core tools."""
    from . import core as core_tools

    core_tools.register_all(registry)
    try:
        from ..termux import registry as termux_registry

        termux_registry.register_termux_tools(registry)
    except Exception:
        pass
