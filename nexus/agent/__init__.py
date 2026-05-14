"""Nexus Agent - Orchestrates AI interaction with tools and memory."""

from ..memory import get_memory
from ..providers import get_manager
from ..tools import get_registry
from .orchestrator import AgentConfig, AgentOrchestrator, Turn

_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the singleton agent orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator(
            provider_manager=get_manager(),
            tool_registry=get_registry(),
            memory=get_memory(),
        )
    return _orchestrator


__all__ = ["AgentOrchestrator", "AgentConfig", "Turn", "get_orchestrator"]
