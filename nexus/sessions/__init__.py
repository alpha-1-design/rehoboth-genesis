"""Session auto-load and memory persistence for Nexus.

On startup: loads the most recent session's context
On tool execution: auto-saves session (crash-safe)
On project change: switches project context automatically
"""

import asyncio
import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..memory import Memory, Session, get_memory


class SessionAutoLoader:
    """
    Handles automatic session loading and persistence.
    
    On Nexus start:
    1. Find the most recent session
    2. Load its context summary
    3. Ask user if they want to continue
    4. Load full session messages if continuing
    
    On exit: auto-save current session
    On crash: sessions are saved incrementally (not just on exit)
    """

    def __init__(self, memory: Memory | None = None):
        self.memory = memory or get_memory()
        self.sessions_dir = self.memory.memory_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._auto_save_interval = 30  # seconds
        self._auto_save_task: asyncio.Task | None = None
        self._last_save_time = datetime.now()

    def get_most_recent_session(self) -> Session | None:
        """Get the most recent session."""
        sessions = self.memory.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def list_recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent sessions with metadata."""
        sessions = self.memory.list_sessions(limit=limit)
        result = []
        for s in sessions:
            result.append({
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                "message_count": len(s.messages),
                "tools_used": len(s.tools_used),
                "outcome": s.outcome or "in progress",
                "preview": s.messages[-1]["content"][:80] if s.messages else "",
            })
        return result

    def save_session(self, session: Session, crash_safe: bool = True) -> str:
        """
        Save session to disk. If crash_safe=True, writes to temp then renames.
        Returns the saved file path.
        """
        filepath = self.sessions_dir / f"{session.id}.json"
        temp_filepath = self.sessions_dir / f"{session.id}.tmp"

        data = asdict(session)
        # Convert datetime objects to strings
        if data.get("created_at"):
            data["created_at"] = str(session.created_at)
        if data.get("updated_at"):
            data["updated_at"] = str(session.updated_at)

        if crash_safe:
            temp_filepath.write_text(json.dumps(data, indent=2))
            temp_filepath.rename(filepath)
        else:
            filepath.write_text(json.dumps(data, indent=2))

        self._last_save_time = datetime.now()
        return str(filepath)

    def load_session(self, session_id: str) -> Session | None:
        """Load a session from disk by ID."""
        filepath = self.sessions_dir / f"{session_id}.json"
        if not filepath.exists():
            return None

        try:
            data = json.loads(filepath.read_text())
            # Parse datetime strings back
            if data.get("created_at"):
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            if data.get("updated_at"):
                data["updated_at"] = datetime.fromisoformat(data["updated_at"])
            return Session(**data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from disk."""
        filepath = self.sessions_dir / f"{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def start_auto_save(self, session: Session) -> None:
        """Start background auto-save task."""
        if self._auto_save_task and not self._auto_save_task.done():
            return

        async def _auto_save_loop():
            while True:
                await asyncio.sleep(self._auto_save_interval)
                try:
                    session.updated_at = datetime.now()
                    self.save_session(session)
                except Exception:
                    pass

        self._auto_save_task = asyncio.create_task(_auto_save_loop())

    def stop_auto_save(self) -> None:
        """Stop background auto-save task."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None

    def format_session_list(self, limit: int = 10) -> str:
        """Format session list for display."""
        sessions = self.list_recent_sessions(limit=limit)
        if not sessions:
            return "No sessions found."

        lines = ["\nRecent Sessions:"]
        for i, s in enumerate(sessions, 1):
            date = s.get("created_at", "")[:10] if s.get("created_at") else "?"
            outcome = s.get("outcome", "unknown")[:40]
            msgs = s.get("message_count", 0)
            tools = s.get("tools_used", 0)
            preview = s.get("preview", "")
            lines.append(f"  [{i}] {s['id'][:8]} ({date})")
            lines.append(f"      {msgs} msgs, {tools} tools — {outcome}")
            if preview:
                lines.append(f"      \"{preview}...\"")

        return "\n".join(lines)

    def get_resume_prompt(self, session: Session) -> str:
        """Build a prompt asking if user wants to resume session."""
        msg_count = len(session.messages)
        tool_count = len(session.tools_used)
        last_msg = session.messages[-1]["content"][:100] if session.messages else ""
        date = session.updated_at.strftime("%Y-%m-%d %H:%M") if session.updated_at else "unknown"

        return f"""
╔══════════════════════════════════════════════════════════╗
║  Session Resume                                          ║
╠══════════════════════════════════════════════════════════╣
║  Session: {session.id[:16]}                          ║
║  Last active: {date}                         ║
║  Messages: {msg_count}  │  Tools used: {tool_count}                     ║
║  Last message: "{last_msg}..."                   ║
╚══════════════════════════════════════════════════════════╝

Continue from last session? (y/n): """


class ProjectContext:
    """
    Per-project context that auto-switches when the working directory changes.
    
    Project context files live at: <project_root>/.nexus/context.json
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.context_file = self.project_root / ".nexus" / "context.json"
        self._context: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        """Load context from project .nexus/context.json."""
        if self.context_file.exists():
            try:
                self._context = json.loads(self.context_file.read_text())
            except (OSError, json.JSONDecodeError):
                self._context = {}
        return self._context

    def save(self) -> None:
        """Save context to project .nexus/context.json."""
        self.context_file.parent.mkdir(parents=True, exist_ok=True)
        self.context_file.write_text(json.dumps(self._context, indent=2))

    def get(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._context[key] = value
        self.save()

    def delete(self, key: str) -> None:
        if key in self._context:
            del self._context[key]
            self.save()

    def detect_project(self, path: Path | None = None) -> str | None:
        """Walk up from path to find a project marker."""
        search = path or Path.cwd()
        markers = [
            ".git", "pyproject.toml", "package.json", "Cargo.toml",
            "go.mod", "Makefile", ".nexus", "requirements.txt",
            "setup.py", ".codeclimate", "package-lock.json",
        ]
        while search != search.parent:
            for marker in markers:
                if (search / marker).exists():
                    return str(search)
            search = search.parent
        return None

    def format_context(self) -> str:
        """Format context as a readable string."""
        if not self._context:
            return "(no project context)"
        lines = ["## Project Context"]
        for key, value in self._context.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)


# Global singletons
_session_loader: SessionAutoLoader | None = None


def get_session_loader() -> SessionAutoLoader:
    global _session_loader
    if _session_loader is None:
        _session_loader = SessionAutoLoader()
    return _session_loader
