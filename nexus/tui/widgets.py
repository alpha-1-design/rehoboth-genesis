"""Reusable widgets for the Nexus TUI."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static

from .state import (
    AgentInfo,
    AgentStatus,
    ChatMessage,
    MessageRole,
    ThinkingStep,
    ToolInfo,
    ToolStatus,
)


class ChatMessageWidget(Container):
    """Displays a single chat message with atmospheric styling."""

    def __init__(self, message: ChatMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        timestamp = self.message.timestamp.strftime("%H:%M:%S")

        if self.message.role == MessageRole.USER:
            role_display = "[bold cyan]USER[/]"
            prefix = "╼"
        elif self.message.role == MessageRole.ASSISTANT:
            role_display = "[bold purple]NEXUS[/]"
            prefix = "╾"
        elif self.message.role == MessageRole.SYSTEM:
            role_display = "[dim]SYST[/]"
            prefix = "•"
        else:
            role_display = "[bold blue]TOOL[/]"
            prefix = "⚙"

        yield Horizontal(
            Static(f"[dim]{timestamp}[/] {prefix} ", classes="timestamp"),
            Static(role_display, classes="role"),
            Static(self._format_content(), classes="content", markup=True),
            classes="message-row",
        )

    def _format_content(self) -> str:
        content = self.message.content
        if self.message.tool_name:
            content = f"[tool: {self.message.tool_name}] {content}"
        if self.message.tool_calls:
            for tc in self.message.tool_calls:
                content += f"\n[tool call: {tc.get('name', 'unknown')}]"
        return content


class ChatPanel(Vertical):
    """Scrollable chat history panel."""

    def __init__(self, messages: list[ChatMessage] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._messages = messages or []

    def compose(self) -> ComposeResult:
        yield Static("Chat History", classes="panel-header")
        with Vertical(id="messages-container"):
            pass

    def add_message(self, message: ChatMessage) -> None:
        self._messages.append(message)
        widget = ChatMessageWidget(message)
        self.query_one("#messages-container").mount(widget)
        self.scroll_end()

    def clear(self) -> None:
        self._messages = []
        container = self.query_one("#messages-container")
        container.remove_children()


class ThinkingBlock(Container):
    """A thinking step with expand/collapse."""

    expanded = reactive(True)

    def __init__(self, step: ThinkingStep, **kwargs):
        super().__init__(**kwargs)
        self.step = step

    def compose(self) -> ComposeResult:
        icon = "▼" if self.expanded else "▶"
        yield Horizontal(
            Static(f"[bold cyan]{icon}[/] [dim]#{self.step.step_number}[/]", classes="step-number"),
            Static(self.step.description, classes="step-description"),
        )
        if self.expanded and self.step.details:
            yield Static(f"   [dim]{self.step.details}[/]", classes="step-details")

    def on_click(self) -> None:
        self.expanded = not self.expanded
        self.refresh()


class ThinkingPanel(Vertical):
    """Panel showing structured thinking steps."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._steps: list[ThinkingStep] = []

    def compose(self) -> ComposeResult:
        yield Static("Thinking", classes="panel-header")
        with Vertical(id="thinking-container"):
            pass

    def add_step(self, step: ThinkingStep) -> None:
        self._steps.append(step)
        widget = ThinkingBlock(step)
        self.query_one("#thinking-container").mount(widget)

    def clear(self) -> None:
        self._steps = []
        container = self.query_one("#thinking-container")
        container.remove_children()


class ToolStatusWidget(Static):
    """Displays a tool's execution status."""

    def __init__(self, tool: ToolInfo, **kwargs):
        super().__init__(**kwargs)
        self.tool = tool

    def render(self) -> str:
        status_icon = {
            ToolStatus.PENDING: "[dim]○[/]",
            ToolStatus.RUNNING: "[bold cyan]◎[/]",
            ToolStatus.DONE: "[bold green]●[/]",
            ToolStatus.ERROR: "[bold red]✗[/]",
        }.get(self.tool.status, "[?]")

        duration_str = f" [dim]{self.tool.duration_ms}ms[/]" if self.tool.duration_ms else ""
        return f"{status_icon} {self.tool.name}{duration_str}"


class ToolPanel(Vertical):
    """Panel showing tool execution status."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tools: dict[str, ToolInfo] = {}

    def compose(self) -> ComposeResult:
        yield Static("Tools", classes="panel-header")
        with Vertical(id="tools-container"):
            pass

    def update_tool(self, tool: ToolInfo) -> None:
        self._tools[tool.name] = tool
        container = self.query_one("#tools-container")

        existing = container.query(f"#tool-{tool.name}")
        if existing:
            existing.remove()

        widget = ToolStatusWidget(tool, id=f"tool-{tool.name}")
        container.mount(widget)

    def clear(self) -> None:
        self._tools = {}
        container = self.query_one("#tools-container")
        container.remove_children()


class AgentCard(Static):
    """Displays an agent's status."""

    def __init__(self, agent: AgentInfo, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    def render(self) -> str:
        status_icon = {
            AgentStatus.IDLE: "[dim]💤[/]",
            AgentStatus.THINKING: "[bold cyan]🧠[/]",
            AgentStatus.TOOL_USE: "[bold yellow]🛠️[/]",
            AgentStatus.WAITING: "[dim]⏳[/]",
            AgentStatus.ERROR: "[bold red]⚠️[/]",
        }.get(self.agent.status, "?")

        model_str = f" [dim]({self.agent.model})[/]" if self.agent.model else ""
        return f"{status_icon} {self.agent.name}{model_str}"


class AgentsPanel(Vertical):
    """Panel showing active agents."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._agents: list[AgentInfo] = []

    def compose(self) -> ComposeResult:
        yield Static("Agents", classes="panel-header")
        with Vertical(id="agents-container"):
            pass

    def update_agent(self, agent: AgentInfo) -> None:
        found = False
        for i, a in enumerate(self._agents):
            if a.name == agent.name:
                self._agents[i] = agent
                found = True
                break

        if not found:
            self._agents.append(agent)

        container = self.query_one("#agents-container")
        existing = container.query(f"#agent-{agent.name}")
        if existing:
            existing.remove()

        widget = AgentCard(agent, id=f"agent-{agent.name}")
        container.mount(widget)

    def clear(self) -> None:
        self._agents = []
        container = self.query_one("#agents-container")
        container.remove_children()


class ProgressBar(Static):
    """ASCII-style progress bar."""

    percent = reactive(0.0)
    width = 20

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self) -> str:
        filled = int(self.percent / 100 * self.width)
        bar = "▓" * filled + "░" * (self.width - filled)
        return f"[{bar}] {self.percent:.0f}%"


class LoadingIndicator(Static):
    """Animated spinner."""

    def __init__(self, message: str = "Loading...", **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._index = 0

    def render(self) -> str:
        char = self._spinner_chars[self._index]
        self._index = (self._index + 1) % len(self._spinner_chars)
        return f"{char} {self.message}"


class InputBar(Container):
    """Command input bar with history and completion."""

    input_value = reactive("")
    history_index = reactive(-1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._command_history: list[str] = []
        self._history_position = 0

    def compose(self) -> ComposeResult:
        yield Static("CMD:>", classes="prompt")
        yield Input(
            placeholder="Type a message or /help for commands...",
            id="command-input",
            classes="input-field",
        )

    def on_mount(self) -> None:
        self.focused_input = self.query_one("#command-input", Input)

    @property
    def value(self) -> str:
        return self.query_one("#command-input", Input).value

    def clear(self) -> None:
        self.query_one("#command-input", Input).value = ""

    def add_to_history(self, command: str) -> None:
        if command and command != self._command_history[-1] if self._command_history else True:
            self._command_history.append(command)
            self._history_position = len(self._command_history)

    def history_up(self) -> None:
        if self._command_history and self._history_position > 0:
            self._history_position -= 1
            self.query_one("#command-input", Input).value = self._command_history[self._history_position]

    def history_down(self) -> None:
        if self._history_position < len(self._command_history):
            self._history_position += 1
            if self._history_position == len(self._command_history):
                self.query_one("#command-input", Input).value = ""
            else:
                self.query_one("#command-input", Input).value = self._command_history[self._history_position]

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        if command:
            self.add_to_history(command)
            self.post_message(CommandEntered(command))
        self.clear()

    def on_click(self, event: events.Click) -> None:
        """Force focus to the input field on click."""
        self.query_one("#command-input", Input).focus()

    def on_key(self, event: events.Key) -> bool:
        if event.key == "up":
            self.history_up()
            return True
        elif event.key == "down":
            self.history_down()
            return True
        return False


class CommandEntered(events.Message):
    """Message sent when user enters a command."""

    def __init__(self, command: str):
        super().__init__()
        self.command = command


class StatusBar(Static):
    """Bottom status bar with system info."""

    def __init__(self, version: str = "0.1.0", model: str = "", project: str = "", termux: bool = False, battery: int = 100, **kwargs):
        super().__init__(**kwargs)
        self.version = version
        self.model = model
        self.project = project
        self.termux = termux
        self.battery = battery
        self.message = ""

    def update(self, message: str = ""):
        self.message = message
        self.refresh()

    def render(self) -> str:
        parts = [self.message or f"NEXUS-OS v{self.version}"]
        if self.model:
            parts.append(f"CORE: [bold cyan]{self.model}[/]")
        if self.project:
            parts.append(f"PROJ: [bold yellow]{self.project}[/]")
        if self.termux:
            parts.append("[bold green]MOBILE-LINK: ACTIVE[/]")
        if self.battery >= 0:
            color = "green" if self.battery > 20 else "red"
            parts.append(f"PWR: [{color}]{self.battery}%[/]")
        return " | ".join(parts)


class Heartbeat(Static):
    """Pulsing indicator for Nexus activity."""

    def on_mount(self) -> None:
        self.set_interval(0.8, self.update_pulse)
        self.pulse = 0
        self.chars = ["▱▱▱▱", "▰▱▱▱", "▰▰▱▱", "▰▰▰▱", "▰▰▰▰", "▱▰▰▰", "▱▱▰▰", "▱▱▱▰"]

    def update_pulse(self) -> None:
        self.pulse = (self.pulse + 1) % len(self.chars)
        self.update(f"[bold cyan]NEURAL:{self.chars[self.pulse]}[/]")


class Telemetry(Static):
    """Live status display for system and steward metrics."""

    def on_mount(self) -> None:
        self.set_interval(2.0, self.update_metrics)
        self._load = 3

    def update_metrics(self) -> None:
        import random

        self._load = max(1, min(99, self._load + random.randint(-5, 5)))
        self.update(f"[telemetry-item]MESH-LOAD: {self._load}% | STEWARD: READY[/]")
