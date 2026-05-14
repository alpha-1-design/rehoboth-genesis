"""TUI State Management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class MessageRole(Enum):
    USER = auto()
    ASSISTANT = auto()
    SYSTEM = auto()
    TOOL = auto()


@dataclass
class ChatMessage:
    """A chat message."""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_name: str | None = None


class ToolStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE = auto()
    ERROR = auto()


@dataclass
class ToolInfo:
    """Information about a tool execution."""

    name: str
    status: ToolStatus = ToolStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    duration_ms: int = 0


class AgentStatus(Enum):
    IDLE = auto()
    THINKING = auto()
    TOOL_USE = auto()
    WAITING = auto()
    ERROR = auto()


@dataclass
class AgentInfo:
    """Information about an active agent."""

    name: str
    role: str
    status: AgentStatus = AgentStatus.IDLE
    model: str | None = None
    current_task: str | None = None


@dataclass
class ThinkingStep:
    """A thinking step."""

    step_number: int
    description: str
    details: str = ""
    expanded: bool = True


@dataclass
class TUIState:
    """State for the TUI."""

    messages: list[ChatMessage] = field(default_factory=list)
    thinking_steps: list[ThinkingStep] = field(default_factory=list)
    active_agents: list[AgentInfo] = field(default_factory=list)
    tool_statuses: dict[str, ToolInfo] = field(default_factory=dict)
    session_id: str | None = None
    active_model: str | None = None
    is_busy: bool = False
    error: str | None = None


class TUIStateManager:
    """Manages state for the TUI and coordinates between components."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._state = TUIState()
        self._listeners: list[callable] = []
        self._initialized = True

    @property
    def state(self) -> TUIState:
        return self._state

    def reset(self) -> None:
        self._state = TUIState()

    def add_message(self, role: MessageRole, content: str, tool_calls: list[dict] | None = None, tool_name: str | None = None) -> None:
        msg = ChatMessage(
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            tool_name=tool_name,
        )
        self._state.messages.append(msg)
        self._notify()

    def add_thinking_step(self, step_number: int, description: str, details: str = "") -> None:
        step = ThinkingStep(
            step_number=step_number,
            description=description,
            details=details,
        )
        self._state.thinking_steps.append(step)
        self._notify()

    def clear_thinking(self) -> None:
        self._state.thinking_steps = []
        self._notify()

    def add_agent(self, name: str, role: str, model: str | None = None) -> None:
        agent = AgentInfo(name=name, role=role, model=model)
        self._state.active_agents.append(agent)
        self._notify()

    def update_agent_status(self, name: str, status: AgentStatus, task: str | None = None) -> None:
        for agent in self._state.active_agents:
            if agent.name == name:
                agent.status = status
                agent.current_task = task
                break
        self._notify()

    def remove_agent(self, name: str) -> None:
        self._state.active_agents = [a for a in self._state.active_agents if a.name != name]
        self._notify()

    def start_tool(self, tool_name: str) -> None:
        self._state.tool_statuses[tool_name] = ToolInfo(
            name=tool_name,
            status=ToolStatus.RUNNING,
            started_at=datetime.now(),
        )
        self._notify()

    def finish_tool(self, tool_name: str, result: str | None = None, error: str | None = None) -> None:
        if tool_name in self._state.tool_statuses:
            tool = self._state.tool_statuses[tool_name]
            tool.status = ToolStatus.DONE if not error else ToolStatus.ERROR
            tool.finished_at = datetime.now()
            tool.result = result
            tool.error = error
            if tool.started_at and tool.finished_at:
                tool.duration_ms = int((tool.finished_at - tool.started_at).total_seconds() * 1000)
        self._notify()

    def set_busy(self, busy: bool) -> None:
        self._state.is_busy = busy
        self._notify()

    def set_error(self, error: str | None) -> None:
        self._state.error = error
        self._notify()

    def set_session(self, session_id: str) -> None:
        self._state.session_id = session_id
        self._notify()

    def set_active_model(self, model: str) -> None:
        self._state.active_model = model
        self._notify()

    def subscribe(self, listener: callable) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener(self._state)


def get_state_manager() -> TUIStateManager:
    """Get the global state manager instance."""
    return TUIStateManager()
