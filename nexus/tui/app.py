"""Nexus TUI - Main Textual Application."""

import asyncio
import os
from datetime import datetime
from typing import Any

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Static

from ..agent import get_orchestrator
from .colors import CSS_COLORS
from .palette import CommandPalette
from .state import (
    AgentStatus,
    ChatMessage,
    MessageRole,
    TUIState,
    get_state_manager,
)
from .task_wrapper import OrchestrationTask
from .widgets import (
    AgentsPanel,
    ChatMessageWidget,
    ChatPanel,
    CommandEntered,
    InputBar,
    StatusBar,
    ThinkingPanel,
    ToolPanel,
)


class NexusTUI(App):
    """Main Textual application for Nexus."""

    CSS_PATH = "styles.css"
    TITLE = "Nexus - Terminal User Interface"
    SUB_TITLE = "Nexus"

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True),
        Binding("ctrl+p", "command_palette", "Command Palette"),
        Binding("ctrl+l", "clear_screen", "Clear Screen"),
        Binding("ctrl+g", "toggle_thinking", "Toggle Thinking Panel"),
        Binding("ctrl+t", "toggle_tools", "Toggle Tools Panel"),
        Binding("ctrl+a", "toggle_agents", "Toggle Agents Panel"),
        Binding("f1", "show_help", "Help"),
        Binding("f2", "show_status", "Status"),
        Binding("escape", "quit", "Quit", priority=True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orchestrator = get_orchestrator()
        self.state_manager = get_state_manager()
        self.orchestrator.set_ui_callback(self._on_orchestrator_event)
        self.state_manager.reset()
        self._input_buffer = ""
        self._command_history: list[str] = []
        self._history_index = -1
        self._termux_mode = os.path.exists("/data/data/com.termux")
        self._version = "0.1.0"

        from .. import __version__
        self._version = __version__

    def _on_orchestrator_event(self, event_type: str, data: Any):
        """Bridge orchestrator brain events to TUI state manager."""
        if event_type == "thinking":
            self.state_manager.add_thinking_step(
                data.get("number", 0),
                data.get("description", ""),
                data.get("details", "")
            )
        elif event_type == "agent_status":
            self.state_manager.update_agent_status(
                data.get("name"),
                data.get("status"),
                data.get("task")
            )

    def compose(self) -> ComposeResult:
        """Create the layout."""
        yield Header()

        # Simple vertical stack to avoid recursion
        yield ChatPanel(id="chat-panel", classes="neural-node")
        yield ThinkingPanel(id="thinking-panel", classes="neural-node")
        yield ToolPanel(id="tool-panel", classes="neural-node")
        yield AgentsPanel(id="agents-panel", classes="neural-node")

        yield InputBar(id="input-bar")
        yield StatusBar(id="status-bar")

        yield Footer()


    def _get_battery(self) -> int:
        """Get battery percentage if available."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                return battery.percent
        except Exception:
            pass
        return -1

    def on_mount(self) -> None:
        """Called when the TUI mounts. Auto-focus the input bar."""
        self.query_one("#command-input", Input).focus()
        self.state_manager.subscribe(self._on_state_change)

        # ... (rest of mount logic) ...
        # Start Shadow Indexer (Proactive Background Learning)
        import threading

        from ..memory.shadow import get_shadow_indexer
        self.shadow_indexer = get_shadow_indexer()
        threading.Thread(target=self.shadow_indexer.start, daemon=True).start()

        chat_panel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.add_message(ChatMessage(
            role=MessageRole.SYSTEM,
            content="Welcome to Nexus TUI! Type /help for available commands.",
            timestamp=datetime.now(),
        ))

        self._update_status_bar()
    def _on_state_change(self, state: TUIState) -> None:
        """Handle state changes from the state manager."""
        self._update_status_bar()
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        thinking_panel = self.query_one("#thinking-panel", ThinkingPanel)
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        agents_panel = self.query_one("#agents-panel", AgentsPanel)

        # Show the most recent message if it's new
        if state.messages:
            last_msg = state.messages[-1]
            if len(chat_panel._messages) == 0 or chat_panel._messages[-1] != last_msg:
                chat_panel.add_message(last_msg)

        # Handle thinking/tools
        for step in state.thinking_steps:
            if step not in thinking_panel._steps:
                thinking_panel.add_step(step)

        for tool in state.tool_statuses.values():
            tool_panel.update_tool(tool)

        # Handle agents
        for agent in state.active_agents:
            agents_panel.update_agent(agent)

            # Check if agent status is noteworthy
            if agent.status == AgentStatus.THINKING:
                chat_panel.add_message(ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"Agent {agent.name} is {agent.status.name.lower()}: {agent.task if hasattr(agent, 'task') else agent.current_task}",
                    timestamp=datetime.now(),
                ))

    def on_command_entered(self, event: CommandEntered) -> None:
        """Handle command entry."""
        # Process the input through the wrapped orchestrator task
        task = OrchestrationTask(self, self._process_input(event.command))
        asyncio.create_task(task.run())

    def action_interrupt(self) -> None:
        """Handle Ctrl+C interrupt."""
        self.notify("Interrupted - use /exit to quit", severity="warning")

    def action_command_palette(self) -> None:
        """Show command palette."""
        def set_command(command: str | None):
            if command:
                input_bar = self.query_one("#command-input", Input)
                input_bar.value = command
                input_bar.focus()

        self.push_screen(CommandPalette(), set_command)

    def action_clear_screen(self) -> None:
        """Clear the chat panel."""
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.clear()
        self.state_manager.state.messages = []

    def action_toggle_thinking(self) -> None:
        """Toggle thinking panel visibility."""
        panel = self.query_one("#thinking-panel", ThinkingPanel)
        panel.toggle_class("hidden")

    def action_toggle_tools(self) -> None:
        """Toggle tools panel visibility."""
        panel = self.query_one("#tool-panel", ToolPanel)
        panel.toggle_class("hidden")

    def action_toggle_agents(self) -> None:
        """Toggle agents panel visibility."""
        panel = self.query_one("#agents-panel", AgentsPanel)
        panel.toggle_class("hidden")

    def on_click(self, event: events.Click) -> None:
        """Globally handle clicks to ensure input bar is focused."""
        try:
            self.query_one("#command-input", Input).focus()
        except:
            pass
        event.stop()

    def action_show_help(self) -> None:
        """Show help overlay."""
        help_text = """
╔══════════════════════════════════════════════════════════╗
║                    Nexus TUI Help                        ║
╠══════════════════════════════════════════════════════════╣
║  Keyboard Shortcuts:                                    ║
║    Ctrl+C    - Interrupt current operation                ║
║    Ctrl+P    - Command palette (placeholder)             ║
║    Ctrl+L    - Clear screen                              ║
║    Ctrl+G    - Toggle thinking panel                     ║
║    Ctrl+T    - Toggle tools panel                        ║
║    Ctrl+A    - Toggle agents panel                       ║
║    F1        - Show this help                            ║
║    F2        - Show status                               ║
║    Escape    - Quit                                      ║
║                                                          ║
║  Slash Commands:                                         ║
║    /help     - Show this help                            ║
║    /clear    - Clear chat history                        ║
║    /history  - Show command history                     ║
║    /tools    - List available tools                     ║
║    /model    - Show/switch model                        ║
║    /facts    - Show stored facts                        ║
║    /session  - Show session info                         ║
║    /doctor   - Run system diagnostics                    ║
║    /cleanup  - Perform tactical cleanup                  ║
║    /exit     - Exit the TUI                              ║
╚══════════════════════════════════════════════════════════╝
        """
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.add_message(ChatMessage(
            role=MessageRole.SYSTEM,
            content=help_text.strip(),
            timestamp=datetime.now(),
        ))

    def action_show_status(self) -> None:
        """Show status information."""
        state = self.state_manager.state
        status_text = f"""
Session: {state.session_id or 'new'}
Model: {state.active_model or 'not set'}
Messages: {len(state.messages)}
Thinking Steps: {len(state.thinking_steps)}
Tools: {len(state.tool_statuses)}
Agents: {len(state.active_agents)}
        """.strip()

        chat_panel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.add_message(ChatMessage(
            role=MessageRole.SYSTEM,
            content=status_text,
            timestamp=datetime.now(),
        ))

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def _update_status_bar(self) -> None:
        """Update the status bar with current info."""
        state = self.state_manager.state
        status_bar = self.query_one(StatusBar)

        status_bar.model = state.active_model or "nexus-v2"

        # Get project info
        import os
        status_bar.project = os.path.basename(os.getcwd())
        status_bar.battery = self._get_battery()
        status_bar.refresh()

    def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        if not command.startswith("/"):
            return False

        parts = command[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        chat_panel = self.query_one("#chat-panel", ChatPanel)

        if cmd in ("exit", "quit", "q"):
            self.exit()
            return True

        elif cmd in ("help", "h"):
            self.action_show_help()
            return True

        elif cmd == "clear":
            chat_panel.clear()
            self.state_manager.state.messages = []
            return True

        elif cmd == "history":
            history_text = "Recent commands:\n" + "\n".join(
                f"  {i+1}. {cmd}" for i, cmd in enumerate(self._command_history[-10:])
            )
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=history_text,
                timestamp=datetime.now(),
            ))
            return True

        elif cmd == "tools":
            from ..tools import get_registry
            registry = get_registry()
            tools_text = "Available tools:\n" + "\n".join(
                f"  - {t.name}: {t.description}" for t in registry.list_all()
            )
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=tools_text,
                timestamp=datetime.now(),
            ))
            return True

        elif cmd == "model":
            if args:
                self.state_manager.set_active_model(args)
                chat_panel.add_message(ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"Model switched to: {args}",
                    timestamp=datetime.now(),
                ))
            else:
                state = self.state_manager.state
                chat_panel.add_message(ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"Current model: {state.active_model or 'not set'}",
                    timestamp=datetime.now(),
                ))
            return True

        elif cmd == "facts":
            from ..memory import get_memory
            memory = get_memory()
            facts = memory.get_all_facts()
            if facts:
                facts_text = "Stored facts:\n" + "\n".join(
                    f"  - {k}: {v}" for k, v in facts.items()
                )
            else:
                facts_text = "No facts stored."
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=facts_text,
                timestamp=datetime.now(),
            ))
            return True

        elif cmd == "session":
            from ..memory import get_memory
            memory = get_memory()
            session = memory.create_session()
            self.state_manager.set_session(session.id)
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=f"Session: {session.id}\nCreated: {session.created_at}",
                timestamp=datetime.now(),
            ))
            return True

        elif cmd == "doctor":
            from ..doctor import NexusDoctor
            doctor = NexusDoctor()
            report = doctor.run_all()

            doctor_text = "[bold blue]NEXUS SYSTEM DIAGNOSTICS[/]\n"
            for category, result in report.items():
                status = "[bold green][OK][/]" if result.get("passed", True) else "[bold red][!][/] "
                doctor_text += f"{status} {category.upper()}\n"
                if category == "cache" and result.get("found_count", 0) > 0:
                    from ..utils import format_bytes
                    size = format_bytes(result['total_size_bytes'])
                    doctor_text += f"    -> {result['found_count']} artifacts found ({size} potential savings)\n"

            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=doctor_text.strip(),
                timestamp=datetime.now(),
            ))
            return True

        elif cmd == "cleanup":
            from ..doctor import NexusDoctor
            doctor = NexusDoctor()

            # First show what will be cleaned
            report = doctor.tactical_cleanup(dry_run=True)
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=f"Cleaning {report['potential_savings']} of cache artifacts...",
                timestamp=datetime.now(),
            ))

            # Execute actual cleanup
            result = doctor.tactical_cleanup(dry_run=False)
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=f"[bold green]Cleanup complete.[/] Freed {result['potential_savings']}.",
                timestamp=datetime.now(),
            ))
            self._update_status_bar()
            return True

        return False

    async def _process_input(self, user_input: str) -> None:
        """Process user input through the orchestrator."""
        if not user_input.strip():
            return

        if self._handle_command(user_input):
            return

        chat_panel = self.query_one("#chat-panel", ChatPanel)

        # Echo the user message immediately
        chat_panel.add_message(ChatMessage(
            role=MessageRole.USER,
            content=user_input,
            timestamp=datetime.now(),
        ))

        self.state_manager.set_busy(True)

        try:
            from ..agent.orchestrator import AgentConfig, AgentOrchestrator
            from ..memory import get_memory
            from ..providers import get_manager
            from ..tools import get_registry
            # ... rest of implementation ...

            manager = get_manager()
            registry = get_registry()
            memory = get_memory()

            config = AgentConfig(
                stream=True,
                verbose=False,
            )

            orchestrator = AgentOrchestrator(
                provider_manager=manager,
                tool_registry=registry,
                memory=memory,
                config=config,
            )

            # Keep track of the current assistant message
            self._current_assistant_message = None

            async def stream_callback(content: str):
                if self._current_assistant_message is None:
                    self._current_assistant_message = ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=content,
                        timestamp=datetime.now(),
                    )
                    chat_panel.add_message(self._current_assistant_message)
                else:
                    self._current_assistant_message.content += content
                    # Force update the widget directly
                    # Get the widget corresponding to this message (last added)
                    widgets = chat_panel.query(ChatMessageWidget)
                    if widgets:
                        widgets[-1].message = self._current_assistant_message
                        widgets[-1].refresh()
                self.state_manager.refresh()

            turn = await orchestrator.run(user_input, stream_callback=stream_callback)

            # Ensure all state changes are reflected
            self.state_manager.refresh()

            # Ensure all state changes are reflected
            self.state_manager.refresh()

            if turn.pending_approval:
                self._handle_pending_approval(turn.pending_approval)
                return

            if turn.assistant_message:
                chat_panel.add_message(ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=turn.assistant_message,
                    timestamp=datetime.now(),
                ))

            if turn.error:
                self.state_manager.set_error(turn.error)

        except Exception as e:
            chat_panel.add_message(ChatMessage(
                role=MessageRole.SYSTEM,
                content=f"Error: {e}",
                timestamp=datetime.now(),
            ))
            self.state_manager.set_error(str(e))

        finally:
            self.state_manager.set_busy(False)

    def _handle_pending_approval(self, approval: dict[str, Any]) -> None:
        """Display a diff for user approval."""
        result = approval.get("result", {})
        diff = result.get("metadata", {}).get("diff", "No diff available")
        path = result.get("metadata", {}).get("path", "Unknown")

        diff_display = f"\n{'='*60}\nPROPOSED CHANGE: {path}\n{'='*60}\n{diff}"

        chat_panel = self.query_one("#chat-panel", ChatPanel)

        chat_panel.add_message(
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=diff_display,
                timestamp=datetime.now(),
            )
        )

        chat_panel.add_message(
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="\n[APPROVAL REQUIRED]\nType 'approve' to apply this change, or 'reject' to cancel.",
                timestamp=datetime.now(),
            )
        )

        self.state_manager.set_busy(False)

    def on_input_bar_command_entered(self, event: CommandEntered) -> None:
        """Handle command entered in input bar."""
        command = str(event).strip()
        if command:
            self._command_history.append(command)
            self._history_index = len(self._command_history)

        asyncio.create_task(self._process_input(command))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        command = event.value.strip()
        if command:
            self._command_history.append(command)
            self._history_index = len(self._command_history)

        asyncio.create_task(self._process_input(command))

        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.clear()


class Notification(events.Message):
    """Custom notification message."""

    def __init__(self, message: str, severity: str = "info"):
        super().__init__()
        self.message = message
        self.severity = severity


class NotificationOverlay(Static):
    """Overlay for displaying notifications."""

    def __init__(self, message: str, severity: str = "info", **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.severity = severity

    def compose(self) -> ComposeResult:
        color = {
            "info": CSS_COLORS["info"],
            "warning": CSS_COLORS["warning"],
            "error": CSS_COLORS["error"],
            "success": CSS_COLORS["success"],
        }.get(self.severity, CSS_COLORS["text"])

        yield Static(self.message, markup=True)


def run_tui() -> None:
    """Run the TUI application."""
    app = NexusTUI()
    app.run()
