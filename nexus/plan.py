"""Plan Mode for Nexus — structured task planning with user approval.

Plan Mode is triggered:
- Automatically when task complexity exceeds threshold
- Manually via /plan command

In Plan Mode, the agent breaks down tasks into steps,
shows confidence/progress/effort for each, and waits for user approval
before executing.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepPriority(Enum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


class StepStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SKIPPED = "skipped"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class PlanStep:
    step_id: int
    description: str
    priority: StepPriority = StepPriority.MED
    confidence: float = 0.8
    effort_minutes: float = 1.0
    status: StepStatus = StepStatus.PENDING
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "priority": self.priority.value,
            "confidence": self.confidence,
            "effort_minutes": self.effort_minutes,
            "status": self.status.value,
            "tool_name": self.tool_name,
            "result": self.result,
        }


@dataclass
class Plan:
    task: str
    steps: list[PlanStep] = field(default_factory=list)
    confidence: float = 0.0
    estimated_minutes: float = 0.0
    created_at: str = ""

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def approved_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.APPROVED)

    @property
    def done_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.DONE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "confidence": self.confidence,
            "estimated_minutes": self.estimated_minutes,
            "steps": [s.to_dict() for s in self.steps],
        }


class PlanMode:
    """Manages Plan Mode lifecycle."""

    def __init__(self, task: str, orchestrator=None):
        self.task = task
        self.orchestrator = orchestrator
        self.plan: Plan | None = None
        self._is_active = False
        self._approval_mode = "all"

    def activate(self) -> None:
        self._is_active = True

    def deactivate(self) -> None:
        self._is_active = False

    @property
    def is_active(self) -> bool:
        return self._is_active

    async def generate_plan(self, provider_manager, messages: list) -> Plan:
        """Generate a structured plan using the AI provider."""
        from datetime import datetime

        planning_msg = f"""You are a planning assistant. Break down this task into clear, executable steps.

Task: {self.task}

Respond ONLY with valid JSON in this format (no markdown, no explanation):
{{
  "task_summary": "brief summary",
  "confidence": 0.87,
  "estimated_minutes": 8,
  "steps": [
    {{
      "description": "step description",
      "priority": "HIGH|MED|LOW",
      "confidence": 0.9,
      "effort_minutes": 2,
      "tool_name": "ToolName or null",
      "tool_args": {{}} or null
    }}
  ]
}}

Rules:
- Use only HIGH/MED/LOW for priority
- Each step should be independently executable
- Aim for 3-8 steps total
- Include a review/self-check step for complex tasks
"""

        response = await provider_manager.complete(
            messages=[{"role": "user", "content": planning_msg}],
            system="You are a planning assistant.",
        )

        content = response.content if hasattr(response, "content") else str(response)

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = {"task_summary": self.task, "confidence": 0.5, "estimated_minutes": 5, "steps": []}

        plan = Plan(
            task=data.get("task_summary", self.task),
            confidence=data.get("confidence", 0.5),
            estimated_minutes=data.get("estimated_minutes", 5),
            created_at=datetime.now().isoformat(),
        )

        for i, step_data in enumerate(data.get("steps", []), 1):
            plan.steps.append(
                PlanStep(
                    step_id=i,
                    description=step_data.get("description", ""),
                    priority=StepPriority(step_data.get("priority", "MED")),
                    confidence=step_data.get("confidence", 0.8),
                    effort_minutes=step_data.get("effort_minutes", 1),
                    tool_name=step_data.get("tool_name"),
                    tool_args=step_data.get("tool_args") or {},
                )
            )

        self.plan = plan
        return plan

    def format_for_display(self) -> str:
        """Format the plan as a readable text block for terminal display."""
        if not self.plan:
            return "No plan generated yet."

        lines = []
        lines.append(f"\n{'=' * 60}")
        lines.append(f"PLAN MODE — {self.plan.task}")
        lines.append(f"{'=' * 60}")
        lines.append(f"Confidence: {self.plan.confidence:.0%}  |  Est: ~{self.plan.estimated_minutes:.0f}min  |  Steps: {self.plan.total_steps}")
        lines.append(f"{'─' * 60}")

        for step in self.plan.steps:
            status_icon = {
                StepStatus.PENDING: "[ ]",
                StepStatus.APPROVED: "[●]",
                StepStatus.SKIPPED: "[→]",
                StepStatus.RUNNING: "[◐]",
                StepStatus.DONE: "[✓]",
                StepStatus.FAILED: "[✗]",
            }.get(step.status, "[?]")

            priority_color = {
                StepPriority.HIGH: "🔴 HIGH",
                StepPriority.MED: "🟡 MED",
                StepPriority.LOW: "🟢 LOW",
            }.get(step.priority, "")

            line = f"  {status_icon} {step.step_id}. {step.description}"
            lines.append(line)

            sub = f"       {priority_color}  confidence: {step.confidence:.0%}  est: ~{step.effort_minutes:.0f}min"
            if step.tool_name:
                sub += f"  tool: {step.tool_name}"
            lines.append(sub)

            if step.result:
                lines.append(f"       → {step.result[:80]}")
            if step.error:
                lines.append(f"       ✗ {step.error}")

        lines.append(f"{'─' * 60}")
        lines.append("[A]pprove all  [S]kip low-priority  [N]o auto-approve  [Q]uit plan mode  [E]dit step")
        lines.append("")
        return "\n".join(lines)

    def approve_all(self) -> None:
        """Approve all steps."""
        if self.plan:
            for step in self.plan.steps:
                if step.status == StepStatus.PENDING:
                    step.status = StepStatus.APPROVED

    def skip_low_priority(self) -> None:
        """Skip all LOW priority steps."""
        if self.plan:
            for step in self.plan.steps:
                if step.priority == StepPriority.LOW and step.status == StepStatus.PENDING:
                    step.status = StepStatus.SKIPPED

    def approve_step(self, step_id: int) -> bool:
        """Approve a specific step."""
        if self.plan:
            step = next((s for s in self.plan.steps if s.step_id == step_id), None)
            if step:
                step.status = StepStatus.APPROVED
                return True
        return False

    def skip_step(self, step_id: int) -> bool:
        """Skip a specific step."""
        if self.plan:
            step = next((s for s in self.plan.steps if s.step_id == step_id), None)
            if step:
                step.status = StepStatus.SKIPPED
                return True
        return False

    def get_approved_steps(self) -> list[PlanStep]:
        """Get all approved steps in order."""
        if self.plan:
            return [s for s in self.plan.steps if s.status == StepStatus.APPROVED]
        return []

    def save(self, path: str | None = None) -> str:
        """Save plan to file."""
        if not self.plan:
            return "No plan to save."
        from pathlib import Path

        save_dir = Path.home() / ".nexus" / "plans"
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = path or f"plan_{self.task[:30].replace(' ', '_')}.json"
        filepath = save_dir / filename
        with open(filepath, "w") as f:
            json.dump(self.plan.to_dict(), f, indent=2)
        return str(filepath)


_plan_mode: PlanMode | None = None


def get_plan_mode() -> PlanMode | None:
    return _plan_mode


def set_plan_mode(pm: PlanMode | None) -> None:
    global _plan_mode
    _plan_mode = pm


def should_trigger_plan_mode(task: str) -> bool:
    """Detect if a task is complex enough to warrant planning."""
    task_lower = task.lower()

    action_verbs = sum(
        1
        for w in ["build", "create", "implement", "design", "refactor", "migrate", "setup", "deploy", "test", "fix", "update", "add", "configure", "integrate"]
        if w in task_lower
    )

    file_mentions = len(re.findall(r"(?:src/|file|\.py|\.js|module|component)", task_lower))

    complexity_score = action_verbs * 2 + file_mentions

    return complexity_score >= 3 or any(
        w in task_lower for w in ["multiple", "entire", "full", "complete", "comprehensive", "architecture", "system", "restructure", "migrate"]
    )
