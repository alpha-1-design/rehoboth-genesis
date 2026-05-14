"""Agent orchestrator - the core loop connecting AI, tools, and memory."""

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agent.reflection import ReflectionEngine
from ..agents import AgentRole, MultiAgentTeam
from ..errors import NexusError
from ..memory import Memory
from ..orchestrator.decomposer import LLMAwareDecomposer
from ..orchestrator.executor import ExecutionEngine
from ..plugins import get_plugin_manager
from ..providers import Message, ProviderManager, ToolCall
from ..safety import get_safety_engine
from ..thinking import ThinkingState, get_thinking_engine
from ..tools import ToolRegistry, ToolResult
from ..utils import format_error


def estimate_tokens(text: str) -> int:
    """Estimate token count using a simple approximation (4 chars per token)."""
    if not text:
        return 0
    return len(re.findall(r'\w+', text)) + (len(text) // 4)


def prune_messages(
    messages: list[Message],
    max_tokens: int,
    prune_ratio: float = 0.8,
) -> list[Message]:
    """Prune messages when approaching token limit.

    Keeps recent messages and summarizes old ones.
    """
    if not messages:
        return messages

    current_tokens = sum(estimate_tokens(m.content or "") for m in messages)
    if current_tokens <= max_tokens:
        return messages

    system_messages = [m for m in messages if m.role == "system"]
    other_messages = [m for m in messages if m.role != "system"]

    while estimate_tokens("".join(m.content or "" for m in messages)) > max_tokens * prune_ratio and len(other_messages) > 2:
        msg_to_summarize = other_messages[0]
        summary = f"[Earlier: {msg_to_summarize.role} said {msg_to_summarize.content[:100]}...]"

        summary_msg = Message(
            role="system",
            content=summary,
        )
        system_messages.append(summary_msg)

        other_messages = other_messages[1:]

    return system_messages + other_messages


@dataclass
class AgentConfig:
    """Configuration for the agent orchestrator."""
    model: str | None = None
    provider_name: str | None = None
    max_turns: int = 50
    max_tool_calls: int = 100
    stream: bool = True
    verbose: bool = False
    reflection_enabled: bool = True
    reflection_max_retries: int = 3
    system_prompt: str | None = None
    max_context_tokens: int = 128000
    context_prune_ratio: float = 0.8


@dataclass
class Turn:
    """Represents a single turn in the conversation."""
    user_message: str
    assistant_message: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    reflection: str | None = None
    tokens_used: int = 0
    duration_ms: int = 0
    error: str | None = None
    pending_approval: dict[str, Any] | None = None


class AgentOrchestrator:
    """
    The core agent loop: receives user input, calls the AI provider with tool
    definitions, executes tools, injects results, and repeats until the AI
    produces a final response.

    Combines patterns from:
    - Claude Code: tool-call → execute → inject → repeat
    - OpenCode: compact agent for context reduction
    - nexus_v2: reflection loop on errors with retry
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        tool_registry: ToolRegistry,
        memory: Memory | None = None,
        config: AgentConfig | None = None,
    ):
        self.pm = provider_manager
        self.tools = tool_registry
        self.memory = memory
        self.decomposer = LLMAwareDecomposer()
        self.executor = ExecutionEngine(
            self.tools,
            self._execute_tool_callback,
            llm_callback=self._execute_llm_callback,
            provider_manager=self.pm
        )
        self.config = config or AgentConfig()
        self.reflection_engine = ReflectionEngine(Path("./.nexus/sessions"))

        # ... rest of init ...
        self._tool_call_count = 0
        self._messages: list[Message] = []
        self._history: list[Turn] = []
        self._thinking = get_thinking_engine()
        self._thinking_callback = None
        self._ui_callback: Callable[[str, Any], None] | None = None  # UI Bridge
        self._total_tokens = 0
        self._turn_count = 0
        self._tool_stats: dict[str, dict] = {}
        self._team: MultiAgentTeam | None = None

    async def _execute_tool_callback(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Bridge for ExecutionEngine to call tools."""
        tool = self.tools.get(name)
        if not tool:
            return ToolResult(success=False, content="", error=f"Tool {name} not found")
        return await tool.execute(**args)

    async def _execute_llm_callback(self, prompt: str, provider_name: str | None = None) -> str:
        """Bridge for ExecutionEngine to call LLM."""
        messages = [Message(role="user", content=prompt)]
        response = await self.pm.complete(messages, provider_name=provider_name)
        return response.content

    def set_ui_callback(self, callback: Callable[[str, Any], None]):
        """Set a callback to notify the UI of state changes."""
        self._ui_callback = callback

    def _notify_ui(self, event_type: str, data: Any):
        """Notify the UI of a state change."""
        if self._ui_callback:
            self._ui_callback(event_type, data)

    async def run_complex_task(self, goal: str):
        """Unified entry point for decomposing and executing complex tasks."""
        try:
            # 1. Decompose
            plan = await self.decomposer.decompose(goal)
            self._notify_ui("thinking", {"description": f"Decomposed into {len(plan.steps)} steps"})

            # 2. Execute steps
            results = []
            for step in plan.steps:
                self._notify_ui("thinking", {"description": f"Executing: {step.description}"})
                result = await self.executor.execute_step(step)
                results.append(result)

            self.reflection_engine.perform_reflection()
            return results
        except Exception as e:
            error_msg = format_error(e)
            self._notify_ui("error", error_msg)
            raise NexusError(str(e), user_friendly=error_msg)

    @property
    def team(self) -> MultiAgentTeam | None:
        return self._team

    def spawn_agent(self, role: AgentRole, name: str | None = None,
                    task: str | None = None, model: str | None = None):
        """Spawn an agent with the given role."""
        if self._team is None:
            self._team = self.init_team()
        return self._team.spawn(role, name=name, task=task, model=model)

    def get_team(self) -> MultiAgentTeam | None:
        """Get the current team."""
        return self._team

    def set_system_prompt(self, prompt: str) -> None:
        """Set or update the system prompt."""
        self._messages = [Message(role="system", content=prompt)]
        if self.config.system_prompt:
            self._messages[0] = Message(
                role="system",
                content=self.config.system_prompt + "\n\n" + prompt
            )

    async def run(self, user_input: str, stream_callback=None, thinking_callback=None) -> Turn:
        """Run a single interaction turn."""
        start = time.monotonic()
        turn = Turn(user_message=user_input)
        self._turn_count += 1

        if thinking_callback:
            self._thinking_callback = thinking_callback
            self._thinking.on_update(thinking_callback)

        self._thinking.clear()
        analyze_step = self._thinking.start_step(
            ThinkingState.ANALYZING,
            "Analyzing task...",
            detail=f"Input: {user_input[:100]}..." if len(user_input) > 100 else f"Input: {user_input}"
        )

        self._messages.append(Message(role="user", content=user_input))

        self._thinking.update_step(analyze_step, confidence=0.85)
        self._thinking.finish_step(analyze_step, result="Analyzed user input")

        planning_step = self._thinking.start_step(
            ThinkingState.PLANNING,
            "Planning tool sequence...",
            detail=f"Available tools: {len(self.tools.list_all())}"
        )
        self._thinking.update_step(planning_step, confidence=0.75)
        self._thinking.finish_step(planning_step, result="Tool sequence planned")

        try:
            result = await self._run_loop(stream_callback)
            turn.assistant_message = result["message"]
            turn.tool_calls = result.get("tool_calls", [])
            if result.get("pending_approval"):
                turn.pending_approval = result["pending_approval"]

            review_step = self._thinking.start_step(
                ThinkingState.REVIEWING,
                "Generating response...",
                detail=f"Response length: {len(result['message'])} chars"
            )
            self._thinking.update_step(review_step, confidence=0.90)
            self._thinking.finish_step(review_step, result=result["message"][:200])

            complete_step = self._thinking.start_step(
                ThinkingState.COMPLETE,
                "Task complete",
                detail=f"Completed in {len(result.get('tool_calls', []))} tool calls"
            )
            self._thinking.finish_step(complete_step, result=result["message"][:200])
            turn.tokens_used = self._total_tokens
        except Exception as e:
            turn.error = str(e)
            turn.assistant_message = f"Error: {e}"

        turn.duration_ms = int((time.monotonic() - start) * 1000)
        self._history.append(turn)
        return turn

    async def _run_loop(self, stream_callback=None) -> dict[str, Any]:
        """The main agent loop."""
        tool_defs = self.tools.to_openai_format()
        provider_name = self.config.provider_name
        accumulated = ""
        tool_calls_accumulated: list[ToolCall] = []

        while self._turn_count <= self.config.max_turns:
            if self._tool_call_count >= self.config.max_tool_calls:
                raise RuntimeError(f"Max tool calls ({self.config.max_tool_calls}) reached")

            if self.config.max_context_tokens > 0:
                self._messages = prune_messages(
                    self._messages,
                    self.config.max_context_tokens,
                    self.config.context_prune_ratio,
                )

            if self.config.stream and stream_callback and not tool_defs:
                tool_calls_accumulated = []
                accumulated = ""

                async for chunk in self.pm.stream(
                    messages=self._messages,
                    tools=tool_defs,
                    provider_name=provider_name,
                ):
                    if chunk.tool_call:
                        tool_calls_accumulated.append(chunk.tool_call)
                    elif chunk.content:
                        accumulated += chunk.content
                        stream_callback(chunk.content)
                    if chunk.done:
                        break

                response_content = accumulated
                tool_calls = tool_calls_accumulated
            else:
                response = await self.pm.complete(
                    messages=self._messages,
                    tools=tool_defs,
                    provider_name=provider_name,
                )
                response_content = response.content or ""
                tool_calls = response.tool_calls

            if not tool_calls:
                self._messages.append(Message(role="assistant", content=response_content))
                return {"message": response_content, "tool_calls": []}

            for tc in tool_calls:
                self._tool_call_count += 1
                tool_result = await self._execute_tool(tc, turn=Turn(user_message=""))

                # --- INTERACTIVE APPROVAL FLOW ---
                # If the tool returns a result requiring human approval (like a diff)
                if isinstance(tool_result, ToolResult) and tool_result.metadata and tool_result.metadata.get("action") == "require_approval":
                    # This is where we pause the loop and wait for user input.
                    # In the TUI, this will trigger a modal/prompt.
                    # For the orchestrator, we return a special signal to the TUI.
                    return {
                        "message": f"I have a proposed change for {tool_result.metadata['path']}. Please review the diff.",
                        "tool_calls": [],
                        "pending_approval": {
                            "tool_name": tc.name,
                            "args": tc.arguments,
                            "result": tool_result
                        }
                    }

                tool_msg = f"Tool result for {tc.name}: {tool_result.content}"
                if tool_result.error:
                    tool_msg += f"\nError: {tool_result.error}"
                self._messages.append(Message(role="user", content=tool_msg))

            if self.config.verbose:
                print(f"\n[nexus] Turn {self._turn_count}, tool calls: {len(tool_calls)}")

        raise RuntimeError(f"Max turns ({self.config.max_turns}) reached without final response")

    async def _execute_tool(self, tool_call, turn: Turn, depth: int = 0) -> ToolResult:
        """Execute a tool call with safety checks and reflection on failure."""
        name = tool_call.name
        args = tool_call.arguments if isinstance(tool_call.arguments, dict) else {}

        exec_step = self._thinking.start_step(
            ThinkingState.EXECUTING,
            f"Calling tool: {name}",
            tool_name=name,
            tool_args=args
        )

        # 1. Safety Check
        safety = get_safety_engine()
        context = {"tool": name, "args": args}
        for path_key in ("path", "filePath", "file_path"):
            if path_key in args:
                context["path"] = args[path_key]
                break
        if "command" in args:
            context["command"] = args["command"]

        violations = safety.check(context)
        proceed, reason = safety.should_proceed(violations)
        if not proceed:
            self._thinking.finish_step(exec_step, error=f"Safety Block: {reason}")
            return ToolResult(success=False, content=f"Blocked by Safety: {reason}", error=reason)

        if name == "Read":
            for path_key in ("path", "filePath", "file_path"):
                if path_key in args:
                    safety.mark_file_read(args[path_key])
                    break

        plugin_manager = get_plugin_manager()
        ctx = {"orchestrator": self, "turn": turn}

        for attempt in range(self.config.reflection_max_retries):
            tool = self.tools.get(name)
            if not tool:
                self._thinking.finish_step(exec_step, error=f"Unknown tool: {name}")
                return ToolResult(success=False, content="", error=f"Unknown tool: {name}")

            args = plugin_manager.call_tool_hooks(name, args, ctx)

            result = await tool.execute(**args)
            result = plugin_manager.call_result_hooks(name, result, ctx)

            # 2. The Refiner's Fire (Integrity Validation)
            if result.success and name in ("write", "edit"):
                validation_passed, validation_error = await self._run_refiners_fire(args.get("path"))
                if not validation_passed:
                    result.success = False
                    result.content = f"[REJECTED BY FIRE] The work was performed, but it failed the integrity check:\\n{validation_error}\\n\\n[RECOVERY] I have detected an impurity in the logic. You must fix this error before proceeding."

            if result.success or depth > 0:
                self._thinking.finish_step(exec_step, result=result.content[:200] if result.content else "")
                return result

            # 3. Deterministic Recovery Hints
            if not result.success:
                result.content = await self._handle_tool_failure(name, args, result.error or result.content)

            if self.config.verbose:
                print(f"\\n[nexus] Tool '{name}' failed (attempt {attempt+1}): {result.error}")

            if attempt < self.config.reflection_max_retries - 1 and self.config.reflection_enabled:
                reflection = await self._reflect_on_failure(name, args, result.error or "")
                if reflection.get("adjusted_args"):
                    args = reflection["adjusted_args"]
                    if self.config.verbose:
                        print(f"[nexus] Adjusting args: {args}")

        self._thinking.finish_step(exec_step, error=result.error or "Tool failed")
        return result

    async def _run_refiners_fire(self, path: str | None) -> tuple[bool, str | None]:
        """Perform a mandatory integrity check on modified code."""
        if not path or not os.path.exists(path):
            return True, None
        try:
            if path.endswith(".py"):
                import ast
                with open(path, encoding="utf-8") as f:
                    ast.parse(f.read())
            elif path.endswith(".json"):
                import json
                with open(path, encoding="utf-8") as f:
                    json.load(f)
            elif path.endswith((".yaml", ".yml")):
                import yaml
                with open(path, encoding="utf-8") as f:
                    yaml.safe_load(f)
            return True, None
        except Exception as e:
            return False, str(e)

    async def _handle_tool_failure(self, tool_name: str, args: dict, error: str) -> str:
        """Provide deterministic recovery hints for tool failures."""
        import os
        user_friendly_error = format_error(error)
        hint = f"Tool '{tool_name}' failed: {user_friendly_error}"
        if tool_name == "edit" and "context mismatch" in error.lower():
            path = args.get("path")
            old_string = args.get("old_string")
            if path and os.path.exists(path):
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if old_string and old_string in content:
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if old_string in line:
                            context_block = "\n".join(lines[max(0, i-2):min(len(lines), i+3)])
                            hint += f"\n\n[RECOVERY HINT] 'old_string' was found at line {i+1}, but context mismatch occurred. Here is the actual context in the file:\n{context_block}"
                            break
                else:
                    hint += "\n\n[RECOVERY HINT] 'old_string' was NOT found in the file at all. Please use the 'read' tool to verify the current file content."
        elif tool_name == "bash" and "not found" in error.lower():
            hint += "\n\n[RECOVERY HINT] The command was not found. If this is a new tool, you might need to install it via 'apt install' or 'pip install'. In Termux, try 'pkg install'."
        elif "file not found" in error.lower() or "no such file" in error.lower():
            hint += "\n\n[RECOVERY HINT] Verify the path exists using 'list' or 'glob'. Paths should usually be relative to the project root."
        return hint

    async def _reflect_on_failure(
        self, tool_name: str, args: dict, error: str
    ) -> dict[str, Any]:
        """Ask the AI to suggest fixes for a failed tool call."""
        prompt = (
            f"Tool '{tool_name}' failed with error: {error}\n"
            f"Original args: {json.dumps(args)}\n"
            "Suggest adjusted args (JSON only, or {{}} if no fix possible)."
        )

        try:
            response = await self.pm.complete(
                messages=[Message(role="user", content=prompt)],
                provider_name=self.config.provider_name,
            )
            content = response.content or "{}"
            try:
                adjusted = json.loads(content)
                return {"adjusted_args": adjusted} if isinstance(adjusted, dict) else {}
            except json.JSONDecodeError:
                return {}
        except Exception:
            return {}

    def get_history(self) -> list[Turn]:
        """Return conversation history."""
        return self._history

    def compact_history(self, target_turns: int = 10) -> None:
        """
        Compact conversation history to reduce context size.
        Keeps first and last N turns, summarizes middle turns.
        """
        if len(self._messages) <= target_turns * 2:
            return

        system = [m for m in self._messages if m.role == "system"]
        non_system = [m for m in self._messages if m.role != "system"]
        keep = non_system[:2] + non_system[-target_turns:]

        summary = Message(
            role="system",
            content=f"[Previous conversation summarized — {len(non_system)} messages condensed]"
        )
        self._messages = system + [summary] + keep

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    def reset(self) -> None:
        """Reset conversation state but keep config."""
        system = [m for m in self._messages if m.role == "system"]
        self._messages = system
        self._history = []
        self._turn_count = 0
        self._tool_call_count = 0
