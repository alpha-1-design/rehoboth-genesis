"""Evolution State Machine for Nexus Recursive Self-Improvement.
Manages the lifecycle of a core code change from proposal to merge.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any


class EvolutionState(Enum):
    PROPOSAL = auto()  # Proposed as a fix or feature
    SHADOW_IMPLEMENTATION = auto()  # Written to temporary branch/file
    STABILITY_CHECK = auto()  # Running through StabilityGate
    HIVE_REVIEW = auto()  # Awaiting Reviewer SIGN-OFF
    MERGED = auto()  # Successfully integrated into src/
    REJECTED = auto()  # Failed stability or review
    ROLLED_BACK = auto()  # Failed post-merge health check


@dataclass
class EvolutionTask:
    """An atomic unit of self-evolution."""

    id: str
    lesson_id: str | None
    description: str
    proposed_changes: dict[str, str]  # path: content
    state: EvolutionState = EvolutionState.PROPOSAL
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    stability_report: str | None = None
    reviewer_feedback: str | None = None
    version_tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lesson_id": self.lesson_id,
            "description": self.description,
            "proposed_changes": self.proposed_changes,
            "state": self.state.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "stability_report": self.stability_report,
            "reviewer_feedback": self.reviewer_feedback,
            "version_tag": self.version_tag,
        }


class EvolutionManager:
    """Coordinates the recursive evolution of the Nexus core."""

    def __init__(self, evolution_dir: Path | None = None):
        self.evolution_dir = evolution_dir or Path.home() / ".nexus" / "evolution"
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        self.active_evolutions: dict[str, EvolutionTask] = {}
        self._load_evolutions()

    def _load_evolutions(self) -> None:
        """Load existing evolution states from disk."""
        for file in self.evolution_dir.glob("*.json"):
            with open(file) as f:
                data = json.load(f)
                task = EvolutionTask(
                    id=data["id"],
                    lesson_id=data["lesson_id"],
                    description=data["description"],
                    proposed_changes=data["proposed_changes"],
                    state=EvolutionState[data["state"]],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    stability_report=data.get("stability_report"),
                    reviewer_feedback=data.get("reviewer_feedback"),
                    version_tag=data.get("version_tag"),
                )
                self.active_evolutions[task.id] = task

    def save_evolution(self, task: EvolutionTask) -> None:
        """Persist evolution state to disk."""
        task.updated_at = datetime.now()
        path = self.evolution_dir / f"{task.id}.json"
        with open(path, "w") as f:
            json.dump(task.to_dict(), f, indent=2)

    def propose_evolution(self, description: str, changes: dict[str, str], lesson_id: str | None = None) -> EvolutionTask:
        """Initiate a new evolution proposal."""
        task = EvolutionTask(
            id=str(uuid.uuid4())[:8],
            lesson_id=lesson_id,
            description=description,
            proposed_changes=changes,
            state=EvolutionState.PROPOSAL,
        )
        self.active_evolutions[task.id] = task
        self.save_evolution(task)
        return task

    def transition(self, task_id: str, new_state: EvolutionState, report: str | None = None) -> EvolutionTask:
        """Transition an evolution task to a new state."""
        task = self.active_evolutions.get(task_id)
        if not task:
            raise ValueError(f"Evolution task {task_id} not found.")

        task.state = new_state
        if report:
            task.stability_report = report if new_state == EvolutionState.STABILITY_CHECK else task.stability_report
            if new_state == EvolutionState.HIVE_REVIEW:
                task.reviewer_feedback = report

        self.save_evolution(task)
        return task

    def get_pending_evolutions(self) -> list[EvolutionTask]:
        """Get all evolutions that are not yet merged or rejected."""
        return [t for t in self.active_evolutions.values() if t.state not in (EvolutionState.MERGED, EvolutionState.REJECTED)]
