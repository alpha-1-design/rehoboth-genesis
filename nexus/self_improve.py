"""Self-Improvement Agent — Nexus can improve itself.

This is NOT about self-modifying AGI. It's about:
  1. Writing helper scripts/tools in ~/.nexus/improvements/
  2. Improving tool implementations based on failure patterns
  3. Auto-generating better prompts and system instructions
  4. Creating custom rules based on user preferences
  5. Building project-specific tooling

The improvements/ directory is where Nexus writes code it creates.
User must approve before any improvement is applied.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Improvement:
    """A self-written improvement."""
    improvement_id: str
    created_at: datetime
    title: str
    description: str
    file_path: Path | None = None
    improvement_type: str = "helper"  # helper, tool, rule, prompt, script
    status: str = "draft"  # draft, approved, rejected, applied
    trigger: str = ""  # when to apply this improvement
    code: str = ""
    approved_by: str | None = None
    applied_at: datetime | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "improvement_id": self.improvement_id,
            "created_at": self.created_at.isoformat(),
            "title": self.title,
            "description": self.description,
            "file_path": str(self.file_path) if self.file_path else None,
            "improvement_type": self.improvement_type,
            "status": self.status,
            "trigger": self.trigger,
            "code": self.code,
            "approved_by": self.approved_by,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "notes": self.notes,
        }


class SelfImprovementAgent:
    """
    Nexus's self-improvement system.
    
    Works alongside the learning engine:
      learn.record_failure() → learn.get_applicable_lessons()
                            → self_improver.suggest_improvement()
                            → improvement written to ~/.nexus/improvements/
                            → user approves → applied
    
    Also proactively suggests improvements based on:
      - Repeated failure patterns
      - User preferences (learned from corrections)
      - Project conventions (detected from code)
      - Tool performance (slow tools → better prompts)
    """

    IMPROVEMENTS_DIR = Path.home() / ".nexus" / "improvements"
    PREFERENCES_FILE = Path.home() / ".nexus" / "preferences.json"

    def __init__(self):
        self.improvements_dir = self.IMPROVEMENTS_DIR
        self.improvements_dir.mkdir(parents=True, exist_ok=True)

        self._improvements: list[Improvement] = []
        self._preferences: dict[str, Any] = {}
        self._load_preferences()
        self._load_improvements()

    def _load_preferences(self) -> None:
        """Load learned user preferences."""
        if self.PREFERENCES_FILE.exists():
            try:
                self._preferences = json.loads(self.PREFERENCES_FILE.read_text())
            except Exception:
                self._preferences = {}

    def _save_preferences(self) -> None:
        """Save user preferences."""
        self.PREFERENCES_FILE.write_text(json.dumps(self._preferences, indent=2))

    def learn_preference(self, key: str, value: Any, context: str = "") -> None:
        """Learn a user preference from behavior."""
        self._preferences[key] = {
            "value": value,
            "context": context,
            "learned_at": datetime.now().isoformat(),
        }
        self._save_preferences()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a learned preference."""
        pref = self._preferences.get(key)
        return pref["value"] if pref else default

    def _load_improvements(self) -> None:
        """Load existing improvements."""
        for f in self.improvements_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                if data.get("applied_at"):
                    data["applied_at"] = datetime.fromisoformat(data["applied_at"])
                if data.get("file_path"):
                    data["file_path"] = Path(data["file_path"])
                self._improvements.append(Improvement(**data))
            except Exception:
                pass

    def suggest_improvement(
        self,
        improvement_type: str,
        title: str,
        description: str,
        code: str,
        trigger: str = "",
    ) -> Improvement:
        """Create a new improvement suggestion."""
        import uuid

        imp = Improvement(
            improvement_id=str(uuid.uuid4())[:12],
            created_at=datetime.now(),
            title=title,
            description=description,
            improvement_type=improvement_type,
            code=code,
            trigger=trigger,
            status="draft",
        )

        self._save_improvement(imp)
        self._improvements.append(imp)

        return imp

    def _save_improvement(self, imp: Improvement) -> None:
        """Save improvement to disk."""
        path = self.improvements_dir / f"{imp.improvement_id}.json"
        path.write_text(json.dumps(imp.to_dict(), indent=2))

        # If there's code, also save as a .py file
        if imp.code and imp.status in ("draft", "approved"):
            code_path = self.improvements_dir / f"{imp.improvement_id}.py"
            code_path.write_text(imp.code)
            imp.file_path = code_path

    def approve(self, improvement_id: str, approver: str = "user") -> bool:
        """Approve an improvement (user must do this)."""
        for imp in self._improvements:
            if imp.improvement_id == improvement_id:
                imp.status = "approved"
                imp.approved_by = approver
                self._save_improvement(imp)
                return True
        return False

    def reject(self, improvement_id: str, reason: str = "") -> bool:
        """Reject an improvement."""
        for imp in self._improvements:
            if imp.improvement_id == improvement_id:
                imp.status = "rejected"
                imp.notes = reason
                self._save_improvement(imp)
                return True
        return False

    def apply(self, improvement_id: str) -> dict[str, Any]:
        """Apply an approved improvement."""
        for imp in self._improvements:
            if imp.improvement_id != improvement_id:
                continue

            if imp.status != "approved":
                return {"success": False, "error": "Improvement not approved"}

            if imp.improvement_type == "helper":
                return self._apply_helper(imp)
            elif imp.improvement_type == "tool":
                return self._apply_tool(imp)
            elif imp.improvement_type == "rule":
                return self._apply_rule(imp)
            elif imp.improvement_type == "prompt":
                return self._apply_prompt(imp)

            return {"success": False, "error": "Unknown improvement type"}

        return {"success": False, "error": "Improvement not found"}

    def _apply_helper(self, imp: Improvement) -> dict[str, Any]:
        """Apply a helper script improvement."""
        helpers_dir = self.improvements_dir / "helpers"
        helpers_dir.mkdir(exist_ok=True)

        code_path = helpers_dir / f"{imp.improvement_id}.py"
        code_path.write_text(imp.code)

        imp.status = "applied"
        imp.applied_at = datetime.now()
        imp.file_path = code_path
        self._save_improvement(imp)

        return {"success": True, "path": str(code_path), "message": f"Helper written to {code_path}"}

    def _apply_tool(self, imp: Improvement) -> dict[str, Any]:
        """Apply a tool improvement."""
        # This would integrate with the tool registry
        # For now, save to improvements/tools/
        tools_dir = self.improvements_dir / "tools"
        tools_dir.mkdir(exist_ok=True)

        code_path = tools_dir / f"{imp.improvement_id}.py"
        code_path.write_text(imp.code)

        imp.status = "applied"
        imp.applied_at = datetime.now()
        imp.file_path = code_path
        self._save_improvement(imp)

        return {"success": True, "path": str(code_path), "message": "Tool written to improvements/tools/"}

    def _apply_rule(self, imp: Improvement) -> dict[str, Any]:
        """Apply a rule improvement."""
        # Save as a rules file that gets loaded by the safety engine
        rules_path = self.improvements_dir / f"{imp.improvement_id}_rule.json"
        rules_path.write_text(json.dumps({"rule": imp.description, "code": imp.code}, indent=2))

        imp.status = "applied"
        imp.applied_at = datetime.now()
        imp.file_path = rules_path
        self._save_improvement(imp)

        return {"success": True, "path": str(rules_path), "message": "Rule applied to safety engine"}

    def _apply_prompt(self, imp: Improvement) -> dict[str, Any]:
        """Apply a prompt improvement."""
        # Save improved system prompt
        prompts_path = self.improvements_dir / "prompts"
        prompts_path.mkdir(exist_ok=True)

        prompt_path = prompts_path / f"{imp.improvement_id}.md"
        prompt_path.write_text(f"# {imp.title}\n\n{imp.description}\n\n```\n{imp.code}\n```")

        imp.status = "applied"
        imp.applied_at = datetime.now()
        imp.file_path = prompt_path
        self._save_improvement(imp)

        # Update learned preferences
        self.learn_preference("system_prompt", imp.code, context=imp.trigger)

        return {"success": True, "path": str(prompt_path), "message": "Prompt improvement saved"}

    def generate_reflection_report(self, session_summary: dict[str, Any]) -> str:
        """
        Generate a reflection report after work.
        This is what Nexus shows the user asking:
        "Should I run a self-improvement loop?"
        """
        lines = [
            "\n\033[95m═══════════════════════════════════════════════════════════\033[0m",
            "\033[95m║  🤖 SELF-IMPROVEMENT REVIEW                               ║\033[0m",
            "\033[95m═══════════════════════════════════════════════════════════\033[0m",
            "",
        ]

        # What we accomplished
        if session_summary.get("tasks_completed"):
            lines.append(f"  ✓ Completed: {session_summary['tasks_completed']} task(s)")

        # What failed
        failures = session_summary.get("failures", [])
        if failures:
            lines.append(f"  ✗ Failures: {len(failures)}")
            for f in failures[:3]:
                lines.append(f"    - {f['tool']}: {f['error'][:50]}...")

        # Suggestions
        lines.extend([
            "",
            "  I can run a self-improvement loop that will:",
            "",
            "    📝 Analyze my approach and identify patterns",
            "    🛠️  Write helper scripts for repeated tasks",
            "    📖 Improve my understanding of this project",
            "    🔧 Suggest tool/prompt improvements",
            "    📚 Update my lessons from today's failures",
            "",
        ])

        # Show existing improvements
        applied = [i for i in self._improvements if i.status == "applied"]
        if applied:
            lines.append(f"  Improvements applied so far: {len(applied)}")
            for i in applied[-3:]:
                lines.append(f"    • {i.title}")

        lines.extend([
            "",
            "  Run self-improvement loop? (yes/no): ",
        ])

        return "\n".join(lines)

    def run_improvement_loop(
        self,
        failures: list[dict],
        task_context: str,
        provider_manager=None,
    ) -> list[Improvement]:
        """
        Run the self-improvement loop.
        Uses the AI to analyze failures and generate improvements.
        Returns a list of suggested improvements (user must approve).
        """
        suggestions: list[Improvement] = []

        if not failures:
            return suggestions

        # Analyze failure patterns
        error_types: dict[str, int] = {}
        tool_failures: dict[str, int] = {}

        for f in failures:
            et = f.get("error_type", "UNKNOWN")
            error_types[et] = error_types.get(et, 0) + 1
            tn = f.get("tool_name", "unknown")
            tool_failures[tn] = tool_failures.get(tn, 0) + 1

        # Generate improvements for frequent failure patterns
        most_common_error = max(error_types, key=error_types.get) if error_types else None

        if most_common_error:
            # Write a helper for this error type
            code = self._generate_error_handler(most_common_error, failures)
            imp = self.suggest_improvement(
                improvement_type="helper",
                title=f"Handler: {most_common_error}",
                description=f"Auto-generated handler for {most_common_error} errors. "
                           f"Occurred {error_types[most_common_error]} times this session.",
                code=code,
                trigger=f"error_type:{most_common_error}",
            )
            suggestions.append(imp)

        # Generate a project-specific helper if there were many failures
        if len(failures) >= 3:
            project_helper = self._generate_project_helper(failures, task_context)
            imp = self.suggest_improvement(
                improvement_type="helper",
                title="Project Helper Script",
                description="Auto-generated helper tailored to this project's patterns. "
                           "Created based on repeated interactions.",
                code=project_helper,
                trigger=f"context:{task_context[:50]}",
            )
            suggestions.append(imp)

        # Save all improvements
        for imp in suggestions:
            self._save_improvement(imp)

        return suggestions

    def _generate_error_handler(self, error_type: str, failures: list[dict]) -> str:
        """Generate a Python error handler for an error type."""
        handlers = {
            "NOT_FOUND": '''"""Auto-generated: NOT_FOUND error handler for Nexus."""
import asyncio
from pathlib import Path


async def safe_file_operation(path: str | Path, operation: callable, *args, **kwargs):
    """
    Safely perform a file operation, checking existence first.
    Falls back gracefully if file doesn't exist.
    """
    path = Path(path)
    
    if operation.__name__ in ("read", "read_text"):
        if not path.exists():
            return {"success": False, "error": f"File not found: {path}"}
    
    if operation.__name__ in ("write", "write_text"):
        path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        result = await operation(*args, **kwargs) if asyncio.iscoroutinefunction(operation) \\
                                 else operation(*args, **kwargs)
        return {"success": True, "result": result}
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {path}", "recovered": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
''',
            "NETWORK_TIMEOUT": '''"""Auto-generated: NETWORK_TIMEOUT error handler for Nexus."""
import asyncio
import httpx


async def resilient_request(
    url: str,
    method: str = "GET",
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs,
) -> dict:
    """
    Make an HTTP request with exponential backoff retry logic.
    """
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 30.0)) as client:
                response = await client.request(method, url, **kwargs)
                return {
                    "success": True,
                    "status": response.status_code,
                    "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                }
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == max_retries - 1:
                return {"success": False, "error": f"Failed after {max_retries} attempts: {e}"}
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay)
    
    return {"success": False, "error": "Max retries exceeded"}
''',
        }

        return handlers.get(error_type, f'''"""Auto-generated handler for {error_type}."""\n\n# TODO: Implement {error_type} handler\n''')

    def _generate_project_helper(self, failures: list[dict], task_context: str) -> str:
        """Generate a project-specific helper script."""
        tools_used = list(set(f.get("tool_name", "") for f in failures))

        return f'''"""Auto-generated project helper for Nexus.
Generated from session analysis. User should review before relying on this.
Context: {task_context[:100]}
"""
import asyncio
from pathlib import Path


# Project-specific shortcuts based on {len(failures)} analyzed interactions
TOOLS = {tools_used}


async def project_quick_task(task_type: str, **kwargs):
    """
    Quick task dispatcher based on detected project patterns.
    """
    handlers = {{
        # Add project-specific handlers here
    }}
    
    handler = handlers.get(task_type)
    if handler:
        return await handler(**kwargs)
    
    return {{"error": f"No handler for task type: {{task_type}}"}}


def detect_project_root(path: Path | None = None) -> Path | None:
    """Detect project root from common markers."""
    markers = [".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]
    search = (path or Path.cwd())
    
    while search != search.parent:
        if any((search / m).exists() for m in markers):
            return search
        search = search.parent
    
    return None
'''

    def get_improvement_queue(self) -> list[Improvement]:
        """Get improvements awaiting approval."""
        return [i for i in self._improvements if i.status == "draft"]

    def format_improvement_queue(self) -> str:
        """Format the improvement queue for display."""
        queue = self.get_improvement_queue()
        if not queue:
            return "  No improvements pending approval."

        lines = [f"\n  {len(queue)} improvement(s) awaiting approval:"]
        for imp in queue:
            type_icon = {"helper": "🛠️", "tool": "🔧", "rule": "📋", "prompt": "📝"}.get(imp.improvement_type, "📄")
            lines.append(f"  {type_icon} [{imp.improvement_id}] {imp.title}")
            lines.append(f"      {imp.description[:70]}...")
            lines.append(f"      Use /improve approve {imp.improvement_id} to approve")

        return "\n".join(lines)


# Global singleton
_self_improver: SelfImprovementAgent | None = None


def get_self_improver() -> SelfImprovementAgent:
    global _self_improver
    if _self_improver is None:
        _self_improver = SelfImprovementAgent()
    return _self_improver
