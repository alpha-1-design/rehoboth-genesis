"""Failure Learning System — every failure becomes a lesson.

How it works:
  1. Every failed tool call → logged with full context
  2. After each session → review and generate lessons
  3. Lessons are stored and applied before future similar tasks
  4. After work → prompt user: "Run reflection loop?"
  5. Self-improvement loop → analyzes own behavior, writes improvements

The learning directory: ~/.nexus/learn/
  - failures/    — raw failure records (JSON)
  - lessons/    — synthesized lessons (Markdown)
  - patterns/   — detected patterns (what causes failures)
  - improvements/ — self-written code improvements
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json


@dataclass
class FailureRecord:
    """A complete record of a failed operation."""
    failure_id: str
    timestamp: datetime
    tool_name: str
    args: dict[str, Any]
    error: str
    error_type: str
    session_id: str
    context: dict[str, Any]  # what was the user trying to do
    attempts: int = 1
    resolution: str | None = None
    resolved_by: str | None = None  # "user", "retry", "manual_fix"
    lesson_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "args": self.args,
            "error": self.error,
            "error_type": self.error_type,
            "session_id": self.session_id,
            "context": self.context,
            "attempts": self.attempts,
            "resolution": self.resolution,
            "resolved_by": self.resolved_by,
            "lesson_id": self.lesson_id,
        }


@dataclass
class Lesson:
    """A synthesized lesson from failures."""
    lesson_id: str
    created_at: datetime
    title: str
    summary: str
    trigger_conditions: list[str]  # keywords/patterns that activate this lesson
    solution: str  # what to do
    code_snippet: str | None = None
    examples: list[str] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    source_failures: list[str] = field(default_factory=list)  # failure_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "created_at": self.created_at.isoformat(),
            "title": self.title,
            "summary": self.summary,
            "trigger_conditions": self.trigger_conditions,
            "solution": self.solution,
            "code_snippet": self.code_snippet,
            "examples": self.examples,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "source_failures": self.source_failures,
        }

    def to_markdown(self) -> str:
        return f"""# Lesson: {self.title}

**Created:** {self.created_at.date()}
**Success Rate:** {self.success_count}/{self.success_count + self.failure_count}

## Summary
{self.summary}

## When to Apply
{chr(10).join(f"- {c}" for c in self.trigger_conditions)}

## Solution
{self.solution}

{f'## Code Snippet\n```python\n{self.code_snippet}\n```' if self.code_snippet else ''}

## Examples
{chr(10).join(f"{i+1}. {e}" for i, e in enumerate(self.examples))}
"""


class LearningEngine:
    """
    The failure learning system. Records failures, synthesizes lessons,
    and applies them proactively.
    
    Flow:
      failure → record → analyze → lesson → apply → reflect
    """

    def __init__(self, learn_dir: Path | None = None):
        self.learn_dir = learn_dir or (Path.home() / ".nexus" / "learn")
        self.failures_dir = self.learn_dir / "failures"
        self.lessons_dir = self.learn_dir / "lessons"
        self.patterns_dir = self.learn_dir / "patterns"
        self.improvements_dir = self.learn_dir / "improvements"
        
        for d in [self.failures_dir, self.lessons_dir, self.patterns_dir, self.improvements_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        self._current_session_failures: list[FailureRecord] = []
        self._session_id: str = ""
        self._lessons_cache: list[Lesson] | None = None

    def get_session_stats(self, session_id: str) -> dict[str, Any]:
        """Get statistics for a specific session."""
        failures = [f for f in self._current_session_failures if f.session_id == session_id]
        
        # Aggregate tool usage
        tool_usage: dict[str, int] = {}
        for f in failures:
            tool_usage[f.tool_name] = tool_usage.get(f.tool_name, 0) + 1
            
        return {
            "session_id": session_id,
            "failures": [f.to_dict() for f in failures],
            "tool_usage": tool_usage
        }

    def start_session(self, session_id: str) -> None:
        """Mark the start of a learning session."""
        self._session_id = session_id
        self._current_session_failures = []

    def record_failure(
        self,
        tool_name: str,
        args: dict[str, Any],
        error: str,
        context: dict[str, Any],
        attempts: int = 1,
    ) -> FailureRecord:
        """Record a failed operation."""
        import uuid
        
        error_type = self._classify_error(error)
        record = FailureRecord(
            failure_id=str(uuid.uuid4())[:12],
            timestamp=datetime.now(),
            tool_name=tool_name,
            args=args,
            error=error,
            error_type=error_type,
            session_id=self._session_id,
            context=context,
            attempts=attempts,
        )
        
        self._current_session_failures.append(record)
        
        # Save to disk
        path = self.failures_dir / f"{record.failure_id}.json"
        path.write_text(json.dumps(record.to_dict(), indent=2))
        
        return record

    def resolve_failure(self, failure_id: str, resolution: str, resolved_by: str = "user") -> None:
        """Mark a failure as resolved and update."""
        path = self.failures_dir / f"{failure_id}.json"
        if not path.exists():
            return
        
        data = json.loads(path.read_text())
        data["resolution"] = resolution
        data["resolved_by"] = resolved_by
        path.write_text(json.dumps(data, indent=2))
        
        # Update in-memory record if present
        for f in self._current_session_failures:
            if f.failure_id == failure_id:
                f.resolution = resolution
                f.resolved_by = resolved_by
                break

    def _classify_error(self, error: str) -> str:
        """Classify an error into a category."""
        error_lower = error.lower()
        
        if any(x in error_lower for x in ["not found", "no such file", "does not exist", "404"]):
            return "NOT_FOUND"
        elif any(x in error_lower for x in ["permission denied", "access denied", "forbidden", "401", "403"]):
            return "PERMISSION_DENIED"
        elif any(x in error_lower for x in ["timeout", "timed out", "connection refused"]):
            return "NETWORK_TIMEOUT"
        elif any(x in error_lower for x in ["syntax", "parse", "invalid", "malformed"]):
            return "SYNTAX_ERROR"
        elif any(x in error_lower for x in ["memory", "out of", "overflow", "recursion"]):
            return "RESOURCE_ERROR"
        elif any(x in error_lower for x in ["rate limit", "quota", "exceeded"]):
            return "RATE_LIMIT"
        elif any(x in error_lower for x in ["api key", "authentication", "unauthorized", "invalid token"]):
            return "AUTH_ERROR"
        elif any(x in error_lower for x in ["import", "module", "no module"]):
            return "IMPORT_ERROR"
        else:
            return "UNKNOWN"

    def synthesize_lesson(self, failure: FailureRecord) -> Lesson:
        """
        Synthesize a lesson from a failure record.
        In production, this would use the AI to generate the lesson.
        For now, it creates a template-based lesson.
        """
        import uuid
        
        trigger_conditions = [
            f"tool:{failure.tool_name}",
            f"error_type:{failure.error_type}",
        ]
        
        # Extract keywords from error
        words = failure.error.split()
        trigger_conditions.extend(w for w in words if len(w) > 4 and w.isalpha())
        
        lesson = Lesson(
            lesson_id=str(uuid.uuid4())[:12],
            created_at=datetime.now(),
            title=f"{failure.tool_name}: {failure.error_type.replace('_', ' ').title()}",
            summary=f"When using `{failure.tool_name}`, encountered: {failure.error[:200]}",
            trigger_conditions=trigger_conditions,
            solution=self._suggest_solution(failure),
            code_snippet=self._suggest_code(failure),
            examples=[f"Failed with args: {json.dumps(failure.args)}"],
            source_failures=[failure.failure_id],
        )
        
        # Save lesson
        path = self.lessons_dir / f"{lesson.lesson_id}.json"
        path.write_text(json.dumps(lesson.to_dict(), indent=2))
        
        # Also save as markdown
        md_path = self.lessons_dir / f"{lesson.lesson_id}.md"
        md_path.write_text(lesson.to_markdown())
        
        failure.lesson_id = lesson.lesson_id
        return lesson

    def _suggest_solution(self, failure: FailureRecord) -> str:
        """Suggest a solution for the failure type."""
        solutions = {
            "NOT_FOUND": f"Check if the target exists before calling `{failure.tool_name}`. "
                        "Verify file paths, URLs, and resource IDs.",
            "PERMISSION_DENIED": f"Ensure proper permissions before calling `{failure.tool_name}`. "
                                "Check if the user has the required access level.",
            "NETWORK_TIMEOUT": f"Add retry logic with exponential backoff for `{failure.tool_name}`. "
                              "Consider increasing timeout values.",
            "SYNTAX_ERROR": f"Validate input format before calling `{failure.tool_name}`. "
                           "Check the argument structure matches expected types.",
            "RATE_LIMIT": f"Implement rate limiting for `{failure.tool_name}`. "
                         "Add delays between calls and respect API quotas.",
            "AUTH_ERROR": f"Verify authentication credentials for `{failure.tool_name}`. "
                         "Check if API keys are valid and not expired.",
            "IMPORT_ERROR": f"Ensure required modules are installed before using `{failure.tool_name}`. "
                           "Try importing the module first to verify availability.",
            "RESOURCE_ERROR": f"Reduce scope or batch size for `{failure.tool_name}`. "
                             "Consider processing in smaller chunks.",
        }
        return solutions.get(failure.error_type, 
            f"Review the error message and adjust the approach for `{failure.tool_name}`.")

    def _suggest_code(self, failure: FailureRecord) -> str | None:
        """Suggest a code pattern to prevent this failure."""
        if failure.error_type == "NOT_FOUND":
            return f'''async def safe_{failure.tool_name}(...):
    # Check if target exists first
    if not await check_exists(target):
        logger.warning(f"Target {{target}} not found")
        return None
    return await {failure.tool_name}(...)'''
        
        if failure.error_type == "NETWORK_TIMEOUT":
            return f'''import asyncio

async def resilient_{failure.tool_name}(...):
    for attempt in range(3):
        try:
            return await {failure.tool_name}(...)
        except TimeoutError as e:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)  # exponential backoff
    return None'''
        
        if failure.error_type == "RATE_LIMIT":
            return f'''import asyncio

async def rate_limited_{failure.tool_name}(...):
    async with rate_limiter:
        return await {failure.tool_name}(...)'''
        
        return None

    def get_applicable_lessons(self, task: str, tool_name: str | None = None) -> list[Lesson]:
        """Get lessons applicable to the current task."""
        lessons = self._load_all_lessons()
        applicable = []
        
        task_lower = task.lower()
        for lesson in lessons:
            # Check if any trigger condition matches
            for trigger in lesson.trigger_conditions:
                trigger_lower = trigger.lower()
                if trigger_lower in task_lower or \
                   (tool_name and trigger_lower == f"tool:{tool_name}"):
                    applicable.append(lesson)
                    break
                # Also check if error type keywords appear
                if any(w in task_lower for w in trigger_lower.split()):
                    applicable.append(lesson)
                    break
        
        return applicable

    def _load_all_lessons(self) -> list[Lesson]:
        """Load all lessons from disk."""
        if self._lessons_cache is not None:
            return self._lessons_cache
        
        lessons = []
        for f in self.lessons_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                lessons.append(Lesson(**data))
            except Exception:
                pass
        
        lessons.sort(key=lambda l: l.success_count / max(1, l.success_count + l.failure_count), reverse=True)
        self._lessons_cache = lessons
        return lessons

    def end_session(self, session_id: str, outcome: str = "completed") -> dict[str, Any]:
        """
        Called when a session ends. Reviews failures and synthesizes lessons.
        Returns a summary of what was learned.
        """
        failures = [f for f in self._current_session_failures if f.session_id == session_id]
        
        if not failures:
            return {"failures": 0, "lessons_created": 0, "outcome": outcome}
        
        lessons_created = 0
        for failure in failures:
            if not failure.resolution:
                failure.resolution = outcome
                failure.resolved_by = "session_end"
            lesson = self.synthesize_lesson(failure)
            lessons_created += 1
        
        self._lessons_cache = None  # Invalidate cache
        
        return {
            "failures": len(failures),
            "lessons_created": lessons_created,
            "outcome": outcome,
            "resolution_rate": sum(1 for f in failures if f.resolution) / len(failures),
        }

    def get_stats(self) -> dict[str, Any]:
        """Get learning statistics."""
        failures = list(self.failures_dir.glob("*.json"))
        lessons = list(self.lessons_dir.glob("*.json"))
        
        error_types: dict[str, int] = {}
        for f in failures:
            try:
                data = json.loads(f.read_text())
                et = data.get("error_type", "UNKNOWN")
                error_types[et] = error_types.get(et, 0) + 1
            except Exception:
                pass
        
        resolved = sum(1 for f in failures if json.loads(f.read_text()).get("resolution"))
        
        return {
            "total_failures": len(failures),
            "total_lessons": len(lessons),
            "resolved_failures": resolved,
            "resolution_rate": resolved / max(1, len(failures)),
            "errors_by_type": error_types,
            "improvements_count": len(list(self.improvements_dir.glob("*.py"))),
        }

    def format_summary(self) -> str:
        """Format learning stats for display."""
        stats = self.get_stats()
        
        lines = ["\n=== Nexus Learning Stats ==="]
        lines.append(f"  Failures recorded: {stats['total_failures']}")
        lines.append(f"  Lessons learned: {stats['total_lessons']}")
        lines.append(f"  Resolution rate: {stats['resolution_rate']:.0%}")
        
        if stats["errors_by_type"]:
            lines.append("  Top error types:")
            sorted_errors = sorted(stats["errors_by_type"].items(), key=lambda x: -x[1])[:5]
            for et, count in sorted_errors:
                lines.append(f"    {et}: {count}")
        
        return "\n".join(lines)

    def ask_reflection(self) -> str:
        """Build the reflection prompt shown to user after work."""
        stats = self.get_stats()
        failures = self._current_session_failures
        
        if not failures:
            return ""
        
        lines = [
            "\n\033[93m═══════════════════════════════════════════════════════════\033[0m",
            "\033[93m║  🎓 LEARNING REVIEW — Want me to reflect on this session?\033[[0m",
            "\033[93m═══════════════════════════════════════════════════════════\033[0m",
            f"  I encountered {len(failures)} failure(s) this session.",
            "",
            "  I can run a self-reflection loop that will:",
            "    1. Analyze what went wrong and why",
            "    2. Generate lessons from failures",
            "    3. Check if similar tasks can be handled better",
            "    4. Suggest code improvements for my own tools",
            "",
        ]
        
        if failures:
            lines.append("  Failures this session:")
            for f in failures[-3:]:
                lines.append(f"    ✗ {f.tool_name}: {f.error[:60]}...")
        
        lines.extend([
            "",
            "  Run reflection loop? (yes/no/silent): ",
        ])
        
        return "\n".join(lines)


# Global singleton
_learning_engine: LearningEngine | None = None


def get_learning_engine() -> LearningEngine:
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine()
    return _learning_engine
