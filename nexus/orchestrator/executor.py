"""Execution Engine — executes task plans with dependency ordering.

This is the bridge between the Decomposer and the actual tool execution.
It takes a TaskPlan and executes steps in order, respecting dependencies.
"""

import asyncio
import time
from typing import Any, Callable, Coroutine

from ..tools import ToolResult
from ..utils import get_logger
from .decomposer import (
    ExecutionStep,
    StepStatus,
    StepType,
    TaskPlan,
)

logger = get_logger(__name__)


TASK_KEYWORDS = [
    "create", "write", "make file", "build", "generate",
    "fix", "bug", "error", "crash", "patch",
    "analyze", "audit", "review", "assess",
    "test", "run tests", "testing",
    "deploy", "release", "publish",
    "refactor", "rename", "move", "copy",
    "install", "setup", "configure",
    "debug", "troubleshoot",
]

NEEDS_TOOLS_KEYWORDS = [
    "write", "create file", "edit", "modify", "delete file",
    "run", "execute", "bash", "command",
    "read", "list files", "search", "grep", "find",
    "build", "compile", "test",
]


def is_structured_task(user_input: str) -> bool:
    """Detect if a task requires structured execution (not just chat)."""
    text = user_input.lower()
    
    for keyword in TASK_KEYWORDS:
        if keyword in text:
            return True
    
    for keyword in NEEDS_TOOLS_KEYWORDS:
        if keyword in text:
            return True
    
    return False


class ExecutionEngine:
    """Executes task plans with ordered, dependency-aware steps."""

    def __init__(
        self,
        registry: Any,
        tool_executor: Callable[..., Coroutine[Any, Any, ToolResult]],
        llm_callback: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        provider_manager: Any = None,
    ):
        self.registry = registry
        self.execute_tool = tool_executor
        self.llm_callback = llm_callback
        self.pm = provider_manager
        self._step_results: dict[str, Any] = {}
        self._multi_key_enabled = False
        self._consent_asked = False

    def is_heavy_task(self, plan: TaskPlan) -> bool:
        """Identify if a task plan is considered 'heavy'."""
        heavy_keywords = ["refactor", "audit", "test", "analyze codebase", "generate project"]
        if any(kw in plan.task.lower() for kw in heavy_keywords):
            return True
        return len(plan.steps) > 5

    async def _ask_multi_key_consent(self) -> bool:
        """Prompt user for multi-key parallel processing consent."""
        if self._consent_asked:
            return self._multi_key_enabled
        
        from ..providers import get_manager
        manager = get_manager()
        enabled = manager.get_enabled_providers()
        
        if len(enabled) < 2:
            return False

        print("\n  \033[34m╼\033[0m \033[36mnexus/orchestrator\033[0m \033[1mHeavy task detected.\033[0m")
        print(f"    Multiple API keys detected ({', '.join(enabled)}).")
        choice = input("    \033[1mActivate Parallel Neural Processing (Multi-Key)?\033[0m (y/N): ").strip().lower()
        
        self._consent_asked = True
        self._multi_key_enabled = choice in ('y', 'yes')
        
        if self._multi_key_enabled:
            print("    \033[32m✔\033[0m Multi-key orchestration engaged.")
        return self._multi_key_enabled

    async def execute_plan(
        self,
        plan: TaskPlan,
        progress_callback: Callable[[str, StepStatus, Any], None] | None = None,
    ) -> tuple[bool, str]:
        """Execute a task plan and return (success, summary)."""
        plan.start()
        
        if self.is_heavy_task(plan):
            await self._ask_multi_key_consent()
        
        completed: set[str] = set()
        results: dict[str, Any] = {}
        batches = plan.get_parallel_batches(completed, results)
        
        for batch_idx, batch in enumerate(batches):
            if self._multi_key_enabled and len(batch) > 1:
                # Parallel execution across multiple providers
                await self._execute_batch_parallel(batch, plan, progress_callback)
            else:
                for step in batch:
                    # Sequential or standard single-provider parallel (if supported by executor)
                    await self._execute_step_with_retries(step, plan, batch_idx, len(batches), progress_callback)
            
            # Update results for next batch
            for step in batch:
                if step.status == StepStatus.COMPLETED:
                    completed.add(step.id)
                    results[step.id] = step.result
                elif step.status == StepStatus.FAILED:
                    plan.fail(f"Step '{step.description}' failed")
                    return False, plan.format_summary()

        plan.finish()
        return True, plan.format_summary()

    async def _execute_batch_parallel(self, batch: list[ExecutionStep], plan: TaskPlan, progress_callback: Any):
        """Execute a batch of steps in parallel using multiple keys."""
        from ..providers import get_manager
        manager = get_manager()
        providers = manager.get_enabled_providers()
        
        # Distribute steps across providers
        tasks = []
        for i, step in enumerate(batch):
            prov = providers[i % len(providers)]
            step.status = StepStatus.RUNNING
            step.started_at = time.time()
            if progress_callback:
                progress_callback(f"{step.description} [\033[36m{prov}\033[0m]", StepStatus.RUNNING, "PARALLEL")
            
            # This is a simplification; actual tool execution might need to be wrapped differently
            # for different providers if they have different tool calling formats
            tasks.append(self._execute_step(step, plan, progress_callback, provider_name=prov))
            
        await asyncio.gather(*tasks)

    async def _execute_step_with_retries(self, step, plan, batch_idx, total_batches, progress_callback):
        step_num = batch_idx + 1
        status_text = f"{step_num}/{total_batches}"
        
        if progress_callback:
            progress_callback(step.description, StepStatus.RUNNING, status_text)
        
        success = await self._execute_step(step, plan, progress_callback)
        
        if not success and step.max_retries > 0:
            for retry in range(step.max_retries):
                step.retry_count = retry + 1
                if progress_callback:
                    progress_callback(f"{step.description} (retry {retry + 1})", StepStatus.RUNNING, status_text)
                success = await self._execute_step(step, plan, progress_callback)
                if success:
                    break
        
        if progress_callback:
            if success:
                progress_callback(step.description, StepStatus.COMPLETED, status_text)
            else:
                progress_callback(step.description, StepStatus.FAILED, status_text)
        return success

    async def _execute_step(
        self,
        step: ExecutionStep,
        plan: TaskPlan,
        progress_callback: Callable[[str, StepStatus, Any], None] | None = None,
        provider_name: str | None = None,
    ) -> bool:
        """Execute a single step."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        
        try:
            if step.step_type == StepType.PLANNING:
                result = await self._execute_llm_step(step, provider_name=provider_name)
            elif step.step_type == StepType.AGENT_TASK:
                result = await self._execute_llm_step(step, provider_name=provider_name)
            elif step.step_type == StepType.CUSTOM:
                result = await self._execute_llm_step(step, provider_name=provider_name)
            elif step.tool_name:
                result = await self._execute_tool_step(step)
            else:
                result = await self._execute_llm_step(step, provider_name=provider_name)
            
            step.completed_at = time.time()
            step.actual_duration_ms = step.duration_ms()
            self._step_results[step.id] = result
            
            if isinstance(result, ToolResult):
                if result.success:
                    step.status = StepStatus.COMPLETED
                    step.result = result.content
                    return True
                else:
                    step.status = StepStatus.FAILED
                    step.error = result.error
                    return False
            else:
                step.status = StepStatus.COMPLETED
                step.result = result
                return True
                
        except Exception as e:
            step.completed_at = time.time()
            step.status = StepStatus.FAILED
            step.error = str(e)
            logger.error(f"Step {step.id} failed: {e}")
            return False

    async def _execute_tool_step(self, step: ExecutionStep) -> ToolResult:
        """Execute a step that calls a tool directly."""
        tool = self.registry.get(step.tool_name)
        if not tool:
            return ToolResult(
                success=False,
                content="",
                error=f"Tool '{step.tool_name}' not found",
            )
        
        resolved_args = self._resolve_step_args(step)
        
        return await self.execute_tool(step.tool_name, resolved_args)

    async def _execute_llm_step(self, step: ExecutionStep, provider_name: str | None = None) -> str:
        """Execute a step that requires LLM reasoning."""
        if not self.llm_callback:
            return f"No LLM callback configured for step: {step.description}"

        context_parts = []
        for dep in step.dependencies:
            if dep.step_id in self._step_results:
                context_parts.append(f"Previous result: {self._step_results[dep.step_id]}")

        context = "\n".join(context_parts) if context_parts else "No previous results."

        prompt = f"""Task: {step.description}

    Previous context:
    {context}

    Execute this step and provide the result."""

        if provider_name:
            # If the callback supports provider_name (like in the updated orchestrator)
            try:
                return await self.llm_callback(prompt, provider_name=provider_name)
            except TypeError:
                return await self.llm_callback(prompt)

        return await self.llm_callback(prompt)
    def _resolve_step_args(self, step: ExecutionStep) -> dict[str, Any]:
        """Resolve step arguments, substituting dependency results."""
        resolved = step.args.copy()
        
        for key, value in resolved.items():
            if isinstance(value, str) and value.startswith("$"):
                dep_id = value[1:]
                if dep_id in self._step_results:
                    resolved[key] = self._step_results[dep_id]
        
        return resolved

    async def execute_from_llm_response(
        self,
        tool_calls: list[dict[str, Any]],
        progress_callback: Callable[[str, StepStatus, str], None] | None = None,
    ) -> list[ToolResult]:
        """Execute tool calls in dependency order if provided."""
        if not tool_calls:
            return []
        
        steps = self._tool_calls_to_steps(tool_calls)
        plan = TaskPlan(task="LLM response execution", goal="Execute LLM tool calls", steps=steps)
        
        batches = plan.get_parallel_batches(completed=set(), results={})
        results = []
        
        for batch in batches:
            batch_results = await asyncio.gather(
                *[self._execute_step(step, plan, progress_callback) for step in batch],
                return_exceptions=True,
            )
            results.extend(batch_results)
        
        return results

    def _tool_calls_to_steps(self, tool_calls: list[dict[str, Any]]) -> list[ExecutionStep]:
        """Convert LLM tool calls to execution steps."""
        steps = []
        for i, tc in enumerate(tool_calls):
            step = ExecutionStep(
                id=f"tool_{i + 1}",
                description=f"Call tool: {tc.get('name', 'unknown')}",
                step_type=StepType.CUSTOM,
                tool_name=tc.get("name"),
                args=tc.get("arguments", {}),
            )
            steps.append(step)
        return steps
