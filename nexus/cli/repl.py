"""Interactive REPL for Nexus."""

import asyncio
import readline
import sys
<<<<<<< HEAD
import time
from typing import Any

from ..providers import Message, get_manager
from ..tools import get_registry, ToolResult
from ..memory import get_memory
from ..agents import init_team, get_team, AgentRole, MultiAgentTeam
from ..thinking import ThinkingEngine, get_thinking_engine, ThinkingState
from ..ui import LoadingIndicator, ProgressTracker
from ..plan import PlanMode, get_plan_mode, set_plan_mode, should_trigger_plan_mode
from ..sessions import get_session_loader
from ..safety import get_safety_engine, SafetyEngine
from ..sync import get_sync_engine
from ..learn import get_learning_engine
from ..self_improve import get_self_improver
from ..personality import get_personality, Personality
from ..phone import get_phone_mode, PhoneMode
from ..voice import get_voice_engine
=======
from typing import Any

from nexus.agents import AgentRole, MultiAgentTeam, init_team
from nexus.learn import get_learning_engine
from nexus.memory import get_memory
from nexus.orchestrator import ExecutionEngine, LLMAwareDecomposer, is_structured_task
from nexus.personality import Personality, get_personality
from nexus.phone import PhoneMode, get_phone_mode
from nexus.plan import PlanMode, set_plan_mode
from nexus.plugins import get_plugin_manager
from nexus.providers import Message, get_manager
from nexus.safety import SafetyEngine, get_safety_engine
from nexus.self_improve import get_self_improver
from nexus.sessions import get_session_loader
from nexus.skills import SkillsManager
from nexus.sync import get_sync_engine
from nexus.thinking import ThinkingState, get_thinking_engine
from nexus.tools import ToolResult, get_registry
from nexus.ui import ProgressTracker
from nexus.voice import get_voice_engine
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)


class REPL:
    """Interactive REPL for Nexus."""

    def __init__(self, config: dict[str, Any] | None = None):
<<<<<<< HEAD
=======
        from nexus.cli.task_tracker import TaskTracker

        self.tasks = TaskTracker()
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        self.config = config or {}
        self.manager = get_manager()
        self.registry = get_registry()
        self.memory = get_memory()
        self.session = self.memory.create_session()
        self.messages: list[Message] = []
        self.running = True
        self.streaming = True
        self.team: MultiAgentTeam | None = None
        self.thinking_engine = get_thinking_engine()
        self._first_token_received = False
        self._tool_call_count = 0
        self._total_tool_calls = 0
        self._start_time = 0.0
        self._plan_mode: PlanMode | None = None
        self._plan_active = False
<<<<<<< HEAD
        
=======
        self._last_failed_tool_call = None
        self._file_snapshots: dict[str, str] = {}

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        # New systems
        self.safety: SafetyEngine = get_safety_engine()
        self.sync_engine = get_sync_engine()
        self.learning = get_learning_engine()
        self.improver = get_self_improver()
        self.personality: Personality = get_personality()
        self.phone: PhoneMode = get_phone_mode()
<<<<<<< HEAD
        
        # Session auto-load
        self.session_loader = get_session_loader()
        
        # Set up readline
        self._setup_readline()
        
=======

        # Session auto-load
        self.session_loader = get_session_loader()
        self.session_loader.start_auto_save(self.session)

        # Plugin system
        self.plugin_manager = get_plugin_manager()

        # Skills system
        self.skills = SkillsManager()
        self.skills.load_all()

        # CLI flags
        self._yes_flag = self.config.get("yes", False)

        # Set up readline
        self._setup_readline()

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        # Initialize multi-agent team
        self.team = init_team(lead_name="nexus", pm=self.manager)
        self.team.on_message(self._on_team_message)

<<<<<<< HEAD
        # Register thinking callback
        self.thinking_engine.on_update(self._on_thinking_update)
        
        # Start learning session
        self.learning.start_session(self.session.id)
        
        # Phone mode preprocessing
        if self.phone.enabled:
            print("📱 Phone mode active — type /h for compact help")
        
=======
        # Initialize execution engine
        self.decomposer = LLMAwareDecomposer(llm_callback=self._llm_plan_callback)
        self.executor = ExecutionEngine(
            registry=self.registry,
            tool_executor=self._execute_tool_wrapper,
            llm_callback=self._llm_plan_callback,
        )

        # Register thinking callback
        self.thinking_engine.on_update(self._on_thinking_update)

        # Start learning session
        self.learning.start_session(self.session.id)

        # Phone mode preprocessing
        if self.phone.enabled:
            cyan = "\033[36m"
            blue = "\033[34m"
            dim = "\033[90m"
            reset = "\033[0m"
            print(f"  {blue}╼{reset} {dim}nexus/{reset}{cyan}phone{reset} active {dim}— type /h for compact help{reset}")

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        self._check_resume_session()

    async def _ensure_provider(self) -> None:
        """Ensure a working provider is configured. Auto-setup OpenCode Zen if needed."""
        try:
            # Try to get the active provider
            provider = await self.manager.get_provider()
            # Quick ping to verify it works
            await provider.complete([Message(role="user", content="ping")], None)
            return
        except Exception:
            pass

        # No working provider — try OpenCode Zen free models
<<<<<<< HEAD
        print("\n\033[33m⚠ No working AI provider found.\033[0m")
        print("Trying OpenCode Zen free models (no API key needed)...\n")

        try:
            from ..providers.base import PROVIDER_REGISTRY
            from ..config import ProviderConfig, save_config
            from .. import config as cfg_module
=======
        cyan = "\033[36m"
        blue = "\033[34m"
        bold = "\033[1m"
        reset = "\033[0m"
        
        print(f"\n  {blue}╼{reset} {cyan}nexus{reset} {bold}provider link lost{reset}")
        print(f"    {bold}Attempting OpenCode Zen uplink...{reset}\n")

        try:
            from .. import config as cfg_module
            from ..config import ProviderConfig, save_config
            from ..providers.base import PROVIDER_REGISTRY
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

            opencode_config = ProviderConfig(
                name="opencode-zen",
                provider_type="openai",
                api_key="",
                base_url="https://opencode.ai/zen/v1",
                model="minimax-m2.5-free",
                max_tokens=8192,
                temperature=0.7,
                timeout=120,
                enabled=True,
            )

<<<<<<< HEAD
            prov = PROVIDER_REGISTRY["openai"]({
                "api_key": "",
                "base_url": "https://opencode.ai/zen/v1",
                "model": "minimax-m2.5-free",
                "timeout": 120,
            })
=======
            prov = PROVIDER_REGISTRY["openai"](
                {
                    "api_key": "",
                    "base_url": "https://opencode.ai/zen/v1",
                    "model": "minimax-m2.5-free",
                    "timeout": 120,
                }
            )
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            await prov.complete([Message(role="user", content="ping")], None)

            # Works — save to config
            self.manager.configs["opencode-zen"] = opencode_config
            self.manager.providers["opencode-zen"] = prov
            self.manager.active_provider = "opencode-zen"

            # Persist
            full_config = cfg_module.load_config()
            full_config.providers = {"opencode-zen": opencode_config}
            full_config.active_provider = "opencode-zen"
            save_config(full_config)

<<<<<<< HEAD
            print("\033[92m✓ Connected to OpenCode Zen (minimax-m2.5-free)\033[0m\n")
        except Exception as e:
            print(f"\n\033[91m✗ Could not connect to OpenCode Zen: {e}\033[0m")
            print("\nRun \033[1mnexus setup\033[0m to configure a provider manually.\n")
=======
            print(f"    {blue}✔{reset} {bold}Connected to OpenCode Zen (minimax-m2.5-free){reset}\n")
        except Exception as e:
            print(f"\n    {blue}✘{reset} {bold}Could not connect to OpenCode Zen: {e}{reset}")
            print(f"    {dim}Run{reset} {cyan}nexus setup{reset} {dim}to configure a provider manually.{reset}\n")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

    def _check_resume_session(self) -> None:
        """Check for previous session and offer to resume."""
        recent = self.session_loader.get_most_recent_session()
        if recent and recent.messages:
            prompt = self.session_loader.get_resume_prompt(recent)
            try:
                response = input(prompt).strip().lower()
                if response in ("y", "yes"):
                    # Load session messages
                    loaded = self.session_loader.load_session(recent.id)
                    if loaded:
                        self.session = loaded
                        for msg in loaded.messages[-20:]:
                            if msg["role"] == "user":
                                self.messages.append(Message(role="user", content=msg["content"]))
                            elif msg["role"] == "assistant":
<<<<<<< HEAD
                                self.messages.append(Message(role="assistant", content=msg["content"]))
                        print(f"Resumed session. {len(self.messages)} messages loaded.")
                else:
                    print("Starting fresh session.")
            except (EOFError, KeyboardInterrupt):
                    print("Starting fresh session.")
=======
                                self.messages.append(
                                    Message(role="assistant", content=msg["content"])
                                )
                        cyan = "\033[36m"
                        blue = "\033[34m"
                        dim = "\033[90m"
                        reset = "\033[0m"
                        print(f"  {blue}╼{reset} {dim}nexus/{reset}{cyan}session{reset} {dim}resumed. {len(self.messages)} entries restored.{reset}")
                else:
                    cyan = "\033[36m"
                    blue = "\033[34m"
                    dim = "\033[90m"
                    reset = "\033[0m"
                    print(f"  {blue}╼{reset} {dim}nexus/{reset}{cyan}session{reset} {dim}starting fresh context.{reset}")
            except (EOFError, KeyboardInterrupt):
                cyan = "\033[36m"
                blue = "\033[34m"
                dim = "\033[90m"
                reset = "\033[0m"
                print(f"  {blue}╼{reset} {dim}nexus/{reset}{cyan}session{reset} {dim}starting fresh context.{reset}")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

    def _check_tool_safety(self, tool_name: str, arguments: dict) -> tuple[bool, ToolResult | None]:
        """Check tool call against safety rules. Returns (proceed, error_result)."""
        path_keys = ("path", "filePath", "file_path", "directory", "workdir")
<<<<<<< HEAD
        context: dict = {"tool": tool_name, "args": arguments}
=======
        context: dict = {"tool_name": tool_name}
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        for key in path_keys:
            if key in arguments and arguments[key]:
                context["path"] = arguments[key]
                break
        if "command" in arguments:
            context["command"] = arguments["command"]

        violations = self.safety.check(context)
        if not violations:
            return True, None

<<<<<<< HEAD
        proceed, reason = self.safety.should_proceed(violations)
        if not proceed:
=======
        blocks = [v for v in violations if v.severity == "BLOCK"]
        if blocks:
            reason = "\n  ".join(v.message for v in blocks)
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            error = ToolResult(
                success=False,
                content=f"[SAFETY BLOCK] {reason}",
            )
            print(f"\n{self.safety.render_violations(violations)}\n")
            return False, error

        print(f"\n{self.safety.render_violations(violations)}\n")
        return True, None

    def _setup_readline(self) -> None:
        """Configure readline for better editing."""
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set editing-mode vi")
<<<<<<< HEAD
        
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        # History file
        histfile = self._get_histfile()
        try:
            readline.read_history_file(histfile)
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)

    def _get_histfile(self) -> str:
        """Get the history file path."""
        from pathlib import Path
<<<<<<< HEAD
        return str(Path.home() / ".nexus" / ".history")

=======

        return str(Path.home() / ".nexus" / ".history")

    async def _execute_single_tool(self, tool_call, tool) -> ToolResult:
        """Execute a single tool call and return the result."""
        exec_step = self.thinking_engine.start_step(
            ThinkingState.EXECUTING,
            f"Calling tool: {tool_call.name}",
            tool_name=tool_call.name,
            tool_args=tool_call.arguments,
        )
        proceed, error_result = self._check_tool_safety(tool_call.name, tool_call.arguments)
        if not proceed:
            result = error_result
        else:
            if tool_call.name == "Read":
                for path_key in ("path", "filePath", "file_path"):
                    if path_key in tool_call.arguments:
                        self.safety.mark_file_read(tool_call.arguments[path_key])
                        break
            if tool_call.name == "Write":
                path_key = next((k for k in ("path", "filePath", "file_path") if k in tool_call.arguments), None)
                if path_key:
                    path = tool_call.arguments[path_key]
                    from pathlib import Path
                    if Path(path).exists():
                        self._file_snapshots[path] = Path(path).read_text()
            ctx = {"session_id": self.session.id}
            modified_args = self.plugin_manager.call_tool_hooks(tool_call.name, tool_call.arguments, ctx)
            result = await tool.execute(**modified_args)
            result = self.plugin_manager.call_result_hooks(tool_call.name, result, ctx)
        if not result.success:
            self._last_failed_tool_call = tool_call
            self.learning.record_failure(
                tool_name=tool_call.name,
                args=tool_call.arguments,
                error=result.error or result.content,
                context={"session": self.session.id},
            )
        self.thinking_engine.finish_step(
            exec_step,
            result=result.content[:200] if result.content else "",
        )
        return result

    async def _execute_tool_wrapper(self, tool_name: str, args: dict) -> ToolResult:
        """Wrapper for executing tools via the execution engine."""
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(success=False, content="", error=f"Tool '{tool_name}' not found")
        
        tool_call = type("ToolCall", (), {"name": tool_name, "arguments": args})()
        return await self._execute_single_tool(tool_call, tool)

    async def _llm_plan_callback(self, prompt: str) -> str:
        """Callback for LLM-assisted planning."""
        messages = [
            Message(role="system", content="You are a task planning assistant. Create a JSON plan."),
            Message(role="user", content=prompt),
        ]
        tools = self.registry.to_openai_format()
        
        try:
            response = await self.manager.complete(messages, tools)
            if response.content:
                return response.content
            if response.tool_calls:
                return str(response.tool_calls)
            return ""
        except Exception as e:
            return f"Planning error: {e}"

    def _manage_context_window(self) -> None:
        """Truncate messages if context window is getting too large."""
        max_messages = 200
        if len(self.messages) <= max_messages:
            return
        keep = max_messages // 2
        removed = len(self.messages) - keep
        self.messages = self.messages[-keep:]
        print(f"\n[context] Truncated {removed} older messages to manage context window.")

    async def _retry_tool(self, tool_call, tool) -> None:
        """Retry a failed tool call."""
        result = await self._execute_single_tool(tool_call, tool)
        print(f"Result: {result.content[:200] if result.content else result.error}")

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
    def _save_history(self) -> None:
        """Save command history."""
        histfile = self._get_histfile()
        try:
            readline.write_history_file(histfile)
        except Exception:
            pass

    async def _llm_voice_callback(self, text: str) -> str:
        """Send voice input to LLM and return response text."""
        from ..providers import Message
<<<<<<< HEAD
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        messages = [Message(role="system", content=self._get_system_prompt())] + self.messages
        messages.append(Message(role="user", content=text))

        tools = self.registry.to_openai_format()

        try:
            response = await self.manager.complete(messages, tools)
            for tc in response.tool_calls:
                tool = self.registry.get(tc.name)
                if tool:
                    result = await tool.execute(**tc.arguments)
<<<<<<< HEAD
                    messages.append(Message(
                        role="tool", content=result.content,
                        name=tc.name, tool_call_id=tc.id,
                    ))
=======
                    messages.append(
                        Message(
                            role="tool",
                            content=result.content,
                            name=tc.name,
                            tool_call_id=tc.id,
                        )
                    )
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

            response = await self.manager.complete(messages, tools)
            self.messages.append(Message(role="user", content=text))
            self.messages.append(Message(role="assistant", content=response.content))
            self.session.messages.append({"role": "user", "content": text})
            self.session.messages.append({"role": "assistant", "content": response.content})
            self.memory.save_session(self.session)
            return response.content
        except Exception as e:
            return f"Oops, ran into an issue: {e}"

    async def _run_voice_mode(self, overrides: dict[str, str]) -> None:
        """Enter voice conversation mode."""
        engine = get_voice_engine(llm_callback=self._llm_voice_callback, **overrides)
        print(f"\n{self.personality.greet()} Starting voice mode...")
        async with engine.voice_mode():
            while engine._running:
                await asyncio.sleep(0.5)

    def _get_prompt(self) -> str:
<<<<<<< HEAD
        """Get the command prompt."""
        return "\033[1;36mnexus\033[0m> "
=======
        """Get the branded command prompt."""
        cyan = "\033[36m"
        bold = "\033[1m"
        blue = "\033[34m"
        reset = "\033[0m"
        return f"{blue}⫸{cyan}nexus{reset} {bold}»{reset} "
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the agent."""
        context = self.memory.get_context_summary()
        voice_prompt = self.personality.get_voice_system_prompt()
<<<<<<< HEAD

        return f"""{voice_prompt}
=======
        skills_context = self.skills.get_context()

        prompt = f"""{voice_prompt}
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

You are an AI coding assistant powered by Nexus.

You have access to the following tools:
{self._format_tools()}

Memory context:
{context}
<<<<<<< HEAD

When using tools, always provide clear feedback about what you're doing.
Focus on being helpful, accurate, and efficient.
"""
=======
"""
        if skills_context:
            prompt += f"\n{skills_context}\n"
        prompt += "\nWhen using tools, always provide clear feedback about what you're doing.\nFocus on being helpful, accurate, and efficient.\n"
        return prompt
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

    def _format_tools(self) -> str:
        """Format tools for the system prompt."""
        lines = []
        for tool in self.registry.list_all():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    async def _generate_response(self, user_input: str, print_result: bool = True) -> str:
        """Generate a response from the AI."""
        # Add user message
        self.messages.append(Message(role="user", content=user_input))
        self.session.messages.append({"role": "user", "content": user_input})

<<<<<<< HEAD
=======
        # Auto-activate skills based on task
        self.skills.auto_activate(user_input)

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        # Auto-spawn agents for complex tasks
        if self.team:
            spawned = self.team.auto_spawn_for_task(user_input)
            if spawned:
<<<<<<< HEAD
                print(f"\n[team] Auto-spawned: {', '.join(a.name for a in spawned)}")
=======
                cyan = "\033[36m"
                blue = "\033[34m"
                dim = "\033[90m"
                reset = "\033[0m"
                agents = ", ".join(f"{cyan}{a.name}{reset}" for a in spawned)
                print(f"  {blue}╼{reset} {dim}nexus/{reset}{cyan}team{reset} {dim}auto-spawned:{reset} {agents}")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

        # Build messages with system prompt
        messages = [Message(role="system", content=self._get_system_prompt())] + self.messages

        # Get tools
        tools = self.registry.to_openai_format()

        try:
            if self.streaming:
<<<<<<< HEAD
                response_text = ""
                tool_results = []

                async for chunk in self.manager.stream(messages, tools):
                    if chunk.content:
                        self._first_token_received = True
                        print(chunk.content, end="", flush=True)
                        response_text += chunk.content

                    if chunk.tool_call:
                        tool_call = chunk.tool_call
                        print(f"\n\n[Calling tool: {tool_call.name}]\n")
                        exec_step = self.thinking_engine.start_step(
                            ThinkingState.EXECUTING,
                            f"Calling tool: {tool_call.name}",
                            tool_name=tool_call.name,
                            tool_args=tool_call.arguments,
                        )
                        tool = self.registry.get(tool_call.name)
                        if tool:
                            proceed, error_result = self._check_tool_safety(tool_call.name, tool_call.arguments)
=======
                from nexus.providers.base import ToolCall
                import json as json_module

                max_tool_rounds = 10
                tool_round = 0
                final_content = ""
                streaming_done = True

                while tool_round < max_tool_rounds:
                    tool_round += 1
                    response_text = ""
                    complete_tool_calls: list[ToolCall] = []
                    collected_raw_tool_calls: list[dict] = []

                    async for chunk in self.manager.stream(messages, tools):
                        if chunk.content:
                            self._first_token_received = True
                            print(chunk.content, end="", flush=True)
                            response_text += chunk.content

                        if chunk.raw_tool_call:
                            collected_raw_tool_calls.append(chunk.raw_tool_call)

                        if chunk.done:
                            break

                    print()

                    if not collected_raw_tool_calls:
                        final_content = response_text
                        break

                    raw_tool_calls = None
                    if collected_raw_tool_calls:
                        raw_by_index: dict[int, dict] = {}
                        for raw_tc in collected_raw_tool_calls:
                            idx = raw_tc.get("index", 0)
                            if idx not in raw_by_index:
                                raw_by_index[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            if raw_tc.get("id"):
                                raw_by_index[idx]["id"] = raw_tc["id"]
                            if raw_tc.get("function", {}).get("name"):
                                raw_by_index[idx]["function"]["name"] = raw_tc["function"]["name"]
                            args_val = raw_tc.get("function", {}).get("arguments")
                            if args_val is not None:
                                raw_by_index[idx]["function"]["arguments"] += args_val
                        raw_tool_calls = list(raw_by_index.values())

                        for raw_tc in raw_tool_calls:
                            if raw_tc.get("function", {}).get("name"):
                                args_str = raw_tc["function"].get("arguments", "{}")
                                try:
                                    args = json_module.loads(args_str) if args_str else {}
                                except json_module.JSONDecodeError:
                                    args = {}
                                complete_tool_calls.append(ToolCall(
                                    id=raw_tc.get("id", ""),
                                    name=raw_tc["function"]["name"],
                                    arguments=args,
                                ))

                    if raw_tool_calls:
                        assistant_msg = Message(
                            role="assistant",
                            content=response_text,
                            tool_calls=raw_tool_calls,
                        )
                        messages.append(assistant_msg)

                    if complete_tool_calls and len(complete_tool_calls) > 1:
                        permission_checks = []
                        for tool_call in complete_tool_calls:
                            tool = self.registry.get(tool_call.name)
                            if tool and tool.needs_permission and not self._yes_flag:
                                try:
                                    print(f"\n[Permission required for: {tool_call.name}]")
                                    response = input(f"  Allow '{tool_call.name}'? (y/N): ").strip().lower()
                                    if response not in ("y", "yes"):
                                        permission_checks.append((tool_call, None))
                                    else:
                                        permission_checks.append((tool_call, tool))
                                except (EOFError, KeyboardInterrupt):
                                    print("  Skipped.")
                                    permission_checks.append((tool_call, None))
                            else:
                                permission_checks.append((tool_call, tool))

                        print(f"\n[Running {sum(1 for _, t in permission_checks if t is not None)} tools in parallel]")
                        coroutines = []
                        for tool_call, tool in permission_checks:
                            if tool:
                                coroutines.append(self._execute_single_tool(tool_call, tool))
                            else:
                                coroutines.append(asyncio.coroutine(lambda tc=tool_call: ToolResult(
                                    success=False, content="", error=f"Permission denied for {tc.name}"
                                ))())

                        results = await asyncio.gather(*coroutines, return_exceptions=True)
                        for (tool_call, tool), result in zip(permission_checks, results):
                            if isinstance(result, Exception):
                                result = ToolResult(success=False, content="", error=str(result))
                            messages.append(
                                Message(
                                    role="tool",
                                    content=result.content or "",
                                    name=tool_call.name,
                                    tool_call_id=tool_call.id,
                                )
                            )
                            if tool_call.name not in self.session.tools_used:
                                self.session.tools_used.append(tool_call.name)
                            if result.success:
                                prefix = f"{self.personality.success()} "
                            else:
                                prefix = f"{self.personality.failure()} "
                            preview = result.content[:200] if result.content else result.error or ""
                            print(
                                f"{prefix}{tool_call.name}: {preview}..."
                                if len(preview) > 200
                                else f"{prefix}{tool_call.name}: {preview}"
                            )
                    elif complete_tool_calls:
                        tool_call = complete_tool_calls[0]
                        tool = self.registry.get(tool_call.name)
                        if tool and tool.needs_permission and not self._yes_flag:
                            try:
                                cyan = "\033[36m"
                                blue = "\033[34m"
                                bold = "\033[1m"
                                reset = "\033[0m"
                                print(f"  {blue}╼{reset} {cyan}{tool_call.name}{reset} {bold}requires authorization{reset}")
                                response = input(f"    {bold}Allow execution?{reset} (y/N): ").strip().lower()
                                if response not in ("y", "yes"):
                                    print(f"  Skipped: {tool_call.name}")
                                    messages.append(
                                        Message(
                                            role="tool",
                                            content=f"[SKIPPED] User denied permission for {tool_call.name}",
                                            name=tool_call.name,
                                            tool_call_id=tool_call.id,
                                        )
                                    )
                                else:
                                    result = await self._execute_single_tool(tool_call, tool)
                                    messages.append(
                                        Message(
                                            role="tool",
                                            content=result.content or "",
                                            name=tool_call.name,
                                            tool_call_id=tool_call.id,
                                        )
                                    )
                                    if tool_call.name not in self.session.tools_used:
                                        self.session.tools_used.append(tool_call.name)
                            except (EOFError, KeyboardInterrupt):
                                print("  Skipped.")
                                messages.append(
                                    Message(
                                        role="tool",
                                        content=f"[SKIPPED] User denied permission for {tool_call.name}",
                                        name=tool_call.name,
                                        tool_call_id=tool_call.id,
                                    )
                                )
                        elif tool:
                            result = await self._execute_single_tool(tool_call, tool)
                            messages.append(
                                Message(
                                    role="tool",
                                    content=result.content or "",
                                    name=tool_call.name,
                                    tool_call_id=tool_call.id,
                                )
                            )
                            if tool_call.name not in self.session.tools_used:
                                self.session.tools_used.append(tool_call.name)

                    if not complete_tool_calls:
                        final_content = response_text
                        break

                    print()

            else:
                response = await self.manager.complete(messages, tools)

                # Handle tool calls
                if response.tool_calls:
                    # Add assistant message with tool calls before tool results
                    messages.append(Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.raw_tool_calls,
                    ))

                    for tool_call in response.tool_calls:
                        tool = self.registry.get(tool_call.name)
                        if tool and tool.needs_permission and not self._yes_flag:
                            try:
                                cyan = "\033[36m"
                                blue = "\033[34m"
                                bold = "\033[1m"
                                reset = "\033[0m"
                                print(f"  {blue}╼{reset} {cyan}{tool_call.name}{reset} {bold}requires authorization{reset}")
                                response = input(f"    {bold}Allow execution?{reset} (y/N): ").strip().lower()
                                if response not in ("y", "yes"):
                                    print(f"  Skipped: {tool_call.name}")
                                    messages.append(
                                        Message(
                                            role="tool",
                                            content=f"[SKIPPED] User denied permission for {tool_call.name}",
                                            name=tool_call.name,
                                            tool_call_id=tool_call.id,
                                        )
                                    )
                                    continue
                            except (EOFError, KeyboardInterrupt):
                                print("  Skipped.")
                                messages.append(
                                    Message(
                                        role="tool",
                                        content=f"[SKIPPED] User denied permission for {tool_call.name}",
                                        name=tool_call.name,
                                        tool_call_id=tool_call.id,
                                    )
                                )
                                continue
                        if tool:
                            proceed, error_result = self._check_tool_safety(
                                tool_call.name, tool_call.arguments
                            )
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                            if not proceed:
                                result = error_result
                            else:
                                if tool_call.name == "Read":
                                    for path_key in ("path", "filePath", "file_path"):
                                        if path_key in tool_call.arguments:
                                            self.safety.mark_file_read(tool_call.arguments[path_key])
                                            break
<<<<<<< HEAD
                                result = await tool.execute(**tool_call.arguments)
                            tool_results.append((tool_call, result))
                            if not result.success:
=======
                                if tool_call.name == "Write":
                                    path_key = next((k for k in ("path", "filePath", "file_path") if k in tool_call.arguments), None)
                                    if path_key:
                                        path = tool_call.arguments[path_key]
                                        from pathlib import Path
                                        if Path(path).exists():
                                            self._file_snapshots[path] = Path(path).read_text()
                                ctx = {"session_id": self.session.id}
                                modified_args = self.plugin_manager.call_tool_hooks(tool_call.name, tool_call.arguments, ctx)
                                result = await tool.execute(**modified_args)
                                result = self.plugin_manager.call_result_hooks(tool_call.name, result, ctx)
                            if not result.success:
                                self._last_failed_tool_call = tool_call
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                                self.learning.record_failure(
                                    tool_name=tool_call.name,
                                    args=tool_call.arguments,
                                    error=result.error or result.content,
                                    context={"session": self.session.id},
                                )
<<<<<<< HEAD
                            self.thinking_engine.finish_step(
                                exec_step,
                                result=result.content[:200] if result.content else "",
                            )
                            if result.success:
                                prefix = f"\n{self.personality.success()} "
                            else:
                                prefix = f"\n{self.personality.failure()} "
                            preview = result.content[:200]
                            print(f"{prefix}{preview}..." if len(result.content) > 200 else f"{prefix}{result.content}")

                            # Add tool result as message
                            messages.append(Message(
                                role="tool",
                                content=result.content,
                                name=tool_call.name,
                                tool_call_id=tool_call.id,
                            ))

                            # Record tool usage
                            if chunk.tool_call.name not in self.session.tools_used:
                                self.session.tools_used.append(chunk.tool_call.name)

                print()  # Newline after streaming
                final_content = response_text
                streaming_done = True

            else:
                response = await self.manager.complete(messages, tools)
                
                # Handle tool calls
                for tool_call in response.tool_calls:
                    tool = self.registry.get(tool_call.name)
                    if tool:
                        proceed, error_result = self._check_tool_safety(tool_call.name, tool_call.arguments)
                        if not proceed:
                            result = error_result
                        else:
                            if tool_call.name == "Read":
                                for path_key in ("path", "filePath", "file_path"):
                                    if path_key in tool_call.arguments:
                                        self.safety.mark_file_read(tool_call.arguments[path_key])
                                        break
                            result = await tool.execute(**tool_call.arguments)
                        if not result.success:
                            self.learning.record_failure(
                                tool_name=tool_call.name,
                                args=tool_call.arguments,
                                error=result.error or result.content,
                                context={"session": self.session.id},
                            )
                        messages.append(Message(
                            role="tool",
                            content=result.content,
                            name=tool_call.name,
                            tool_call_id=tool_call.id,
                        ))

                # Get final response (may be after tool results)
                response = await self.manager.complete(messages, tools)
                final_content = response.content
=======
                            messages.append(
                                Message(
                                    role="tool",
                                    content=result.content or "",
                                    name=tool_call.name,
                                    tool_call_id=tool_call.id,
                                )
                            )

                    # Get final response (may be after tool results)
                    response = await self.manager.complete(messages, tools)
                    final_content = response.content
                else:
                    final_content = response.content
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                streaming_done = False

            if print_result and final_content and not streaming_done:
                print(final_content)

            self.memory.save_session(self.session)
<<<<<<< HEAD
=======
            self._manage_context_window()
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            return final_content

        except Exception as e:
            return f"Error: {e}"

<<<<<<< HEAD
=======
    def _get_help_categories(self) -> dict[str, list[tuple[str, str]]]:
        """Returns a categorized mapping of commands and their descriptions."""
        return {
            "Session": [
                ("/exit", "Exit the REPL"),
                ("/clear", "Clear conversation"),
                ("/history", "Show message history"),
                ("/save", "Save current session"),
                ("/sessions", "List saved sessions"),
                ("/load <id>", "Load a saved session"),
                ("/session", "Show current session info"),
            ],
            "Team": [
                ("/spawn <role>", "Spawn a team agent (coder, reviewer, tester, researcher)"),
                ("/template <name>", "Load a pre-configured agent profile"),
                ("/agents", "List active agents"),
                ("/team", "Show team status"),
            ],
            "Cognition & Planning": [
                ("/plan, /p", "Enter plan mode for a task"),
                ("/build", "Execute approved plan steps"),
                ("/think", "Show thinking engine state"),
                ("/reflect", "Trigger reflection on current work"),
            ],
            "Configuration & Status": [
                ("/model <name>", "Switch model"),
                ("/providers", "Show configured providers"),
                ("/models", "Show available models"),
                ("/status", "Show system status"),
                ("/doctor", "Run system diagnostics"),
                ("/config", "Manage configuration"),
            ],
            "Learning & Safety": [
                ("/learn stats", "Learning system / lessons / failures / clear"),
                ("/improve queue", "Improvement queue / approve / reject / run"),
                ("/safety status", "Safety rules / strict / permissive"),
                ("/facts", "Show stored facts"),
                ("/fact <text>", "Add a persistent fact"),
            ],
            "Extensions": [
                ("/skills", "List available skills"),
                ("/skill <name>", "Activate a skill"),
                ("/plugin", "Plugin management"),
                ("/mcp", "MCP server status"),
            ],
            "Interface": [
                ("/stream", "Toggle streaming mode"),
                ("/voice", "Enter voice mode (Nexus speaks & listens)"),
                ("/phone", "Phone-optimized mode info"),
                ("/partner", "Set personality mode"),
                ("/update", "Update Nexus to the latest version"),
            ],
        }

    def _handle_help(self, args: str) -> None:
        """Display the interactive command explorer."""
        categories = self._get_help_categories()

        print("\n\033[1;36m-- NEXUS COMMAND EXPLORER --\033[0m")
        print("\033[90mSearch: /help <keyword> | Quick Start: /plan, /template, /doctor\033[0m\n")

        if args:
            # Filtered Mode
            keyword = args.lower()
            found = False
            print(f"\033[1mSearching for '{keyword}':\033[0m")
            for cat, cmds in categories.items():
                matches = [c for c in cmds if keyword in c[0].lower() or keyword in c[1].lower()]
                if matches:
                    print(f"\n\033[94m{cat}\033[0m")
                    for cmd, desc in matches:
                        print(f"  \033[32m{cmd}\033[0m → {desc}")
                    found = True
            if not found:
                print(f"\033[91mNo commands found matching '{keyword}'\033[0m")
            return

        # Global Mode
        for cat, cmds in categories.items():
            print(f"\033[1;34m{cat}\033[0m")
            for cmd, desc in cmds:
                print(f"  \033[32m{cmd}\033[0m  {desc}")
            print()

    async def _handle_update(self) -> None:
        """Check for and apply updates from GitHub."""
        import subprocess

        print("\n\033[1;36mChecking for updates...\033[0m")

        try:
            # 1. Fetch latest from origin
            subprocess.run(["git", "fetch", "origin"], check=True, capture_output=True)

            # 2. Compare local HEAD with origin/main
            local_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            remote_hash = subprocess.check_output(
                ["git", "rev-parse", "origin/main"], text=True
            ).strip()

            if local_hash == remote_hash:
                print("\033[92m[+] Nexus is already up to date.\033[0m")
                return

            print(f"New version found! Updating from {local_hash[:7]} to {remote_hash[:7]}...")

            # 3. Surgical Pull
            subprocess.run(["git", "pull", "origin", "main"], check=True, capture_output=True)

            # 4. Dependency Refresh
            print("\033[90mRefreshing dependencies...\033[0m")
            subprocess.run(["pip", "install", "-e", "."], check=True, capture_output=True)

            print("\n\033[1;32m[+] Update successful! Nexus has been upgraded.\033[0m")
            print("\033[90mPlease restart the session to apply all changes.\033[0m")

        except Exception as e:
            print(f"\n\033[91m[-] Update failed: {e}\033[0m")
            print("You can still use the current version, but check your network connection.")

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
    def _handle_command(self, line: str) -> bool:
        """Handle a slash command. Returns True if handled."""
        if not line.startswith("/"):
            return False

        parts = line[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "exit" or cmd == "quit" or cmd == "q":
            print("Goodbye!")
            self.running = False
            return True

        elif cmd == "help" or cmd == "h":
<<<<<<< HEAD
            print("""
Available commands:
  /exit, /quit     Exit the REPL
  /clear           Clear conversation
  /history         Show message history
  /tools           List available tools
  /model <name>    Switch model
  /stream          Toggle streaming mode
  /facts           Show stored facts
  /fact <text>     Add a persistent fact
  /session         Show current session info
  /save            Save current session
  /sessions        List saved sessions
  /load <id>       Load a saved session
  /voice           Enter voice mode (Nexus speaks & listens)
  /voice tts=freetts stt=whisper  Configure voice providers
  /spawn <role>    Spawn a team agent (coder, reviewer, tester, researcher)
  /agents          List active agents
  /team            Show team status
  /plan, /p        Enter plan mode for a task
  /build           Execute approved plan steps
  /think           Show thinking engine state
  /skills          List available skills
  /skill <name>    Activate a skill
  /providers       Show configured providers
  /models          Show available models
  /context         Show conversation context
  /stats           Show session statistics
  /retry           Retry last user message
  /status          Show system status
  /mcp             MCP server status
  /plugin          Plugin management
  /doctor          Run system diagnostics
  /sync status     Sync status / push / pull / connect / disconnect
  /learn stats     Learning system / lessons / failures / clear
  /improve queue   Improvement queue / approve / reject / run
  /safety status   Safety rules / strict / permissive
  /phone           Phone-optimized mode info
  /reflect         Trigger reflection on current work
  /partner         Set personality mode
  /help            Show this help
""")
=======
            self._handle_help(args)
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            return True

        elif cmd == "clear":
            self.messages = []
            print("Conversation cleared.")
            return True

        elif cmd == "history":
            for i, msg in enumerate(self.messages[-10:]):
                role = msg.role.upper()
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
<<<<<<< HEAD
                print(f"{i+1}. [{role}] {content}")
=======
                print(f"{i + 1}. [{role}] {content}")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            return True

        elif cmd == "tools":
            for tool in self.registry.list_all():
                print(f"  {tool.name}: {tool.description}")
            return True

        elif cmd == "model":
            if args:
                asyncio.create_task(self.manager.switch_model(args))
                print(f"Model switched to: {args}")
            else:
                print(f"Current model: {self.manager.active_provider}")
            return True

        elif cmd == "stream":
            self.streaming = not self.streaming
            print(f"Streaming: {'ON' if self.streaming else 'OFF'}")
            return True

        elif cmd == "session":
            print(f"Session: {self.session.id}")
            print(f"Created: {self.session.created_at}")
            print(f"Messages: {len(self.session.messages)}")
<<<<<<< HEAD
            print(f"Tools used: {', '.join(self.session.tools_used) if self.session.tools_used else 'none'}")
=======
            print(
                f"Tools used: {', '.join(self.session.tools_used) if self.session.tools_used else 'none'}"
            )
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            return True

        elif cmd == "voice":
            parts = args.split() if args else []
            overrides = {}
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    overrides[k.strip()] = v.strip()
            asyncio.create_task(self._run_voice_mode(overrides))
            return True

        elif cmd == "spawn":
            if args:
                parts = args.split(maxsplit=1)
                role_name = parts[0].lower()
                task = parts[1] if len(parts) > 1 else None
                try:
                    role = AgentRole(role_name)
                    agent = self.team.spawn(role, task=task)
                    print(f"Spawned {agent.name} ({role.value})")
                except ValueError:
<<<<<<< HEAD
                    print(f"Invalid role: {role_name}. Valid: {', '.join(r.value for r in AgentRole)}")
=======
                    print(
                        f"Invalid role: {role_name}. Valid: {', '.join(r.value for r in AgentRole)}"
                    )
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            else:
                print("Usage: /spawn <role> [task]")
            return True

<<<<<<< HEAD
=======
        elif cmd == "template":
            if args:
                from ..config import load_config

                cfg = load_config()
                if self.team and self.team.spawn_template(args.strip(), cfg.config_dir):
                    print(f"Template {args} loaded successfully.")
                else:
                    print(f"Template not found: {args}")
            else:
                print("Usage: /template <name>")
            return True

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        elif cmd == "agents":
            print("Active agents:")
            for agent in self.team.list_agents():
                print(f"  {agent.name} ({agent.role.value}) - {agent.status.value}")
            return True

        elif cmd == "kill":
            if args:
                agent_id = args.split()[0]
                if self.team.kill(agent_id):
                    print(f"Killed agent: {agent_id}")
                else:
                    print(f"Agent not found or cannot be killed: {agent_id}")
            else:
                print("Usage: /kill <agent_id>")
            return True

        elif cmd == "team":
            print("=== Team Chat ===")
            print(self.team.format_chat())
            return True

        elif cmd == "plan" or cmd == "p":
            print("\n[PLAN MODE] Generating plan...")
            self._plan_mode = PlanMode(task=args or "Continue task", orchestrator=None)
            set_plan_mode(self._plan_mode)
            self._plan_mode.activate()
            self._plan_active = True
            asyncio.create_task(self._run_plan_mode(args))
            return True

        elif cmd == "build":
            if self._plan_mode and self._plan_mode.plan:
                print("\n[BUILD MODE] Executing plan...")
                asyncio.create_task(self._execute_plan())
            else:
                print("No active plan. Use /plan first.")
            return True

        elif cmd == "abort":
            print("Aborting current task...")
            self.running = False
            return True

        elif cmd == "think":
            print("Thinking panel: ON (always visible in this REPL)")
            return True

        elif cmd == "save":
            path = self.session_loader.save_session(self.session)
            print(f"Session saved: {path}")
            return True

        elif cmd == "sessions":
            print(self.session_loader.format_session_list())
            return True

        elif cmd == "load":
            if args:
                session = self.session_loader.load_session(args)
                if session:
                    self.session = session
                    self.messages.clear()
                    for msg in session.messages[-20:]:
                        self.messages.append(Message(role=msg["role"], content=msg["content"]))
                    print(f"Loaded session: {session.id}")
                else:
                    print(f"Session not found: {args}")
            else:
                print(self.session_loader.format_session_list())
            return True

        elif cmd == "skills":
            from ..skills import SkillsManager
<<<<<<< HEAD
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            sm = SkillsManager()
            sm.load_all()
            print("\nAvailable skills:")
            for s in sm.list_all():
                active = "●" if s.name in sm.list_active() else "○"
                print(f"  {active} {s.name} ({s.category}) — {s.description[:50]}")
            return True

        elif cmd == "skill":
            if args:
                from ..skills import SkillsManager
<<<<<<< HEAD
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                sm = SkillsManager()
                sm.load_all()
                if sm.activate(args):
                    print(f"Activated skill: {args}")
                else:
                    print(f"Skill not found: {args}")
            else:
                print("Usage: /skill <name>")
            return True

        elif cmd == "providers":
            print("\nConfigured providers:")
            for name, cfg in self.manager.configs.items():
                active = "●" if name == self.manager.active_provider else "○"
                print(f"  {active} {name} — {cfg.provider_type} / {cfg.model}")
            return True

        elif cmd == "models":
            print("\nAvailable models:")
            for provider in self.manager.configs.values():
                print(f"  [{provider.name}] {provider.model}")
            return True

        elif cmd == "context":
            print("\n" + self.memory.get_context_summary())
            return True

        elif cmd == "stats":
<<<<<<< HEAD
            print(f"\nAgent Statistics:")
=======
            print("\nAgent Statistics:")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            print(f"  Turn count: {self.session.id[:8]}")
            print(f"  Messages: {len(self.messages)}")
            print(f"  Tool calls: {self._tool_call_count}")
            print(f"  Active agents: {len(self.team.list_agents()) if self.team else 0}")
            return True

        elif cmd == "retry":
<<<<<<< HEAD
            print("Retry: not yet implemented (last failed tool)")
            return True

        elif cmd == "undo":
            print("Undo: not yet implemented")
            return True

        elif cmd == "diff":
            print("Diff: not yet implemented (requires git integration)")
            return True

        elif cmd == "status":
            print(f"\nNEXUS v0.1.0")
=======
            if self._last_failed_tool_call:
                tool = self.registry.get(self._last_failed_tool_call.name)
                if tool:
                    print(f"Retrying: {self._last_failed_tool_call.name}")
                    asyncio.create_task(self._retry_tool(self._last_failed_tool_call, tool))
                    return True
            print("No failed tool to retry.")
            return True

        elif cmd == "undo":
            if not self._file_snapshots:
                print("No file changes to undo.")
                return True
            from pathlib import Path
            undone = []
            for path, original in list(self._file_snapshots.items()):
                try:
                    Path(path).write_text(original)
                    undone.append(path)
                    del self._file_snapshots[path]
                except Exception as e:
                    print(f"Failed to undo {path}: {e}")
            print(f"Undone {len(undone)} file(s): {', '.join(undone)}")
            return True

        elif cmd == "diff":
            import subprocess
            try:
                result = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True)
                if result.returncode == 0:
                    print(result.stdout or "No changes.")
                else:
                    print("Not a git repository or git not available.")
            except FileNotFoundError:
                print("Git not found.")
            return True

        elif cmd == "status":
            print("\nNEXUS v0.1.0")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            print(f"  Status: {'● ONLINE' if self.running else '○ OFFLINE'}")
            print(f"  Model: {self.manager.active_provider}")
            print(f"  Session: {self.session.id[:16]}")
            print(f"  Messages: {len(self.messages)}")
            print(f"  Plan mode: {'ON' if self._plan_active else 'OFF'}")
            print(f"  Agents: {len(self.team.list_agents()) if self.team else 0}")
            return True

        elif cmd == "facts":
            facts = self.memory.get_all_facts()
            if facts:
                print("\nStored facts:")
                for key, value in facts.items():
                    print(f"  {key}: {value}")
            else:
                print("No facts stored.")
            return True

        elif cmd == "fact":
            parts = args.split(maxsplit=1)
            if len(parts) >= 2:
                key, value = parts[0], parts[1]
                self.memory.add_fact(key, value)
                print(f"Added fact: {key} = {value}")
            else:
                print("Usage: /fact add <key> <value>")
            return True

        elif cmd == "mcp":
            print("MCP: use 'nexus mcp list/add/remove' from CLI")
            return True

        elif cmd == "plugin":
            from ..plugins import get_plugin_manager
<<<<<<< HEAD
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            pm = get_plugin_manager()
            parts = args.split(maxsplit=1) if args else []
            subcmd = parts[0] if parts else "list"
            subargs = parts[1] if len(parts) > 1 else ""
<<<<<<< HEAD
            
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            if subcmd == "list":
                plugins = pm.list_all()
                if not plugins:
                    print("No plugins loaded.")
                for p in plugins:
<<<<<<< HEAD
                    status = "✓ enabled" if pm.is_enabled(p.metadata.name) else "✗ disabled"
=======
                    status = "[+] enabled" if pm.is_enabled(p.metadata.name) else "[-] disabled"
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                    error = f" [ERROR: {p.error}]" if p.error else ""
                    print(f"  {p.metadata.name} v{p.metadata.version} — {status}{error}")
            elif subcmd == "enable" and subargs:
                if pm.enable(subargs):
                    print(f"Enabled: {subargs}")
                else:
                    print(f"Plugin not found: {subargs}")
            elif subcmd == "disable" and subargs:
                if pm.disable(subargs):
                    print(f"Disabled: {subargs}")
                else:
                    print(f"Plugin not found: {subargs}")
            else:
                print("Usage: /plugin list|enable <name>|disable <name>")
            return True

        elif cmd == "doctor":
            print("\n[DIAGNOSTICS]")
<<<<<<< HEAD
            print(f"  Config: /root/.nexus/config.json exists")
            print(f"  Providers: {len(self.manager.configs)} configured")
            print(f"  Tools: {len(self.registry.list_all())} available")
            print(f"  Termux: available")
=======
            print("  Config: /root/.nexus/config.json exists")
            print(f"  Providers: {len(self.manager.configs)} configured")
            print(f"  Tools: {len(self.registry.list_all())} available")
            print("  Termux: available")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            print(f"  Plugins: {len(get_plugin_manager().list_all())} loaded")
            print(f"  Safety rules: {len(self.safety.rules)} loaded")
            print(f"  Learning lessons: {self.learning.get_stats()['total_lessons']}")
            print(f"  Sync endpoints: {len(self.sync_engine.endpoints)}")
            print(f"  Improvements pending: {len(self.improver.get_improvement_queue())}")
            return True

        # --- SYNC commands ---
        elif cmd == "sync":
            parts = args.split(maxsplit=1) if args else []
            sub = parts[0] if parts else "status"
            subargs = parts[1] if len(parts) > 1 else ""

            if sub == "status":
                print(self.sync_engine.format_status())
            elif sub == "push":
                result = self.sync_engine.push(subargs or "default")
                if result.get("success"):
<<<<<<< HEAD
                    print(f"✓ Pushed {result.get('items', 0)} item(s)")
                    if result.get("gist_url"):
                        print(f"  Gist: {result['gist_url']}")
                else:
                    print(f"✗ Push failed: {result.get('error')}")
            elif sub == "pull":
                result = self.sync_engine.pull(subargs or "default")
                if result.get("success"):
                    print(f"✓ Pulled {result.get('items', 0)} item(s)")
                    if result.get("conflicts"):
                        print(f"⚠ Conflicts: {', '.join(result['conflicts'])}")
                else:
                    print(f"✗ Pull failed: {result.get('error')}")
            elif sub == "connect":
                print("Use: nexus sync connect <github-gist|local|git> --token <token> --path <path>")
=======
                    print(f"[+] Pushed {result.get('items', 0)} item(s)")
                    if result.get("gist_url"):
                        print(f"  Gist: {result['gist_url']}")
                else:
                    print(f"[-] Push failed: {result.get('error')}")
            elif sub == "pull":
                result = self.sync_engine.pull(subargs or "default")
                if result.get("success"):
                    print(f"[+] Pulled {result.get('items', 0)} item(s)")
                    if result.get("conflicts"):
                        print(f"[!] Conflicts: {', '.join(result['conflicts'])}")
                else:
                    print(f"[-] Pull failed: {result.get('error')}")
            elif sub == "connect":
                print(
                    "Use: nexus sync connect <github-gist|local|git> --token <token> --path <path>"
                )
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            elif sub == "disconnect":
                if subargs and self.sync_engine.disconnect(subargs):
                    print(f"Disconnected: {subargs}")
                else:
                    print("Usage: /sync disconnect <name>")
            else:
                print("Usage: /sync status|push [endpoint]|pull [endpoint]|connect|disconnect")
            return True

        # --- LEARN commands ---
        elif cmd == "learn":
            parts = args.split(maxsplit=1) if args else []
            sub = parts[0] if parts else "stats"

            if sub == "stats":
                print(self.learning.format_summary())
            elif sub == "lessons":
                lessons = self.learning._load_all_lessons()[:5]
                if not lessons:
                    print("No lessons yet. Keep building!")
<<<<<<< HEAD
                for l in lessons:
                    rate = l.success_count / max(1, l.success_count + l.failure_count)
                    print(f"\n  [{l.lesson_id}] {l.title}")
                    print(f"    {l.summary[:80]}...")
                    print(f"    Success: {rate:.0%} | Triggers: {', '.join(l.trigger_conditions[:2])}")
            elif sub == "failures":
                import json
                failures = sorted(self.learning.failures_dir.glob("*.json"),
                                 key=lambda f: f.stat().st_mtime, reverse=True)[:5]
=======
                for lesson in lessons:
                    rate = lesson.success_count / max(1, lesson.success_count + lesson.failure_count)
                    print(f"\n  [{lesson.lesson_id}] {lesson.title}")
                    print(f"    {lesson.summary[:80]}...")
                    print(
                        f"    Success: {rate:.0%} | Triggers: {', '.join(lesson.trigger_conditions[:2])}"
                    )
            elif sub == "failures":
                import json

                failures = sorted(
                    self.learning.failures_dir.glob("*.json"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )[:5]
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                for f in failures:
                    d = json.loads(f.read_text())
                    print(f"  [{d['timestamp'][:16]}] {d['tool_name']} — {d['error_type']}")
                    print(f"    {d['error'][:80]}...")
            else:
                print("Usage: /learn stats|lessons|failures")
            return True

        # --- IMPROVE commands ---
        elif cmd == "improve":
            parts = args.split(maxsplit=1) if args else []
            sub = parts[0] if parts else "queue"

            if sub == "queue":
                print(self.improver.format_improvement_queue())
            elif sub == "approve" and len(parts) > 1:
                if self.improver.approve(parts[1]):
<<<<<<< HEAD
                    print(f"✓ Approved: {parts[1]}. Use /improve apply {parts[1]} to apply.")
=======
                    print(f"[+] Approved: {parts[1]}. Use /improve apply {parts[1]} to apply.")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                else:
                    print(f"Improvement not found: {parts[1]}")
            elif sub == "apply" and len(parts) > 1:
                result = self.improver.apply(parts[1])
                if result.get("success"):
<<<<<<< HEAD
                    print(f"✓ Applied: {result.get('message')}")
                else:
                    print(f"✗ Failed: {result.get('error')}")
            elif sub == "run":
                print("\n🤖 Running self-improvement loop...")
                session_summary = {"tasks_completed": len(self.session.messages) // 2, "failures": []}
                improvements = self.improver.run_improvement_loop(
                    [],  # failures list
                    task_context=str(self.session.messages[-1]["content"])[:100] if self.session.messages else "",
                    provider_manager=self.manager,
                )
                if improvements:
                    print(f"✓ Generated {len(improvements)} improvement(s):")
                    for imp in improvements:
                        print(f"  • {imp.title}")
=======
                    print(f"[+] Applied: {result.get('message')}")
                else:
                    print(f"[-] Failed: {result.get('error')}")
            elif sub == "run":
                print("\n[improve] Running self-improvement loop...")
                {"tasks_completed": len(self.session.messages) // 2, "failures": []}
                improvements = self.improver.run_improvement_loop(
                    [],  # failures list
                    task_context=str(self.session.messages[-1]["content"])[:100]
                    if self.session.messages
                    else "",
                    provider_manager=self.manager,
                )
                if improvements:
                    print(f"[+] Generated {len(improvements)} improvement(s):")
                    for imp in improvements:
                        print(f"  * {imp.title}")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                else:
                    print("  No improvements needed right now.")
            elif sub == "reject" and len(parts) > 1:
                if self.improver.reject(parts[1]):
                    print(f"Rejected: {parts[1]}")
            else:
                print("Usage: /improve queue|approve <id>|apply <id>|run|reject <id>")
            return True

        # --- SAFETY commands ---
        elif cmd == "safety":
            parts = args.split(maxsplit=1) if args else []
            sub = parts[0] if parts else "status"

            if sub == "status":
                print(f"\nSafety: {'STRICT' if self.safety._strict_mode else 'PERMISSIVE'}")
                print(f"Rules loaded: {len(self.safety.rules)}")
                print(f"Violations this session: {len(self.safety._violations)}")
                print(f"Files read: {len(self.safety.get_read_files())}")
                print(f"\nViolation summary:\n{self.safety.get_violation_summary()}")
            elif sub == "strict":
                self.safety.enable_strict_mode()
                print("Strict mode enabled — warnings become blocks")
            elif sub == "permissive":
                self.safety.disable_strict_mode()
                print("Permissive mode — warnings are suggestions only")
            elif sub == "rules":
<<<<<<< HEAD
                for rid, rule in list(self.safety.rules.items())[:10]:
=======
                for _rid, rule in list(self.safety.rules.items())[:10]:
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
                    print(f"  [{rule.level.name}] {rule.name}: {rule.description[:50]}")
            else:
                print("Usage: /safety status|strict|permissive|rules")
            return True

        # --- PHONE mode ---
        elif cmd == "phone":
            if self.phone.enabled:
                print(f"Phone mode: ON ({self.phone.profile.name})")
            else:
                print("Phone mode: OFF. Set NEXUS_PHONE_MODE=1 to enable.")

        # --- REFLECTION ---
        elif cmd == "reflect":
            print(self.personality.reflection_ask())
            print(self.learning.ask_reflection())

        # --- PARTNER ---
        elif cmd == "partner":
            print(f"\n{self.personality.greet()}")
            print(f"Mode: {self.personality.config.mode.name}")
            print(f"Celebrate wins: {self.personality.config.celebrate_wins}")
            print(f"Proactive: {self.personality.config.proactive_suggestions}")

        return False

    async def _run_plan_mode(self, task: str) -> None:
        """Run plan mode for the given task."""
        if not self._plan_mode:
            return
<<<<<<< HEAD
        
        try:
            plan = await self._plan_mode.generate_plan(self.manager, self.messages)
            print(self._plan_mode.format_for_display())
            
=======

        try:
            await self._plan_mode.generate_plan(self.manager, self.messages)
            print(self._plan_mode.format_for_display())

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            # Wait for user input
            try:
                action = input("Action (A=approve all, S=skip low, Q=quit): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("Plan mode cancelled.")
                self._plan_active = False
                return
<<<<<<< HEAD
            
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            if action == "a":
                self._plan_mode.approve_all()
                print("All steps approved. Use /build to execute.")
            elif action == "s":
                self._plan_mode.skip_low_priority()
                print("Low priority steps skipped.")
            elif action == "q":
                self._plan_mode.deactivate()
                self._plan_active = False
                print("Plan mode cancelled.")
        except Exception as e:
            print(f"Plan mode error: {e}")
            self._plan_active = False

    async def _execute_plan(self) -> None:
        """Execute the current plan."""
        if not self._plan_mode or not self._plan_mode.plan:
            return
<<<<<<< HEAD
        
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        approved = self._plan_mode.get_approved_steps()
        if not approved:
            print("No approved steps to execute.")
            return
<<<<<<< HEAD
        
        print(f"\nExecuting {len(approved)} approved steps...")
        tracker = ProgressTracker(len(approved), "Executing plan")
        
=======

        print(f"\nExecuting {len(approved)} approved steps...")
        tracker = ProgressTracker(len(approved), "Executing plan")

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        for step in approved:
            tracker.step(step.description)
            if step.tool_name:
                tool = self.registry.get(step.tool_name)
                if tool:
                    try:
                        result = await tool.execute(**step.tool_args)
                        step.result = result.content[:100]
                    except Exception as e:
                        step.error = str(e)
<<<<<<< HEAD
        
=======

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
        tracker.finish()
        self._plan_active = False

    async def run(self) -> None:
        """Run the REPL."""
<<<<<<< HEAD
        greeting = self.personality.greet()
        print(f"""
╔══════════════════════════════════════════════════════════╗
║                    Nexus AI Agent                        ║
║                                                           ║
║  {greeting:<53} ║
║  Type /help for commands, or just start chatting.         ║
╚══════════════════════════════════════════════════════════╝
""")

        while self.running:
            try:
                line = input(self._get_prompt()).strip()
                
                if not line:
                    continue

                # Handle slash commands
                if self._handle_command(line):
                    continue

                # Handle regular input
                await self._generate_response(line)

            except KeyboardInterrupt:
                print("\n(Use /exit to quit)")
                continue
            except EOFError:
                break
            except Exception as e:
                self.learning.record_failure(str(e), {"type": type(e).__name__}, "")
                print(f"{self.personality.failure()} {e}")
=======
        # Check first run status
        from ..config import load_config, save_config

        cfg = load_config()
        if cfg.first_run:
            from .welcome import display_welcome

            display_welcome()
            # Update first_run to False and save
            cfg.first_run = False
            save_config(cfg)

        print(f"\n{self.personality.greet()} Type /help for commands.")

        # Verify provider is working on startup
        await self._ensure_provider()

        # Auto-detect project
        from nexus.sessions import ProjectContext
        project = ProjectContext()
        detected = project.detect_project()
        if detected:
            project.load()
            cyan = "\033[36m"
            blue = "\033[34m"
            dim = "\033[90m"
            reset = "\033[0m"
            print(f"  {blue}╼{reset} {dim}nexus/{reset}{cyan}project{reset} {detected}")
            context_summary = project.format_context()
            if context_summary != "(no project context)":
                print(f"    {dim}{context_summary}{reset}")

        # Handle SIGINT (Ctrl+C) gracefully
        import signal

        def signal_handler(sig, frame):
            cyan = "\033[36m"
            blue = "\033[34m"
            dim = "\033[90m"
            reset = "\033[0m"
            print(f"\n  {blue}╼{reset} {dim}nexus/{reset}{cyan}core{reset} {dim}interrupt signal received. returning to prompt...{reset}")
            # We raise a KeyboardInterrupt to be caught by the inner loop
            # Since we are in an async loop, we need a way to break the await
            # The simplest way for a synchronous signal handler is to trigger
            # a KeyboardInterrupt in the main thread.
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, signal_handler)

        while self.running:
            try:
                try:
                    line = input(self._get_prompt()).strip()

                    if not line:
                        continue

                    # Handle slash commands
                    if line.startswith("/tasks"):
                        print(self.tasks.get_checklist())
                        continue
                    if self._handle_command(line):
                        continue

                    # Handle regular input
                    await self._generate_response(line)
                except Exception as e:
                    # --- Global Error Boundary (Panic Handler) ---
                    import datetime
                    import traceback
                    from pathlib import Path

                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    panic_file = Path.home() / ".nexus" / f"panic_{timestamp}.log"
                    panic_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(panic_file, "w") as f:
                        f.write(f"Panic occurred at {timestamp}\n")
                        f.write(f"Input: {line if 'line' in locals() else 'N/A'}\n")
                        f.write("-" * 40 + "\n")
                        f.write(traceback.format_exc())

                    print("\n\033[41m\033[37m PANIC \033[0m")
                    print(
                        "\033[91mAn unexpected error occurred. The session was preserved, but the current operation failed.\033[0m"
                    )
                    print(f"\033[90mPanic report saved to: {panic_file}\033[0m")
                    print(f"\n{self.personality.failure()} Recovering to prompt...\n")

                    # Record failure in learning engine
                    try:
                        self.learning.record_failure(
                            tool_name="REPL_CORE",
                            args={"input": line if "line" in locals() else "N/A"},
                            error=str(e),
                            context={"session": self.session.id},
                        )
                    except Exception:
                        pass

                except KeyboardInterrupt:
                    print("\n(Use /exit to quit)")
                    continue
                except EOFError:
                    break
            except Exception as e:
                # This is the absolute last resort wrapper
                print(f"\033[91mCritical System Failure: {e}\033[0m")
                break
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

        self._save_history()
        self.memory.save_session(self.session)
        summary = self.learning.end_session(self.session.id, "completed")
        if summary.get("failures", 0) > 0:
            print(f"\n{self.personality.reflection_ask()}")

<<<<<<< HEAD

    def _on_team_message(self, msg) -> None:
        """Handle incoming team messages."""
        if msg.msg_type == "system":
            print(f"\n[team] {msg.content}")
        else:
            color_map = {
                "planner": "\033[94m",    # blue
                "coder": "\033[92m",       # green
                "reviewer": "\033[93m",    # yellow
                "tester": "\033[95m",      # magenta
                "researcher": "\033[96m",  # cyan
            }
            color = color_map.get(msg.agent_name.split("_")[0] if "_" in msg.agent_name else "", "\033[92m")
            reset = "\033[0m"
            print(f"\n[{color}{msg.agent_name}{reset}]: {msg.content}")

    def _on_thinking_update(self, event) -> None:
        """Handle thinking engine updates."""
        event_type, step = event
        
        if event_type == "start":
            if step.state == ThinkingState.ANALYZING:
                self._show_loading("Analyzing task...")
=======
    def _on_team_message(self, msg) -> None:
        """Handle incoming team messages with sci-fi styling."""
        cyan = "\033[36m"
        blue = "\033[34m"
        bold = "\033[1m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        if msg.msg_type == "system":
            # Strip the [spawn], [done], [fail] brackets from the content
            content = msg.content.replace("[spawn]", f"{blue}⫸{reset}").replace("[done]", f"{blue}✔{reset}").replace("[fail]", f"{blue}✘{reset}")
            print(f"\n  {blue}╼{reset} {dim}nexus/{reset}{cyan}team{reset} {content}")
        else:
            print(f"\n  {blue}╼{reset} {dim}nexus/{reset}{cyan}{msg.agent_name.lower()}{reset} {bold}»{reset} {msg.content}")
            if msg.msg_type == "message":
                self.messages.append(Message(role="assistant", content=f"[{msg.agent_name}]: {msg.content}"))

    def _on_thinking_update(self, event) -> None:
        """Handle thinking engine updates with atmospheric UI."""
        event_type, step = event

        if event_type == "start":
            if step.state == ThinkingState.ANALYZING:
                self._show_loading("nexus/thinking")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
            elif step.state == ThinkingState.PLANNING:
                pass  # Planning is internal
            elif step.state == ThinkingState.EXECUTING:
                self._show_tool_start(step)
            elif step.state == ThinkingState.REVIEWING:
                pass  # Reviewing is internal
            elif step.state == ThinkingState.COMPLETE:
                self._show_complete(step)
        elif event_type == "finish":
            if step.state == ThinkingState.ANALYZING:
                self._hide_loading()
            elif step.state == ThinkingState.EXECUTING:
                self._render_tool_result(step)
            elif step.state == ThinkingState.COMPLETE:
                self._show_task_complete(step)

    def _show_loading(self, message: str) -> None:
        """Show dynamic loading indicator."""
        if not self._first_token_received:
            cyan = "\033[36m"
            reset = "\033[0m"
            sys.stdout.write(f"\r{cyan}◈{reset} {message}...")
            sys.stdout.flush()

    def _hide_loading(self) -> None:
        """Hide loading indicator."""
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def _show_tool_start(self, step) -> None:
        """Show tool execution start with sci-fi styling."""
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        if step.tool_args:
            preview = {k: (str(v)[:40] + "..." if len(str(v)) > 40 else str(v)) for k, v in list(step.tool_args.items())[:3]}
            args_str = f"{dim}(" + ", ".join(f"{k}={repr(v)}" for k, v in preview.items()) + f"){reset}"
            print(f"  {cyan}╼{reset} {step.tool_name} {args_str}")

    def _render_tool_result(self, step) -> None:
        """Render tool execution results with atmospheric styling."""
        import shutil

        term_width = shutil.get_terminal_size((80, 20)).columns

        green = "\033[32m"
        red = "\033[31m"
        dim = "\033[90m"
        reset = "\033[0m"

        if step.state == ThinkingState.ERROR:
            print(f"  {red}╰ Error:{reset} {step.detail or 'Execution failed'}")
        else:
            duration = f"{dim}[{step.duration_ms:.0f}ms]{reset}" if step.duration_ms else ""
            print(f"  {green}╰ Result{reset} {duration}")

            if step.tool_result:
                content = step.tool_result.strip()
                max_chars = 300 if term_width < 60 else 500

                indent = "    "
                if len(content) > max_chars:
                    lines = content.split("\n")
                    shown = f"\n{indent}".join(lines[:5])
                    print(f"{indent}{shown}\n{indent}{dim}... (+{len(content) - len(shown)} chars){reset}")
                else:
                    indented_content = content.replace("\n", f"\n{indent}")
                    print(f"{indent}{indented_content}")

    def _show_complete(self, step) -> None:
        """Show step complete."""
        self._tool_call_count += 1

    def _show_task_complete(self, step) -> None:
        """Show task complete summary."""
        elapsed = step.duration_ms / 1000.0 if step.duration_ms else 0
<<<<<<< HEAD
        tool_count = self._tool_call_count
        print(f"\n\033[92m✅ Done in {elapsed:.1f}s\033[0m — {tool_count} tool call(s)")
=======
        print(f"\n[done] {elapsed:.1f}s, {self._tool_call_count} tool(s)")
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

    async def run_single(self, task: str) -> tuple[str, bool]:
        """Run a single task and return (result, was_streamed)."""
        return await self._generate_response(task, print_result=False), self.streaming


async def run_repl(config: dict[str, Any] | None = None) -> None:
    """Run the REPL."""
    repl = REPL(config)
    await repl._ensure_provider()
    await repl.run()


async def run_task(task: str, config: dict[str, Any] | None = None) -> tuple[str, bool]:
    """Run a single task. Returns (result, was_streamed)."""
    repl = REPL(config)
    await repl._ensure_provider()
    result, streamed = await repl.run_single(task)
    await repl.manager.close_all()
    return result, streamed
<<<<<<< HEAD


=======
>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)
