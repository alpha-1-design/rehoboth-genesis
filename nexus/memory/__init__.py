"""Structured memory system for Nexus.

Provides session management, facts storage, and project context.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Session:
    """A conversation session."""
    id: str
    created_at: datetime
    updated_at: datetime
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    outcome: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": self.messages,
            "tools_used": self.tools_used,
            "outcome": self.outcome,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            messages=data.get("messages", []),
            tools_used=data.get("tools_used", []),
            outcome=data.get("outcome"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Fact:
    """A stored fact about the user or project."""
    key: str
    value: Any
    category: str = "general"
    confidence: float = 1.0
    source: str = "session"
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }


class Memory:
    """Structured memory manager."""

    def __init__(self, memory_dir: Path | None = None):
        from ..config import DEFAULT_MEMORY_DIR
        self.memory_dir = memory_dir or DEFAULT_MEMORY_DIR
        self.sessions_dir = self.memory_dir / "sessions"
        self.projects_dir = self.memory_dir / "projects"
        self.facts_file = self.memory_dir / "facts.json"
        self.todos_file = self.memory_dir / "todos.json"

        self._ensure_dirs()
        self._facts: dict[str, Fact] = {}
        self._load_facts()

    def _ensure_dirs(self) -> None:
        """Ensure memory directories exist."""
        for d in [self.sessions_dir, self.projects_dir, self.memory_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _load_facts(self) -> None:
        """Load facts from disk."""
        if self.facts_file.exists():
            with open(self.facts_file) as f:
                data = json.load(f)
                for key, value in data.items():
                    if isinstance(value, dict):
                        self._facts[key] = Fact(
                            key=key,
                            value=value.get("value"),
                            category=value.get("category", "general"),
                            confidence=value.get("confidence", 1.0),
                            source=value.get("source", "session"),
                            created_at=datetime.fromisoformat(value.get("created_at", datetime.now().isoformat())),
                        )
                    else:
                        self._facts[key] = Fact(key=key, value=value)

    def _save_facts(self) -> None:
        """Save facts to disk."""
        data = {key: fact.to_dict() for key, fact in self._facts.items()}
        with open(self.facts_file, "w") as f:
            json.dump(data, f, indent=2)

    def create_session(self) -> Session:
        """Create a new session."""
        session = Session(
            id=str(uuid.uuid4())[:8],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.save_session(session)
        return session

    def save_session(self, session: Session) -> None:
        """Save a session to disk."""
        session.updated_at = datetime.now()
        path = self.sessions_dir / f"{session.id}.json"
        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

    def load_session(self, session_id: str) -> Session | None:
        """Load a session from disk."""
        path = self.sessions_dir / f"{session_id}.json"
        if path.exists():
            with open(path) as f:
                return Session.from_dict(json.load(f))
        return None

    def list_sessions(self, limit: int = 20) -> list[Session]:
        """List recent sessions."""
        sessions = []
        for path in sorted(self.sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            with open(path) as f:
                sessions.append(Session.from_dict(json.load(f)))
        return sessions

    def add_fact(self, key: str, value: Any, category: str = "general", confidence: float = 1.0, project_id: str | None = None) -> None:
        """Add a fact to memory, optionally scoped to a project."""
        if project_id:
            project_context = self.load_project_context(project_id) or {}
            facts = project_context.get("facts", {})
            facts[key] = Fact(key=key, value=value, category=category, confidence=confidence, source=f"project:{project_id}").to_dict()
            project_context["facts"] = facts
            self.save_project_context(project_id, project_context)
        else:
            self._facts[key] = Fact(key=key, value=value, category=category, confidence=confidence)
            self._save_facts()

    def get_fact(self, key: str, project_id: str | None = None) -> Any | None:
        """Get a fact from memory, checking project scope first."""
        if project_id:
            project_context = self.load_project_context(project_id)
            if project_context and "facts" in project_context:
                fact_data = project_context["facts"].get(key)
                if fact_data:
                    return fact_data.get("value")

        fact = self._facts.get(key)
        return fact.value if fact else None

    def get_facts_by_category(self, category: str) -> list[Fact]:
        """Get all facts in a category."""
        return [f for f in self._facts.values() if f.category == category]

    def get_all_facts(self) -> dict[str, Any]:
        """Get all facts as a dictionary."""
        return {key: fact.value for key, fact in self._facts.items()}

    def save_todos(self, todos: list[dict[str, Any]]) -> None:
        """Save todo list."""
        with open(self.todos_file, "w") as f:
            json.dump(todos, f, indent=2)

    def load_todos(self) -> list[dict[str, Any]]:
        """Load todo list."""
        if self.todos_file.exists():
            with open(self.todos_file) as f:
                return json.load(f)
        return []

    def save_project_context(self, project_id: str, context: dict[str, Any]) -> None:
        """Save project-specific context."""
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        path = project_dir / "context.json"
        with open(path, "w") as f:
            json.dump(context, f, indent=2)

    def load_project_context(self, project_id: str) -> dict[str, Any] | None:
        """Load project-specific context."""
        path = self.projects_dir / project_id / "context.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def get_context_summary(self, project_id: str | None = None) -> str:
        """Get a summary of all stored context for injection into prompts."""
        parts = []

        if self._facts:
            parts.append("## User Facts\n")
            for key, fact in sorted(self._facts.items()):
                parts.append(f"- {key}: {fact.value}")

        if project_id:
            project_context = self.load_project_context(project_id)
            if project_context and "facts" in project_context:
                parts.append(f"\n## Project Facts ({project_id})\n")
                for key, fact_data in sorted(project_context["facts"].items()):
                    parts.append(f"- {key}: {fact_data.get('value')}")

        recent_sessions = self.list_sessions(limit=5)
        if recent_sessions:
            parts.append("\n## Recent Sessions\n")
            for session in recent_sessions:
                date = session.created_at.strftime("%Y-%m-%d %H:%M")
                outcome = session.outcome or "in progress"
                parts.append(f"- [{date}] {session.id}: {outcome}")

        return "\n".join(parts) if parts else "(no context stored)"


from .vectors import MemoryEntry, SimpleKeywordBackend, VectorMemory, VectorMemoryBackend

# Global memory instance
_memory: Memory | None = None


def get_memory() -> Memory:
    """Get the global memory instance."""
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory


def reset_memory() -> None:
    """Reset the global memory instance."""
    global _memory
    _memory = None


class ProjectIndexer:
    """Indexes project structure for semantic understanding."""

    IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".ruff_cache"}
    IGNORE_EXTS = {".pyc", ".pyo", ".so", ".egg", ".whl"}

    def __init__(self, memory: Memory | None = None):
        self.memory = memory or get_memory()
        self._index: dict[str, dict[str, Any]] = {}

    def index_project(self, root_path: str | None = None) -> dict[str, Any]:
        """Index a project directory for semantic understanding."""
        import os

        root = root_path or os.getcwd()
        if not os.path.isdir(root):
            return {"error": f"Directory not found: {root}"}

        project_info = {
            "root": root,
            "language": None,
            "files": [],
            "imports": [],
            "structure": {},
        }

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.IGNORE_DIRS]

            for filename in filenames:
                ext = os.path.splitext(filename)[1]
                if ext in self.IGNORE_EXTS:
                    continue

                file_path = os.path.join(dirpath, filename)
                try:
                    if not os.path.exists(file_path): continue
                    file_info = {
                        "path": os.path.relpath(file_path, root),
                        "type": ext.lstrip("."),
                        "size": os.path.getsize(file_path),
                    }
                    project_info["files"].append(file_info)
                except (OSError, FileNotFoundError):
                    continue # Skip inaccessible files

                if ext == ".py":
                    if project_info["language"] is None:
                        project_info["language"] = "python"
                    try:
                        with open(file_path) as f:
                            content = f.read()
                            imports = self._extract_python_imports(content)
                            project_info["imports"].extend(imports)
                    except Exception:
                        pass

        project_info["file_count"] = len(project_info["files"])
        project_info["import_count"] = len(project_info["imports"])

        self._index = project_info
        return project_info

    def _extract_python_imports(self, content: str) -> list[str]:
        """Extract imports from Python file."""
        imports = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(("import ", "from ")):
                imports.append(line)
        return imports

    def get_summary(self) -> str:
        """Get a human-readable project summary."""
        if not self._index:
            return "No project indexed yet."

        parts = []
        if self._index.get("language"):
            parts.append(f"Language: {self._index['language']}")
        if self._index.get("file_count"):
            parts.append(f"Files: {self._index['file_count']}")
        if self._index.get("import_count"):
            parts.append(f"Imports: {self._index['import_count']}")

        return ", ".join(parts) if parts else "Empty project"

    def audit_dependencies(self, root_path: str | None = None) -> dict[str, Any]:
        """Audit project dependencies for security and updates."""
        import json
        import os

        root = root_path or self._index.get("root", os.getcwd())
        audit = {
            "root": root,
            "python": {"file": None, "packages": []},
            "js": {"file": None, "packages": []},
            "security_issues": [],
        }

        pyproject = os.path.join(root, "pyproject.toml")
        if os.path.exists(pyproject):
            audit["python"]["file"] = pyproject
            try:
                import toml
                with open(pyproject) as f:
                    data = toml.loads(f.read())
                    deps = data.get("project", {}).get("dependencies", [])
                    audit["python"]["packages"] = deps
            except Exception:
                pass

        req_txt = os.path.join(root, "requirements.txt")
        if os.path.exists(req_txt):
            audit["python"]["file"] = req_txt
            with open(req_txt) as f:
                audit["python"]["packages"] = [
                    line.strip() for line in f if line.strip() and not line.startswith("#")
                ]

        pkg_json = os.path.join(root, "package.json")
        if os.path.exists(pkg_json):
            audit["js"]["file"] = pkg_json
            try:
                with open(pkg_json) as f:
                    data = json.load(f)
                    deps = data.get("dependencies", {})
                    audit["js"]["packages"] = list(deps.keys())
            except Exception:
                pass

        return audit
