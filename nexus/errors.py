"""Nexus error classes for structured error handling and user feedback."""


class NexusError(Exception):
    """Base class for all Nexus errors."""

    def __init__(self, message: str, user_friendly: str = None):
        super().__init__(message)
        self.user_friendly = user_friendly or message


class ToolError(NexusError):
    """Errors related to tool execution."""

    pass


class ProviderError(NexusError):
    """Errors related to LLM providers."""

    pass


class DependencyError(NexusError):
    """Errors related to missing or broken dependencies."""

    pass
