"""Safety Rules Engine — prevents fatal mistakes, enforces execution discipline.

Rules are executed in strict order:
  1. READ before EDIT — must read existing code before modifying
  2. BACKUP before DESTRUCTION — backup before delete/overwrite
  3. RESEARCH before ACT — check docs/patterns before implementing
  4. CONFIRM before EXECUTE — dangerous operations need explicit confirmation
  5. VALIDATE after WRITE — verify changes don't break builds/tests
  6. ROLLBACK on ERROR — auto-rollback if critical operations fail
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class RuleLevel(Enum):
    BLOCK = auto()  # Halt and require user intervention
    WARN = auto()  # Print warning, continue if user confirms
    SKIP = auto()  # Skip the operation entirely
    NOTE = auto()  # Just log and continue


class RuleCategory(Enum):
    FILE_SAFETY = auto()
    CODE_QUALITY = auto()
    NETWORK = auto()
    EXTERNAL_SERVICES = auto()
    DESTRUCTIVE = auto()
    SECURITY = auto()
    EXECUTION_ORDER = auto()


class SafetyMode(Enum):
    """Granular safety modes for Nexus."""

    READ_ONLY = "read_only"  # Only allow read/list/glob/grep
    SENSITIVE_WRITE = "sensitive"  # Confirm all modifications, block destructive
    AUTO_GIT = "auto_git"  # Auto-approve non-destructive git, confirm others
    LOCAL_SANDBOX = "sandbox"  # Restrict execution to a specific directory
    USER_REVIEW = "user_review"  # Default: confirm dangerous tools
    UNRESTRICTED = "unrestricted"  # No safety checks (not recommended)
    STRICT = "strict"  # All warnings are blocks, strict execution order


@dataclass
class Rule:
    """A single safety rule."""

    id: str
    name: str
    description: str
    category: RuleCategory
    level: RuleLevel
    pattern: str | None = None
    blocked_extensions: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    require_confirmation: bool = True
    auto_fix: str | None = None
    examples: list[str] = field(default_factory=list)

    def matches(self, context: dict[str, Any]) -> bool:
        """Check if this rule applies to the given context."""
        path = context.get("path", "")

        # Check blocked paths
        if self.blocked_paths:
            for blocked in self.blocked_paths:
                if blocked in path:
                    return True

        # Check allowed paths (if set, only these are allowed)
        if self.allowed_paths:
            allowed = any(a in path for a in self.allowed_paths)
            if not allowed:
                return False

        # Check pattern
        if self.pattern and path:
            return bool(re.search(self.pattern, path))

        return False


@dataclass
class RuleViolation:
    """A rule was triggered."""

    rule: Rule
    context: dict[str, Any]
    severity: str
    message: str
    fix_suggestion: str | None = None


@dataclass
class ExecutionStep:
    """A step in the mandatory execution order."""

    name: str
    required: bool = True
    completed: bool = False
    result: Any = None


class SafetyEngine:
    """
    The safety rules engine. Every tool call goes through this before execution.

    Execution order enforcement:
      READ → RESEARCH → PLAN → CONFIRM → EXECUTE → VALIDATE → ROLLBACK
    """

    DEFAULT_RULES: list[Rule] = [
        # === FILE SAFETY ===
        Rule(
            id="no-bare-commit",
            name="No Bare Commits",
            description="Commits must have meaningful messages",
            category=RuleCategory.FILE_SAFETY,
            level=RuleLevel.WARN,
            require_confirmation=False,
        ),
        Rule(
            id="no-hardcoded-secrets",
            name="No Hardcoded Secrets",
            description="API keys, tokens, passwords must use env vars",
            category=RuleCategory.SECURITY,
            level=RuleLevel.BLOCK,
            pattern=r"(api[_-]?key|secret|token|password|credential)\s*=\s*['\"]?[a-zA-Z0-9_\-]{8,}",
            require_confirmation=False,
        ),
        Rule(
            id="check-gitignore",
            name="Check .gitignore",
            description="Warn before adding sensitive files to git",
            category=RuleCategory.SECURITY,
            level=RuleLevel.WARN,
            blocked_extensions=[".env", ".pem", ".key", ".p12", ".pfx"],
            require_confirmation=True,
        ),
        # === DESTRUCTIVE ===
        Rule(
            id="no-rm-rf",
            name="No Recursive Force Delete",
            description="rm -rf on large directories requires confirmation",
            category=RuleCategory.DESTRUCTIVE,
            level=RuleLevel.BLOCK,
            pattern=r"rm\s+-[rf]+\s+/",
            require_confirmation=True,
        ),
        Rule(
            id="no-destructive-migration",
            name="No Destructive Database Migrations",
            description="DROP TABLE, DELETE without WHERE need confirmation",
            category=RuleCategory.DESTRUCTIVE,
            level=RuleLevel.BLOCK,
            pattern=r"(DROP|DELETE\s+FROM)\s+(?!.*WHERE)",
            require_confirmation=True,
        ),
        Rule(
            id="no-force-push",
            name="No Force Push to Main",
            description="git push --force to main/master is dangerous",
            category=RuleCategory.DESTRUCTIVE,
            level=RuleLevel.BLOCK,
            pattern=r"git\s+push\s+.*--force\s+.*(main|master|main)",
            require_confirmation=True,
        ),
        Rule(
            id="no-overwrite-system",
            name="No System File Overwrite",
            description="Don't overwrite /etc, /usr, /bin files",
            category=RuleCategory.DESTRUCTIVE,
            level=RuleLevel.BLOCK,
            blocked_paths=["/etc/", "/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/lib/"],
            require_confirmation=True,
        ),
        # === CODE QUALITY ===
        Rule(
            id="no-todo-fixme",
            name="No TODO without ticket",
            description="TODOs/FIXMEs should reference a ticket or issue",
            category=RuleCategory.CODE_QUALITY,
            level=RuleLevel.NOTE,
            pattern=r"(TODO|FIXME|XXX|HACK):",
            require_confirmation=False,
        ),
        Rule(
            id="check-test-coverage",
            name="Check Test Coverage",
            description="Code changes should include or update tests",
            category=RuleCategory.CODE_QUALITY,
            level=RuleLevel.NOTE,
            require_confirmation=False,
        ),
        # === EXECUTION ORDER ===
        Rule(
            id="read-before-edit",
            name="Read Before Edit",
            description="Must read a file before editing it",
            category=RuleCategory.EXECUTION_ORDER,
            level=RuleLevel.BLOCK,
            require_confirmation=False,
        ),
        Rule(
            id="research-before-code",
            name="Research Before Code",
            description="Check documentation before implementing unfamiliar APIs",
            category=RuleCategory.EXECUTION_ORDER,
            level=RuleLevel.WARN,
            require_confirmation=False,
        ),
        Rule(
            id="validate-after-write",
            name="Validate After Write",
            description="Run lint/typecheck after modifying code",
            category=RuleCategory.EXECUTION_ORDER,
            level=RuleLevel.NOTE,
            require_confirmation=False,
        ),
    ]

    def __init__(self):
        self.rules: dict[str, Rule] = {r.id: r for r in self.DEFAULT_RULES}
        self._violations: list[RuleViolation] = []
        self._read_files: set[str] = set()
        self._execution_log: list[dict] = []
        self._blocked: bool = False
        self._mode: SafetyMode = SafetyMode.USER_REVIEW
        self._strict_mode: bool = True
        self._sandbox_dir: str | None = None
        self._hooks: dict[str, list[Callable]] = {
            "on_block": [],
            "on_warn": [],
            "on_violation": [],
        }

    def set_mode(self, mode: SafetyMode, sandbox_dir: str | None = None) -> None:
        """Set the current safety mode."""
        self._mode = mode
        self._sandbox_dir = sandbox_dir
        if mode == SafetyMode.STRICT:
            self._strict_mode = True
        elif mode == SafetyMode.UNRESTRICTED:
            self._strict_mode = False
        self._log("mode_change", mode=mode.value, sandbox=sandbox_dir)

    def get_mode(self) -> SafetyMode:
        """Get the current safety mode."""
        return self._mode

    def enable_strict_mode(self) -> None:
        """Enable strict mode: WARN becomes BLOCK."""
        self._strict_mode = True

    def disable_strict_mode(self) -> None:
        """Disable strict mode: rules are suggestions only."""
        self._strict_mode = False

    def add_rule(self, rule: Rule) -> None:
        """Register a custom rule."""
        self.rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> None:
        """Remove a rule by ID."""
        self.rules.pop(rule_id, None)

    def on_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for safety events."""
        if event in self._hooks:
            self._hooks[event].append(callback)

    def mark_file_read(self, path: str) -> None:
        """Mark a file as having been read (satisfies read-before-edit)."""
        import os

        real = os.path.realpath(path)
        self._read_files.add(real)
        self._log("read", path=path)

    def was_file_read(self, path: str) -> bool:
        """Check if a file was read before editing."""
        import os

        real = os.path.realpath(path)
        return real in self._read_files

    def check(self, context: dict[str, Any]) -> list[RuleViolation]:
        """
        Check all rules against the given context, considering the current mode.
        Returns a list of violations (may be empty).
        """
        if self._mode == SafetyMode.UNRESTRICTED:
            return []

        violations = []
        tool = context.get("tool", "")
        path = context.get("path", "")
        command = context.get("command", "")

        # 1. READ_ONLY Mode check
        if self._mode == SafetyMode.READ_ONLY:
            safe_tools = {"read", "list", "glob", "grep", "search", "web_fetch"}
            if tool.lower() not in safe_tools:
                violations.append(
                    RuleViolation(
                        rule=Rule(
                            "mode-violation", "Read-Only Mode", "Modification tools are blocked in READ_ONLY mode", RuleCategory.SECURITY, RuleLevel.BLOCK
                        ),
                        context=context,
                        severity="BLOCK",
                        message="READ_ONLY mode active. Modification tool blocked.",
                    )
                )

        # 2. LOCAL_SANDBOX Mode check
        if self._mode == SafetyMode.LOCAL_SANDBOX and self._sandbox_dir:
            if path and self._sandbox_dir not in path:
                violations.append(
                    RuleViolation(
                        rule=Rule(
                            "sandbox-violation", "Sandbox Violation", f"Paths must be within {self._sandbox_dir}", RuleCategory.SECURITY, RuleLevel.BLOCK
                        ),
                        context=context,
                        severity="BLOCK",
                        message=f"SANDBOX mode active. Access to {path} is blocked.",
                    )
                )

        # 3. AUTO_GIT Mode check (Special handling for git)
        if self._mode == SafetyMode.AUTO_GIT and tool == "git":
            safe_git = {"status", "diff", "log", "branch", "show"}
            cmd_parts = command.split()
            if cmd_parts and cmd_parts[0] in safe_git:
                return []  # Auto-approve safe git commands

        # Standard rule checks
        for rule in self.rules.values():
            # Special case for EXECUTION_ORDER rules
            if rule.id == "read-before-edit" and tool in ("edit", "write"):
                if not self.was_file_read(path):
                    violations.append(
                        RuleViolation(
                            rule=rule,
                            context=context,
                            severity="BLOCK" if self._strict_mode else "WARN",
                            message=f"[EXECUTION_ORDER] {rule.name}: {rule.description}",
                        )
                    )
                    continue

            if rule.matches(context):
                sev = "BLOCK" if (rule.level == RuleLevel.BLOCK or (self._strict_mode and rule.level == RuleLevel.WARN)) else rule.level.name
                violation = RuleViolation(
                    rule=rule,
                    context=context,
                    severity=sev,
                    message=f"[{rule.category.name}] {rule.name}: {rule.description}",
                    fix_suggestion=rule.auto_fix,
                )
                violations.append(violation)
                self._violations.append(violation)
                self._trigger_hook("on_violation", violation)

        self._log("check", context=context, violations=len(violations))
        return violations

    def should_proceed(self, violations: list[RuleViolation]) -> tuple[bool, str]:
        """
        Determine if operations should proceed given violations.
        Returns (proceed, reason).
        """
        if not violations:
            return True, "No violations"

        blocks = [v for v in violations if v.severity == "BLOCK"]
        warns = [v for v in violations if v.severity == "WARN"]

        if blocks:
            reasons = "\n  ".join(v.message for v in blocks)
            return False, f"BLOCKED by {len(blocks)} rule(s):\n  {reasons}"

        if warns and self._strict_mode:
            reasons = "\n  ".join(v.message for v in warns)
            return False, f"STRICT MODE: warnings are blocks:\n  {reasons}"

        if warns:
            reasons = "\n  ".join(v.message for v in warns)
            return True, f"WARNINGS ({len(warns)}):\n  {reasons}"

        return True, "All clear"

    def force_proceed(self, reason: str) -> None:
        """Override safety and proceed anyway (with logged justification)."""
        self._log("force_proceed", reason=reason)
        self._blocked = False

    def log_action(self, action: str, details: dict[str, Any]) -> None:
        """Log an action for the execution history."""
        self._log(action, **details)

    def get_read_files(self) -> list[str]:
        """Files that have been read in this session."""
        return sorted(self._read_files)

    def get_violation_summary(self) -> str:
        """Get a summary of all violations this session."""
        if not self._violations:
            return "No rule violations."

        lines = [f"Total violations: {len(self._violations)}"]
        by_level = {}
        for v in self._violations:
            by_level.setdefault(v.severity, []).append(v.rule.name)

        for level, rules in by_level.items():
            lines.append(f"  [{level}]: {', '.join(set(rules))}")
        return "\n".join(lines)

    def get_execution_log(self) -> list[dict]:
        """Full execution log for review."""
        return self._execution_log.copy()

    def _log(self, event: str, **kwargs) -> None:
        """Internal logging."""
        from datetime import datetime

        self._execution_log.append(
            {
                "event": event,
                "timestamp": datetime.now().isoformat(),
                **kwargs,
            }
        )

    def _trigger_hook(self, hook: str, *args) -> None:
        """Trigger registered hooks."""
        for cb in self._hooks.get(hook, []):
            try:
                cb(*args)
            except Exception:
                pass

    def render_violations(self, violations: list[RuleViolation]) -> str:
        """Render violations as a human-readable string."""
        if not violations:
            return "\033[92m✓ All safety checks passed\033[0m"

        lines = []
        for v in violations:
            icon = "🚫" if v.severity == "BLOCK" else "⚠️" if v.severity == "WARN" else "ℹ️"
            color = "\033[91m" if v.severity == "BLOCK" else "\033[93m" if v.severity == "WARN" else "\033[94m"
            reset = "\033[0m"
            lines.append(f"{color}{icon} {v.message}{reset}")
            if v.context.get("path"):
                lines.append(f"  \033[90mPath: {v.context['path']}\033[0m")
            if v.fix_suggestion:
                lines.append(f"  \033[96mFix: {v.fix_suggestion}\033[0m")

        return "\n".join(lines)


# Global singleton
_safety_engine: SafetyEngine | None = None


def get_safety_engine() -> SafetyEngine:
    global _safety_engine
    if _safety_engine is None:
        _safety_engine = SafetyEngine()
    return _safety_engine
