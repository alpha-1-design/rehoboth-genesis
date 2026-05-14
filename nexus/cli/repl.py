"""Interactive REPL for Nexus."""

import asyncio
import os
import readline
import sys
import time
from typing import Any

from ..providers import Message, get_manager
from ..tools import get_registry, ToolResult
from ..memory import get_memory
from ..agent import get_orchestrator
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


class REPL:
    """Interactive REPL for Nexus."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.orchestrator = get_orchestrator()
        self.manager = self.orchestrator.pm
        self.registry = self.orchestrator.tools
        self.memory = self.orchestrator.memory
        self.session = self.memory.create_session()
        self.messages: list[Message] = []
        self.running = True
        self.streaming = True
        self.team: MultiAgentTeam | None = init_team(lead_name="nexus", pm=self.manager)
        
        # New systems
        self.safety: SafetyEngine = get_safety_engine()
        self.sync_engine = get_sync_engine()
        self.learning = get_learning_engine()
        self.improver = get_self_improver()
        self.personality: Personality = get_personality()
        self.phone: PhoneMode = get_phone_mode()
        
        # Session auto-load
        self.session_loader = get_session_loader()
        
        # Initialize multi-agent team
        self.team = init_team(lead_name="nexus", pm=self.manager)
        self.team.on_message(self._on_team_message)

        # Initialize project indexing for Neural Layers
        from ..memory import ProjectIndexer
        self.indexer = ProjectIndexer(self.memory)

        # Register thinking callback
        self.thinking_engine = get_thinking_engine()
        self.thinking_engine.on_update(self._on_thinking_update)

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
        print("\n\033[33m[!] No working AI provider found.\033[0m")
        print("Trying OpenCode Zen free models (no API key needed)...\n")

        try:
            from ..providers.base import PROVIDER_REGISTRY
            from ..config import ProviderConfig, save_config
            from .. import config as cfg_module

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

            prov = PROVIDER_REGISTRY["openai"]({
                "api_key": "",
                "base_url": "https://opencode.ai/zen/v1",
                "model": "minimax-m2.5-free",
                "timeout": 120,
            })
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

            print("\033[92m✓ Connected to OpenCode Zen (minimax-m2.5-free)\033[0m\n")
        except Exception as e:
            print(f"\n\033[91m✗ Could not connect to OpenCode Zen: {e}\033[0m")
            print("\nRun \033[1mnexus setup\033[0m to configure a provider manually.\n")

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
                                self.messages.append(Message(role="assistant", content=msg["content"]))
                        print(f"Resumed session. {len(self.messages)} messages loaded.")
                else:
                    print("Starting fresh session.")
            except (EOFError, KeyboardInterrupt):
                    print("Starting fresh session.")

    def _check_tool_safety(self, tool_name: str, arguments: dict) -> tuple[bool, ToolResult | None]:
        """Check tool call against safety rules with visual scanning effect."""
        # Visual "Security Scan" effect
        import random
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        symbols = ["-", "\\", "|", "/", "◢", "◣", "◤", "◥"]
        print(f"  {dim}SCANNING PERMISSIONS... {reset}", end="", flush=True)
        for _ in range(5):
            s = random.choice(symbols)
            sys.stdout.write(f"\b{cyan}{s}{reset}")
            sys.stdout.flush()
            time.sleep(0.05)
        sys.stdout.write("\b  \n")
        
        path_keys = ("path", "filePath", "file_path", "directory", "workdir")
        context: dict = {"tool": tool_name, "args": arguments}
        for key in path_keys:
            if key in arguments and arguments[key]:
                context["path"] = arguments[key]
                break
        if "command" in arguments:
            context["command"] = arguments["command"]

        violations = self.safety.check(context)
        if not violations:
            return True, None

        proceed, reason = self.safety.should_proceed(violations)
        if not proceed:
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
        return str(Path.home() / ".nexus" / ".history")

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
        messages = [Message(role="system", content=self._get_system_prompt())] + self.messages
        messages.append(Message(role="user", content=text))

        tools = self.registry.to_openai_format()

        try:
            response = await self.manager.complete(messages, tools)
            for tc in response.tool_calls:
                tool = self.registry.get(tc.name)
                if tool:
                    result = await tool.execute(**tc.arguments)
                    messages.append(Message(
                        role="tool", content=result.content,
                        name=tc.name, tool_call_id=tc.id,
                    ))

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

    async def _handle_orchestrator_event(self, event):
        """Map orchestrator thinking events to REPL visual effects."""
        # event is a tuple of ("type", step)
        event_type, step = event

        if step.state == ThinkingState.ANALYZING:
            self._show_context_pulse()
        elif step.state == ThinkingState.EXECUTING:
            if step.tool_name in ("write", "edit"):
                path = step.tool_args.get("path", "file")
                self._show_kinetic_stream(path)
            else:
                self._show_tool_start(step.tool_name)
        elif step.state == ThinkingState.COMPLETE:
            self._show_task_complete()
        elif step.state == ThinkingState.ERROR:
            print(f"\n\033[91m◈ ERROR: {step.detail}\033[0m")

    async def _stream_to_console(self, content: str):
        """Callback for streaming assistant responses."""
        print(content, end="", flush=True)

    def _get_system_prompt(self) -> str:
        """Get the multi-layered system prompt for the agent (The Memory Harness)."""
        # Layer 1: Core Identity & Voice
        voice_prompt = self.personality.get_voice_system_prompt()
        
        # Layer 2: Safety Mode & Operational Guidelines
        safety_mode = self.safety.get_mode().name
        safety_guidelines = f"Current Safety Mode: {safety_mode}\n"
        if safety_mode == "READ_ONLY":
            safety_guidelines += "- You are in READ-ONLY mode. Do not attempt to modify files.\n"
        elif safety_mode == "STRICT":
            safety_guidelines += "- STRICT mode active. You MUST read files before editing and validate after writing.\n"

        # Layer 3: Project Architecture & Environment
        project_summary = "Environment: Termux (Android)\n"
        project_summary += f"Project Structure: {self.indexer.get_summary()}\n"
        
        # Layer 4: Active Working Memory (Last 5 files read/edited)
        recent_files = self.safety.get_read_files()[-5:]
        working_memory = ""
        if recent_files:
            working_memory = "Recently Accessed Files (Working Memory):\n"
            for f in recent_files:
                working_memory += f"- {f}\n"

        # Layer 5: User Facts & Session Context
        user_context = self.memory.get_context_summary()

        return f"""{voice_prompt}

### OPERATIONAL GUIDELINES
{safety_guidelines}
- You are an AI coding assistant powered by Nexus.
- Focus on being helpful, accurate, and efficient.
- Use tools to gather information before making decisions.

### PROJECT CONTEXT
{project_summary}

### WORKING MEMORY
{working_memory}

### USER & SESSION MEMORY
{user_context}

### AVAILABLE TOOLS
{self._format_tools()}

When using tools, always provide clear feedback about what you're doing.
"""

    def _format_tools(self) -> str:
        """Format tools for the system prompt."""
        lines = []
        for tool in self.registry.list_all():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    async def _generate_response(self, user_input: str, print_result: bool = True) -> str:
        """Generate a response from the AI with dynamic context pulsing."""
        # Check for proactive insights if user is 'free' (idle/short input)
        if len(user_input.split()) < 3:
            insight = self._get_proactive_insight()
            if insight:
                print(f"\n  \033[36m◈ PROACTIVE INSIGHT: {insight}\033[0m")

        # Visual 'Context Pulse'
        self._show_context_pulse()
        
        # Add user message
        self.messages.append(Message(role="user", content=user_input))
        self.session.messages.append({"role": "user", "content": user_input})

        # Auto-spawn agents for complex tasks
        if self.team:
            spawned = self.team.auto_spawn_for_task(user_input)
            if spawned:
                self._show_neural_branching(spawned)

        # Build messages with system prompt
        messages = [Message(role="system", content=self._get_system_prompt())] + self.messages

        # Get tools
        tools = self.registry.to_openai_format()

        try:
            if self.streaming and not tools:
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
                            if not proceed:
                                result = error_result
                            else:
                                if tool_call.name == "Read":
                                    for path_key in ("path", "filePath", "file_path"):
                                        if path_key in tool_call.arguments:
                                            self.safety.mark_file_read(tool_call.arguments[path_key])
                                            break
                                
                                # Visual Kinetic Write for file writes
                                if tool_call.name == "write" or tool_call.name == "edit":
                                    self._show_kinetic_stream(tool_call.arguments.get("path", "file"))
                                
                                result = await tool.execute(**tool_call.arguments)
                                
                                # THE REFINER'S FIRE: Post-Execution Validation
                                if result.success and tool_call.name in ("write", "edit"):
                                    validation_passed, validation_error = await self._run_refiners_fire(tool_call.arguments.get("path"))
                                    if not validation_passed:
                                        result.success = False
                                        result.content = f"[REJECTED BY FIRE] The work was performed, but it failed the integrity check:\n{validation_error}\n\n[RECOVERY] I have detected an impurity in the logic. You must fix this error before proceeding."
                                
                                if not result.success:
                                    result.content = await self._handle_tool_failure(
                                        tool_call.name, tool_call.arguments, result.error or result.content
                                    )
                            tool_results.append((tool_call, result))
                            if not result.success:
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

                # If tools were called, send results back and get final response
                if tool_results:
                    for tc, res in tool_results:
                        messages.append(Message(
                            role="tool",
                            content=res.content,
                            name=tc.name,
                            tool_call_id=tc.id,
                        ))
                    final_response = await self.manager.complete(messages, tools)
                    final_content = final_response.content
                    if print_result and final_content:
                        cyan = "\033[36m"
                        reset = "\033[0m"
                        print(f"\n{cyan}◈{reset} {final_content}")
                    streaming_done = True
                    return final_content
                else:
                    final_content = response_text
                    streaming_done = True
                    return response_text

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
                            
                            # Visual Kinetic Write
                            if tool_call.name == "write" or tool_call.name == "edit":
                                self._show_kinetic_stream(tool_call.arguments.get("path", "file"))
                                
                            result = await tool.execute(**tool_call.arguments)
                            if not result.success:
                                result.content = await self._handle_tool_failure(
                                    tool_call.name, tool_call.arguments, result.error or result.content
                                )
                        if not result.success:
                            self.learning.record_failure(
                                tool_name=tool_call.name,
                                args=tool_call.arguments,
                                error=result.error or result.content,
                                context={"session": self.session.id},
                            )
                        
                        # Add assistant's tool_call message to history
                        messages.append(Message(
                            role="assistant",
                            content=response.content,
                            tool_calls=[tool_call]
                        ))
                        
                        # Add tool result message
                        messages.append(Message(
                            role="tool",
                            content=result.content,
                            name=tool_call.name,
                            tool_call_id=tool_call.id,
                        ))

                # Get final response (may be after tool results)
                response = await self.manager.complete(messages, tools)
                final_content = response.content
                if print_result and final_content:
                    cyan = "\033[36m"
                    reset = "\033[0m"
                    print(f"\n{cyan}◈{reset} {final_content}")
                streaming_done = False
                return final_content

            if print_result and final_content and not streaming_done:
                print(final_content)

            self.memory.save_session(self.session)
            return final_content

        except Exception as e:
            return f"Error: {e}"

    def _get_proactive_insight(self) -> str | None:
        """Fetch a proactive suggestion from the Shadow Architect."""
        import random
        insights_fact = self.memory.get_fact("proactive_insights")
        if insights_fact and isinstance(insights_fact.value, list) and insights_fact.value:
            return random.choice(insights_fact.value)
        return None

    def _show_tech_stack_loader(self, stack: str) -> None:
        """Visual effect for tech stack initialization."""
        cyan = "\033[36m"
        green = "\033[32m"
        dim = "\033[90m"
        reset = "\033[0m"
        bold = "\033[1m"
        
        icons = {
            "python": "🐍 [PYTHON_ENV]",
            "node": "🟢 [NODE_JS]",
            "react": "⚛️  [REACT_APP]",
            "git": "🌿 [GIT_REPO]",
            "rust": "🦀 [RUST_CARGO]",
        }
        
        icon = icons.get(stack.lower(), f"◈ [{stack.upper()}]")
        print(f"\n  {cyan}◈ INITIALIZING TECH STACK: {bold}{icon}{reset}")
        
        # Atmospheric loading bar
        bar_width = 30
        for i in range(bar_width + 1):
            time.sleep(0.02)
            pct = i / bar_width
            filled = int(pct * 20)
            bar = "▰" * filled + "▱" * (20 - filled)
            sys.stdout.write(f"\r    {dim}syncing dependencies... {bar} {pct:.0%}{reset}")
            sys.stdout.flush()
        print(f"\n    {green}STABILIZED: {stack.upper()} ENVIRONMENT READY{reset}\n")

    def _show_context_pulse(self) -> None:
        """Visual effect for context layer injection."""
        import random
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        layers = ["IDENTITY", "SAFETY", "PROJECT", "MEMORY", "USER"]
        print(f"  {dim}INITIALIZING NEURAL LAYERS: {reset}", end="", flush=True)
        for layer in layers:
            time.sleep(0.04)
            sys.stdout.write(f"{cyan}◈{reset}")
            sys.stdout.flush()
        print(f" {dim}STABLE{reset}")

    def _show_neural_branching(self, spawned_agents) -> None:
        """Visual effect for auto-spawning agents."""
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        agent_names = [a.name for a in spawned_agents]
        print(f"  {cyan}◈ NEURAL BRANCHING DETECTED{reset}")
        for name in agent_names:
            print(f"    {dim}╰ spawning specialist:{reset} {cyan}{name}{reset}")

    def _show_kinetic_stream(self, path: str) -> None:
        """Visual effect for data streaming into a file."""
        import random
        green = "\033[32m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        filename = os.path.basename(path)
        print(f"  {dim}STREAMING DATA TO {reset}{green}{filename}{reset} {dim}...", end="", flush=True)
        
        # Kinetic particle stream
        particles = ["·", "•", "◦", "◙", "▫"]
        for _ in range(12):
            p = random.choice(particles)
            sys.stdout.write(f"{green}{p}{reset}")
            sys.stdout.flush()
            time.sleep(0.03)
        print(f" {dim}SYNCED{reset}")

    async def _run_refiners_fire(self, path: str | None) -> tuple[bool, str | None]:
        """Perform a mandatory integrity check on modified code (The Refiner's Fire)."""
        if not path or not os.path.exists(path):
            return True, None
            
        red = "\033[31m"
        green = "\033[32m"
        reset = "\033[0m"
        
        # 1. Syntax Check (The first test of fire)
        if path.endswith(".py"):
            try:
                import ast
                with open(path, "r", encoding="utf-8") as f:
                    ast.parse(f.read())
            except SyntaxError as e:
                return False, f"Syntax Error: {e.msg} (line {e.lineno})"
            except Exception as e:
                return False, str(e)
        
        # 1. Syntax Check (The first test of fire)
        if path.endswith(".py"):
            try:
                import ast
                with open(path, "r", encoding="utf-8") as f:
                    ast.parse(f.read())
            except SyntaxError as e:
                return False, f"Syntax Error: {e.msg} (line {e.lineno})"
            except Exception as e:
                return False, str(e)
        
        elif path.endswith(".json"):
            # 2. JSON Validation
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception as e:
                return False, f"Invalid JSON: {str(e)}"

        elif path.endswith((".yaml", ".yml")):
            # 3. YAML Validation
            try:
                import yaml
                with open(path, "r", encoding="utf-8") as f:
                    yaml.safe_load(f)
            except Exception as e:
                return False, f"Invalid YAML: {str(e)}"

        print(f" {green}STOOD THE FIRE{reset}")
        return True, None
        return True, None

    async def _handle_tool_failure(self, tool_name: str, arguments: dict, error: str) -> str:
        """Perform automatic diagnostics and recovery hints for tool failures."""
        import os
        hint = f"Error: {error}"
        
        # 1. Edit Tool Context Mismatch
        if tool_name == "edit" and "context mismatch" in error.lower():
            path = arguments.get("path")
            old_string = arguments.get("old_string")
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Check if old_string exists without context
                if old_string and old_string in content:
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if old_string in line:
                            context_block = "\n".join(lines[max(0, i-2):min(len(lines), i+3)])
                            hint += f"\n\n[RECOVERY HINT] 'old_string' was found at line {i+1}, but context mismatch occurred. Here is the actual context in the file:\n{context_block}"
                            break
                else:
                    hint += f"\n\n[RECOVERY HINT] 'old_string' was NOT found in the file at all. Please use the 'read' tool to verify the current file content."

        # 2. Bash Tool Command Not Found
        elif tool_name == "bash" and "not found" in error.lower():
            hint += f"\n\n[RECOVERY HINT] The command was not found. If this is a new tool, you might need to install it via 'apt install' or 'pip install'. In Termux, try 'pkg install'."

        # 3. File Not Found
        elif "file not found" in error.lower() or "no such file" in error.lower():
            hint += f"\n\n[RECOVERY HINT] Verify the path exists using 'list' or 'glob'. Paths should usually be relative to the project root."

        return hint

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
  /spawn <role>    Spawn a team agent (coder, reviewer, tester, researcher)
  /plan, /p        Enter plan mode for a task
  /build           Execute approved plan steps
  /safety <mode>   Set safety mode (user_review, read_only, strict, auto_git, sensitive, sandbox, unrestricted)
  /doctor          Run system diagnostics
  /sync status     Sync status / push / pull
  /learn stats     Learning system stats
  /help            Show this help
""")
            return True

        elif cmd == "safety":
            from ..safety import SafetyMode
            if not args:
                current = self.safety.get_mode().name
                print(f"Current safety mode: \033[96m{current}\033[0m")
                print("Available modes: user_review, read_only, strict, auto_git, sensitive, sandbox, unrestricted")
                return True
            
            try:
                mode_map = {m.name.lower(): m for m in SafetyMode}
                mode_map.update({m.value.lower(): m for m in SafetyMode})
                
                if args.lower() in mode_map:
                    new_mode = mode_map[args.lower()]
                    self.safety.set_mode(new_mode)
                    print(f"Safety mode updated to: \033[92m{new_mode.name}\033[0m")
                else:
                    print(f"Invalid mode: {args}")
            except Exception as e:
                print(f"Error updating safety mode: {e}")
            return True

        elif cmd == "reflect":
            print(f"\n\033[36m◈ INITIATING SESSION REFLECTION\033[0m")
            stats = self.learning.get_session_stats(self.session.id)
            failures = stats.get("failures", [])
            successes = stats.get("tool_usage", {})
            
            print(f"  \033[90mTotal Cycles:\033[0m {sum(successes.values())}")
            print(f"  \033[90mAnomalies Detected:\033[0m {len(failures)}")
            
            if failures:
                print(f"\n  \033[31mCritical Failure Nodes:\033[0m")
                for f in failures[-3:]:
                    print(f"    - {f['tool_name']}: {f['error'][:60]}...")
            
            print(f"\n\033[36m  ◈ LOGIC OPTIMIZATION: NOMINAL\033[0m\n")
            return True

        elif cmd == "clear":
            self.messages = []
            print("Conversation cleared.")
            return True

        elif cmd == "history":
            for i, msg in enumerate(self.messages[-10:]):
                role = msg.role.upper()
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                print(f"{i+1}. [{role}] {content}")
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
            print(f"Tools used: {', '.join(self.session.tools_used) if self.session.tools_used else 'none'}")
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
                    print(f"Invalid role: {role_name}. Valid: {', '.join(r.value for r in AgentRole)}")
            else:
                print("Usage: /spawn <role> [task]")
            return True

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
            print(f"\nAgent Statistics:")
            print(f"  Turn count: {self.session.id[:8]}")
            print(f"  Messages: {len(self.messages)}")
            print(f"  Tool calls: {self._tool_call_count}")
            print(f"  Active agents: {len(self.team.list_agents()) if self.team else 0}")
            return True

        elif cmd == "retry":
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
            pm = get_plugin_manager()
            parts = args.split(maxsplit=1) if args else []
            subcmd = parts[0] if parts else "list"
            subargs = parts[1] if len(parts) > 1 else ""
            
            if subcmd == "list":
                plugins = pm.list_all()
                if not plugins:
                    print("No plugins loaded.")
                for p in plugins:
                    status = "✓ enabled" if pm.is_enabled(p.metadata.name) else "✗ disabled"
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
            print(f"  Config: /root/.nexus/config.json exists")
            print(f"  Providers: {len(self.manager.configs)} configured")
            print(f"  Tools: {len(self.registry.list_all())} available")
            print(f"  Termux: available")
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
                        print(f"[!] Conflicts: {', '.join(result['conflicts'])}")
                else:
                    print(f"✗ Pull failed: {result.get('error')}")
            elif sub == "connect":
                print("Use: nexus sync connect <github-gist|local|git> --token <token> --path <path>")
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
                for l in lessons:
                    rate = l.success_count / max(1, l.success_count + l.failure_count)
                    print(f"\n  [{l.lesson_id}] {l.title}")
                    print(f"    {l.summary[:80]}...")
                    print(f"    Success: {rate:.0%} | Triggers: {', '.join(l.trigger_conditions[:2])}")
            elif sub == "failures":
                import json
                failures = sorted(self.learning.failures_dir.glob("*.json"),
                                 key=lambda f: f.stat().st_mtime, reverse=True)[:5]
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
                    print(f"✓ Approved: {parts[1]}. Use /improve apply {parts[1]} to apply.")
                else:
                    print(f"Improvement not found: {parts[1]}")
            elif sub == "apply" and len(parts) > 1:
                result = self.improver.apply(parts[1])
                if result.get("success"):
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
                for rid, rule in list(self.safety.rules.items())[:10]:
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
        
        try:
            plan = await self._plan_mode.generate_plan(self.manager, self.messages)
            print(self._plan_mode.format_for_display())
            
            # Wait for user input
            try:
                action = input("Action (A=approve all, S=skip low, Q=quit): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("Plan mode cancelled.")
                self._plan_active = False
                return
            
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
        
        approved = self._plan_mode.get_approved_steps()
        if not approved:
            print("No approved steps to execute.")
            return
        
        print(f"\nExecuting {len(approved)} approved steps...")
        tracker = ProgressTracker(len(approved), "Executing plan")
        
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
        
        tracker.finish()
        self._plan_active = False

    def _get_prompt(self) -> str:
        """Return the current REPL prompt."""
        return "\n  nexus> "

    async def run(self) -> None:
        """Run the REPL."""
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
                self.learning.record_failure(str(e), {"type": type(e).__name__}, {"session": self.session.id})
                print(f"{self.personality.failure()} {e}")

        self._save_history()
        self.memory.save_session(self.session)
        summary = self.learning.end_session(self.session.id, "completed")
        if summary.get("failures", 0) > 0:
            print(f"\n{self.personality.reflection_ask()}")


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
        """Show a 'Synaptic Pulse' loading indicator."""
        if not self._first_token_received:
            import random
            cyan = "\033[36m"
            dim = "\033[90m"
            reset = "\033[0m"
            
            # Atmospheric synaptic pulse symbols
            pulses = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            symbol = pulses[int(time.time() * 10) % len(pulses)]
            
            sys.stdout.write(f"\r  {cyan}{symbol}{reset} {dim}{message.upper()}{reset}")
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
        cyan = "\033[36m"
        reset = "\033[0m"

        if step.state == ThinkingState.ERROR:
            # Glitch Alert Effect
            red = "\033[31m"
            dim = "\033[90m"
            reset = "\033[0m"
            glitch = "⚠ SYSTEM_ANOMALY ⚠"
            print(f"  {red}{glitch}{reset}")
            print(f"  {dim}╰ Failure Node:{reset} {step.detail or 'Execution failed'}")
        else:
            duration = f"{dim}[{step.duration_ms:.0f}ms]{reset}" if step.duration_ms else ""
            
            # Special Box for Shell/Git commands
            if step.tool_name in ("bash", "git"):
                self._draw_shell_box(step.tool_name, step.tool_result, term_width)
            
            # Diff Box for Edits
            elif step.tool_name == "edit" and "applied successfully" in step.tool_result.lower():
                self._draw_diff_box(step.tool_args, term_width)
            
            # Data Harvest effect for Web tools
            elif step.tool_name in ("web_fetch", "web_search", "codesearch"):
                cyan = "\033[36m"
                print(f"  {cyan}╰ DATA HARVEST COMPLETE{reset} {duration}")
                if step.tool_result:
                    self._draw_harvest_grid(step.tool_result, term_width)
            
            # Scrubbing effect for Read
            elif step.tool_name == "read" and step.tool_result:
                cyan = "\033[36m"
                dim = "\033[90m"
                print(f"  {cyan}╰ FILE_SCRUB COMPLETE{reset} {duration}")
                content = step.tool_result.strip()
                lines = content.split("\n")
                print(f"    {dim}processed {len(lines)} lines from segment{reset}")
                # Show first 2 lines
                for line in lines[:2]:
                    print(f"    {dim}│{reset} {line[:term_width-10]}")
                if len(lines) > 2:
                    print(f"    {dim}╰ ... (+{len(lines)-2} more lines){reset}")

            else:
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

    def _draw_shell_box(self, tool_name: str, content: str, term_width: int) -> None:
        """Draw a dedicated sci-fi console box for shell output."""
        if not content:
            return

        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        # Determine box width (capped at 100 or term_width - 4)
        box_width = min(100, term_width - 8)
        header = f" {tool_name.upper()} CONSOLE "
        padding = (box_width - len(header)) // 2
        
        top_border = f"  {cyan}╔" + "═" * padding + header + "═" * (box_width - padding - len(header)) + "╗" + reset
        bottom_border = f"  {cyan}╚" + "═" * box_width + "╝" + reset
        
        print(top_border)
        
        lines = content.strip().split("\n")
        max_lines = 15 # Don't overwhelm the screen
        
        for i, line in enumerate(lines):
            if i >= max_lines:
                print(f"  {cyan}║{reset}  {dim}... (+{len(lines) - max_lines} more lines){reset}" + " " * (box_width - 25) + f"{cyan}║{reset}")
                break
            
            # Truncate line if it's too long for the box
            display_line = line[:box_width-4]
            # Pad the line to keep the right border aligned
            padding_needed = box_width - len(display_line) - 2
            print(f"  {cyan}║{reset}  {display_line}" + " " * padding_needed + f"{cyan}║{reset}")
            
        print(bottom_border)

    def _draw_diff_box(self, tool_args: dict, term_width: int) -> None:
        """Draw a visual diff of the changes made."""
        path = tool_args.get("path", "file")
        old_text = tool_args.get("old_string", "")
        new_text = tool_args.get("new_string", "")
        
        green = "\033[32m"
        red = "\033[31m"
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        box_width = min(100, term_width - 8)
        print(f"  {cyan}╔" + "═" * ((box_width - 12) // 2) + " DIFF SOURCE " + "═" * (box_width - ((box_width - 12) // 2) - 13) + "╗")
        print(f"  {cyan}║{reset} {dim}File: {path}{reset}" + " " * (box_width - len(path) - 8) + f"{cyan}║")
        print(f"  {cyan}╠" + "═" * box_width + "╣")
        
        # Show what was removed (Red)
        for line in old_text.splitlines():
            display_line = line[:box_width-6]
            padding = box_width - len(display_line) - 4
            print(f"  {cyan}║{reset} {red}-{reset} {display_line}" + " " * padding + f"{cyan}║")
            
        # Show what was added (Green)
        for line in new_text.splitlines():
            display_line = line[:box_width-6]
            padding = box_width - len(display_line) - 4
            print(f"  {cyan}║{reset} {green}+{reset} {display_line}" + " " * padding + f"{cyan}║")
            
        print(f"  {cyan}╚" + "═" * box_width + "╝" + reset)

    def _draw_harvest_grid(self, content: str, term_width: int) -> None:
        """Draw a 'Data Harvest' grid for web results."""
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        indent = "    "
        print(f"{indent}{dim}┌─ SHARED DATA STREAM ────────────────┐{reset}")
        
        # Take a snippet and format it as a grid
        text = content[:400].replace("\n", " ")
        words = text.split()
        
        current_line = f"{indent}{dim}│{reset} "
        line_len = 0
        max_width = min(60, term_width - 15)
        
        for word in words:
            if line_len + len(word) > max_width:
                print(current_line + " " * (max_width - line_len + 1) + f"{dim}│{reset}")
                current_line = f"{indent}{dim}│{reset} "
                line_len = 0
            
            current_line += word + " "
            line_len += len(word) + 1
            
        if line_len > 0:
            print(current_line + " " * (max_width - line_len + 1) + f"{dim}│{reset}")
            
        print(f"{indent}{dim}└─────────────────────────────────────┘{reset}")

    def _show_complete(self, step) -> None:
        """Show step complete."""
        self._tool_call_count += 1

    def _show_task_complete(self, step) -> None:
        """Show task complete summary with Neural Activity styling."""
        elapsed = step.duration_ms / 1000.0 if step.duration_ms else 0
        tool_count = self._tool_call_count
        
        cyan = "\033[36m"
        dim = "\033[90m"
        reset = "\033[0m"
        
        print(f"\n  {cyan}◈ NEURAL ACTIVITY STABILIZED{reset}")
        print(f"    {dim}latency: {elapsed:.2f}s | cycles: {tool_count} | status: nominal{reset}\n")

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


