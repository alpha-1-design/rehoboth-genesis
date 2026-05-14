"""Structured thinking display for Nexus agent.

Shows step-by-step reasoning, tool decisions, confidence levels,
and progress — fully transparent agent cognition.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ThinkingState(Enum):
    IDLE = "idle"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETE = "complete"
    ERROR = "error"

@dataclass
class ThinkingStep:
    step_id: str
    state: ThinkingState
    title: str
    detail: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    sub_steps: list["ThinkingStep"] = field(default_factory=list)
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self.finished_at is None

class ThinkingEngine:
    """Captures and formats agent thinking for display."""

    def __init__(self):
        self._steps: list[ThinkingStep] = []
        self._current: ThinkingStep | None = None
        self._callbacks: list[callable] = []
        self._step_counter = 0

    def start_step(self, state: ThinkingState, title: str, detail: str = "",
                   tool_name: str | None = None, tool_args: dict | None = None) -> str:
        """Start a new thinking step. Returns step_id."""
        self._step_counter += 1
        step_id = f"step_{self._step_counter}"
        step = ThinkingStep(
            step_id=step_id,
            state=state,
            title=title,
            detail=detail,
            tool_name=tool_name,
            tool_args=tool_args or {},
        )
        self._steps.append(step)
        self._current = step
        self._notify(("start", step))
        return step_id

    def update_step(self, step_id: str, **kwargs):
        """Update a thinking step's fields."""
        step = next((s for s in self._steps if s.step_id == step_id), None)
        if step:
            for k, v in kwargs.items():
                if hasattr(step, k):
                    setattr(step, k, v)
            self._notify(("update", step))

    def finish_step(self, step_id: str, result: str | None = None, error: str | None = None):
        """Mark a thinking step as complete."""
        step = next((s for s in self._steps if s.step_id == step_id), None)
        if step:
            step.finished_at = datetime.now()
            step.duration_ms = (step.finished_at - step.started_at).total_seconds() * 1000
            step.tool_result = result
            if error:
                step.state = ThinkingState.ERROR
                step.detail = error
            self._notify(("finish", step))
            if self._current and self._current.step_id == step_id:
                self._current = None

    def get_active_steps(self) -> list[ThinkingStep]:
        """Get all steps that are currently running."""
        return [s for s in self._steps if s.is_running]

    def get_history(self, limit: int = 50) -> list[ThinkingStep]:
        """Get recent thinking history."""
        return self._steps[-limit:]

    def format_for_display(self, step: ThinkingStep) -> str:
        """Format a thinking step for terminal/TUI display."""
        state_icon = {
            ThinkingState.IDLE: "○",
            ThinkingState.ANALYZING: "◐",
            ThinkingState.PLANNING: "▣",
            ThinkingState.EXECUTING: "▸",
            ThinkingState.REVIEWING: "◉",
            ThinkingState.COMPLETE: "✓",
            ThinkingState.ERROR: "✗",
        }.get(step.state, "?")

        lines = [f"[{step.state.value.upper()}] {state_icon} {step.title}"]
        if step.detail:
            lines.append(f"    {step.detail}")
        if step.confidence > 0:
            lines.append(f"    Confidence: {step.confidence:.0%}")
        if step.tool_name:
            lines.append(f"    Tool: {step.tool_name}")
        if step.finished_at:
            lines.append(f"    Duration: {step.duration_ms:.0f}ms")
        elif step.is_running and step.started_at:
            elapsed = (datetime.now() - step.started_at).total_seconds() * 1000
            lines.append(f"    Elapsed: {elapsed:.0f}ms")
        if step.tool_result:
            result_preview = step.tool_result[:200].replace("\n", " ")
            lines.append(f"    Result: {result_preview}...")
        return "\n".join(lines)

    def on_update(self, callback: callable):
        """Register a callback for thinking updates."""
        self._callbacks.append(callback)

    def _notify(self, event):
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def clear(self):
        """Clear all thinking history."""
        self._steps.clear()
        self._current = None
        self._step_counter = 0


# Global singleton
_thinking_engine: ThinkingEngine | None = None

def get_thinking_engine() -> ThinkingEngine:
    global _thinking_engine
    if _thinking_engine is None:
        _thinking_engine = ThinkingEngine()
    return _thinking_engine
