"""Sync Engine — cross-device sync, team collaboration, and external service integration.

Supports:
  - GitHub Gist-based sync (works anywhere with a GitHub token)
  - Local file sync (for USB/hotspot transfers)
  - Git remote sync (push/pull sessions to git repos)
  - External service connectors (GitHub, GitLab, Vercel, Slack)
  - WebSocket-based real-time team sync (same network)
  - Session diff & merge (conflict resolution)

Usage:
  /sync status          — show sync status
  /sync push            — push to remote
  /sync pull            — pull from remote
  /sync connect <type>  — connect external service
"""

import asyncio
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SyncTarget(Enum):
    LOCAL = auto()        # Local file system / USB
    GITHUB_GIST = auto()  # GitHub Gist (cross-device via GitHub)
    GIT_REMOTE = auto()   # Git repository (enterprise)
    WEBRTC = auto()       # Real-time same-network sync
    CLOUD = auto()        # Generic cloud (future: S3, GCS)


class SyncStatus(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    SYNCED = auto()
    PENDING = auto()
    CONFLICT = auto()
    ERROR = auto()


@dataclass
class SyncEndpoint:
    """A sync destination."""
    name: str
    target: SyncTarget
    url: str | None = None
    token: str | None = None
    path: Path | None = None
    auto_sync: bool = False
    sync_interval: int = 60  # seconds
    last_sync: datetime | None = None
    status: SyncStatus = SyncStatus.DISCONNECTED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target.name,
            "url": self.url,
            "path": str(self.path) if self.path else None,
            "auto_sync": self.auto_sync,
            "sync_interval": self.sync_interval,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "status": self.status.name,
        }


@dataclass
class SyncItem:
    """An item to be synced."""
    path: Path
    hash: str = ""
    size: int = 0
    modified: datetime = field(default_factory=datetime.now)
    action: str = "push"  # push, pull, conflict
    session_id: str = ""


class SyncEngine:
    """
    Manages sync across devices and external services.
    
    Default sync strategy:
      - Sessions synced to GitHub Gist (with GitHub token)
      - Config synced locally (~/.nexus/sync/)
      - Conflict resolution: newest wins + manual review
    """

    SYNC_DIR = Path.home() / ".nexus" / "sync"
    SESSIONS_DIR = SYNC_DIR / "sessions"
    CONFIG_FILE = SYNC_DIR / "sync.json"
    ENDPOINTS_FILE = SYNC_DIR / "endpoints.json"

    def __init__(self, nexus_dir: Path | None = None):
        self.nexus_dir = nexus_dir or Path.home() / ".nexus"
        self.sync_dir = self.SYNC_DIR
        self.sessions_dir = self.SESSIONS_DIR
        self.sync_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.endpoints: dict[str, SyncEndpoint] = {}
        self._sync_tasks: dict[str, asyncio.Task] = {}
        self._listeners: list[callable] = []
        self._last_manifest: dict[str, str] = {}
        self._load_endpoints()

    def _load_endpoints(self) -> None:
        """Load saved endpoints."""
        if self.ENDPOINTS_FILE.exists():
            try:
                data = json.loads(self.ENDPOINTS_FILE.read_text())
                for name, ep_data in data.items():
                    ep_data["target"] = SyncTarget[ep_data["target"]]
                    if ep_data.get("path"):
                        ep_data["path"] = Path(ep_data["path"])
                    if ep_data.get("last_sync"):
                        ep_data["last_sync"] = datetime.fromisoformat(ep_data["last_sync"])
                    if ep_data.get("status"):
                        ep_data["status"] = SyncStatus[ep_data["status"]]
                    self.endpoints[name] = SyncEndpoint(**ep_data)
            except Exception as e:
                logger.error(f"Failed to load endpoints: {e}")

    def _save_endpoints(self) -> None:
        """Save endpoints to disk."""
        data = {name: ep.to_dict() for name, ep in self.endpoints.items()}
        self.ENDPOINTS_FILE.write_text(json.dumps(data, indent=2))

    def connect(self, endpoint: SyncEndpoint) -> bool:
        """Connect to a sync endpoint."""
        self.endpoints[endpoint.name] = endpoint
        self._save_endpoints()

        if endpoint.target == SyncTarget.GITHUB_GIST:
            return self._test_github_gist(endpoint)
        elif endpoint.target == SyncTarget.LOCAL:
            return self._test_local(endpoint)
        elif endpoint.target == SyncTarget.GIT_REMOTE:
            return self._test_git_remote(endpoint)

        return True

    def _test_github_gist(self, endpoint: SyncEndpoint) -> bool:
        """Test GitHub Gist connectivity."""
        if not endpoint.token:
            logger.warning("No GitHub token for Gist sync")
            return False
        try:
            import httpx
            resp = httpx.get(
                "https://api.github.com/gists",
                headers={"Authorization": f"token {endpoint.token}", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            endpoint.status = SyncStatus.SYNCED if resp.status_code == 200 else SyncStatus.ERROR
            return resp.status_code == 200
        except Exception as e:
            endpoint.status = SyncStatus.ERROR
            logger.error(f"Gist connection failed: {e}")
            return False

    def _test_local(self, endpoint: SyncEndpoint) -> bool:
        """Test local/USB sync path."""
        if endpoint.path:
            endpoint.path.mkdir(parents=True, exist_ok=True)
            test_file = endpoint.path / ".nexus_sync_test"
            try:
                test_file.write_text("ok")
                test_file.unlink()
                endpoint.status = SyncStatus.SYNCED
                return True
            except Exception:
                endpoint.status = SyncStatus.ERROR
                return False
        return False

    def _test_git_remote(self, endpoint: SyncEndpoint) -> bool:
        """Test git remote connectivity."""
        if endpoint.path:
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "ls-remote", str(endpoint.path)],
                    capture_output=True, timeout=10,
                )
                endpoint.status = SyncStatus.SYNCED if result.returncode == 0 else SyncStatus.ERROR
                return result.returncode == 0
            except Exception:
                endpoint.status = SyncStatus.ERROR
                return False
        return False

    def disconnect(self, name: str) -> bool:
        """Disconnect an endpoint."""
        if name in self.endpoints:
            del self.endpoints[name]
            self._save_endpoints()
            return True
        return False

    def push(self, endpoint_name: str, session_id: str | None = None) -> dict[str, Any]:
        """
        Push sessions/config to an endpoint.
        Returns sync result.
        """
        endpoint = self.endpoints.get(endpoint_name)
        if not endpoint:
            return {"success": False, "error": f"Endpoint '{endpoint_name}' not found"}

        if endpoint.target == SyncTarget.GITHUB_GIST:
            return self._push_to_gist(endpoint, session_id)
        elif endpoint.target == SyncTarget.LOCAL:
            return self._push_to_local(endpoint, session_id)
        elif endpoint.target == SyncTarget.GIT_REMOTE:
            return self._push_to_git(endpoint, session_id)

        return {"success": False, "error": "Unsupported target"}

    def pull(self, endpoint_name: str, session_id: str | None = None) -> dict[str, Any]:
        """
        Pull sessions/config from an endpoint.
        Returns sync result with items pulled.
        """
        endpoint = self.endpoints.get(endpoint_name)
        if not endpoint:
            return {"success": False, "error": f"Endpoint '{endpoint_name}' not found"}

        if endpoint.target == SyncTarget.GITHUB_GIST:
            return self._pull_from_gist(endpoint, session_id)
        elif endpoint.target == SyncTarget.LOCAL:
            return self._pull_from_local(endpoint, session_id)
        elif endpoint.target == SyncTarget.GIT_REMOTE:
            return self._pull_from_git(endpoint, session_id)

        return {"success": False, "error": "Unsupported target"}

    def _push_to_gist(self, endpoint: SyncEndpoint, session_id: str | None = None) -> dict[str, Any]:
        """Push sessions to GitHub Gist."""
        import httpx

        files = {}

        # Package sessions
        sessions_path = Path.home() / ".nexus" / "memory" / "sessions"
        if sessions_path.exists():
            for f in sessions_path.glob("*.json"):
                if session_id and session_id not in f.name:
                    continue
                files[f"session_{f.stem}.json"] = {"content": f.read_text()}

        # Package config
        config_path = Path.home() / ".nexus" / "config.json"
        if config_path.exists():
            files["config.json"] = {"content": config_path.read_text()}

        # Package facts
        facts_path = Path.home() / ".nexus" / "memory" / "facts.json"
        if facts_path.exists():
            files["facts.json"] = {"content": facts_path.read_text()}

        if not files:
            return {"success": True, "message": "Nothing to push", "items": 0}

        gist_name = endpoint.metadata.get("gist_name", "nexus-sessions")

        try:
            # Try to update existing gist
            gist_id = endpoint.metadata.get("gist_id")
            if gist_id:
                resp = httpx.patch(
                    f"https://api.github.com/gists/{gist_id}",
                    headers={"Authorization": f"token {endpoint.token}", "Accept": "application/vnd.github+json"},
                    json={"files": files, "description": f"Nexus sync - {datetime.now().date()}"},
                    timeout=30,
                )
            else:
                resp = httpx.post(
                    "https://api.github.com/gists",
                    headers={"Authorization": f"token {endpoint.token}", "Accept": "application/vnd.github+json"},
                    json={"files": files, "description": f"Nexus sessions - {datetime.now().date()}", "public": False},
                    timeout=30,
                )

            if resp.status_code in (200, 201):
                data = resp.json()
                endpoint.metadata["gist_id"] = data.get("id")
                endpoint.last_sync = datetime.now()
                self._save_endpoints()
                return {"success": True, "items": len(files), "gist_url": data.get("html_url")}
            else:
                return {"success": False, "error": f"GitHub API error: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _pull_from_gist(self, endpoint: SyncEndpoint, session_id: str | None = None) -> dict[str, Any]:
        """Pull sessions from GitHub Gist."""
        import httpx

        gist_id = endpoint.metadata.get("gist_id")
        if not gist_id:
            return {"success": False, "error": "No Gist ID configured. Push first."}

        try:
            resp = httpx.get(
                f"https://api.github.com/gists/{gist_id}",
                headers={"Authorization": f"token {endpoint.token}", "Accept": "application/vnd.github+json"},
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                pulled = 0
                conflicts = []

                for filename, file_data in data["files"].items():
                    content = file_data["content"]

                    if filename.startswith("session_") and filename.endswith(".json"):
                        dest_name = filename.replace("session_", "").replace(".json", "")
                        dest_path = self.sessions_dir / f"{dest_name}.json"

                        if session_id and session_id not in dest_name:
                            continue

                        # Check for conflict
                        if dest_path.exists():
                            local_hash = hashlib.md5(dest_path.read_bytes()).hexdigest()
                            remote_hash = hashlib.md5(content.encode()).hexdigest()
                            if local_hash != remote_hash:
                                conflicts.append(str(dest_path))
                                # Backup local
                                backup_path = dest_path.with_suffix(".conflict.json")
                                shutil.copy2(dest_path, backup_path)

                        dest_path.write_text(content)
                        pulled += 1

                    elif filename == "config.json":
                        dest = Path.home() / ".nexus" / "config.json"
                        dest.write_text(content)
                        pulled += 1

                    elif filename == "facts.json":
                        dest = Path.home() / ".nexus" / "memory" / "facts.json"
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(content)
                        pulled += 1

                endpoint.last_sync = datetime.now()
                self._save_endpoints()
                return {
                    "success": True,
                    "items": pulled,
                    "conflicts": conflicts,
                    "message": f"Pulled {pulled} items" + (f", {len(conflicts)} conflicts" if conflicts else "")
                }
            else:
                return {"success": False, "error": f"GitHub API error: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _push_to_local(self, endpoint: SyncEndpoint, session_id: str | None = None) -> dict[str, Any]:
        """Push to local path (USB, shared drive)."""
        if not endpoint.path:
            return {"success": False, "error": "No path configured"}

        endpoint.path.mkdir(parents=True, exist_ok=True)
        pushed = 0

        sessions_path = Path.home() / ".nexus" / "memory" / "sessions"
        if sessions_path.exists():
            for f in sessions_path.glob("*.json"):
                if session_id and session_id not in f.name:
                    continue
                dest = endpoint.path / f.name
                shutil.copy2(f, dest)
                pushed += 1

        config_path = Path.home() / ".nexus" / "config.json"
        if config_path.exists():
            shutil.copy2(config_path, endpoint.path / "config.json")
            pushed += 1

        endpoint.last_sync = datetime.now()
        self._save_endpoints()
        return {"success": True, "items": pushed}

    def _pull_from_local(self, endpoint: SyncEndpoint, session_id: str | None = None) -> dict[str, Any]:
        """Pull from local path."""
        if not endpoint.path or not endpoint.path.exists():
            return {"success": False, "error": "Path does not exist"}

        pulled = 0
        conflicts = []

        for f in endpoint.path.glob("session_*.json"):
            if session_id and session_id not in f.stem:
                continue
            dest = self.sessions_dir / f.name
            if dest.exists():
                if dest.read_bytes() != f.read_bytes():
                    conflicts.append(str(dest))
                    shutil.copy2(dest, dest.with_suffix(".conflict.json"))
            shutil.copy2(f, dest)
            pulled += 1

        endpoint.last_sync = datetime.now()
        self._save_endpoints()
        return {"success": True, "items": pulled, "conflicts": conflicts}

    def _push_to_git(self, endpoint: SyncEndpoint, session_id: str | None = None) -> dict[str, Any]:
        """Push to a git remote repository."""
        import subprocess

        if not endpoint.path:
            return {"success": False, "error": "No git path configured"}

        repo_path = endpoint.path
        work_dir = repo_path / "nexus-sessions"

        try:
            # Init or clone
            if not work_dir.exists():
                if (repo_path / ".git").exists():
                    subprocess.run(["git", "clone", str(repo_path), str(work_dir)],
                                  capture_output=True, check=True)
            else:
                subprocess.run(["git", "-C", str(work_dir), "pull"],
                              capture_output=True, check=True)

            # Copy sessions
            sessions_path = Path.home() / ".nexus" / "memory" / "sessions"
            if sessions_path.exists():
                for f in sessions_path.glob("*.json"):
                    if session_id and session_id not in f.name:
                        continue
                    shutil.copy2(f, work_dir / f.name)

            # Commit and push
            subprocess.run(["git", "-C", str(work_dir), "add", "."], check=True)
            subprocess.run(["git", "-C", str(work_dir), "commit", "-m",
                          f"Nexus sync {datetime.now().isoformat()}"], check=True)
            subprocess.run(["git", "-C", str(work_dir), "push"], check=True)

            endpoint.last_sync = datetime.now()
            self._save_endpoints()
            return {"success": True, "items": len(list(sessions_path.glob("*.json")) if sessions_path.exists() else [])}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Git error: {e.stderr}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _pull_from_git(self, endpoint: SyncEndpoint, session_id: str | None = None) -> dict[str, Any]:
        """Pull from a git remote repository."""
        import subprocess

        if not endpoint.path:
            return {"success": False, "error": "No git path configured"}

        work_dir = endpoint.path / "nexus-sessions"
        try:
            if work_dir.exists():
                subprocess.run(["git", "-C", str(work_dir), "pull"], check=True)
                # Copy to local sessions
                for f in work_dir.glob("session_*.json"):
                    if session_id and session_id not in f.stem:
                        continue
                    shutil.copy2(f, self.sessions_dir / f.name)

                endpoint.last_sync = datetime.now()
                self._save_endpoints()
                return {"success": True, "items": len(list(work_dir.glob("session_*.json")))}
            return {"success": False, "error": "No sync directory found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_auto_sync(self, endpoint_name: str) -> None:
        """Start automatic background sync for an endpoint."""
        endpoint = self.endpoints.get(endpoint_name)
        if not endpoint or endpoint_name in self._sync_tasks:
            return

        async def _auto_sync_loop():
            while True:
                await asyncio.sleep(endpoint.sync_interval)
                try:
                    self.push(endpoint_name)
                    self._notify_listeners("sync", endpoint_name, "pushed")
                except Exception as e:
                    logger.error(f"Auto-sync failed: {e}")

        task = asyncio.create_task(_auto_sync_loop())
        self._sync_tasks[endpoint_name] = task
        endpoint.auto_sync = True
        self._save_endpoints()

    def stop_auto_sync(self, endpoint_name: str) -> None:
        """Stop automatic sync."""
        if endpoint_name in self._sync_tasks:
            self._sync_tasks[endpoint_name].cancel()
            del self._sync_tasks[endpoint_name]
        if endpoint_name in self.endpoints:
            self.endpoints[endpoint_name].auto_sync = False
            self._save_endpoints()

    def add_listener(self, callback: callable) -> None:
        """Add a listener for sync events."""
        self._listeners.append(callback)

    def _notify_listeners(self, event: str, *args) -> None:
        for listener in self._listeners:
            try:
                listener(event, *args)
            except Exception:
                pass

    def get_status(self, endpoint_name: str | None = None) -> dict[str, Any]:
        """Get sync status."""
        if endpoint_name:
            ep = self.endpoints.get(endpoint_name)
            if not ep:
                return {"error": "Endpoint not found"}
            return ep.to_dict()

        return {
            "endpoints": {name: ep.to_dict() for name, ep in self.endpoints.items()},
            "auto_sync_active": list(self._sync_tasks.keys()),
        }

    def format_status(self) -> str:
        """Format sync status for display."""
        lines = ["\n=== Sync Status ==="]

        if not self.endpoints:
            lines.append("  No endpoints configured.")
            lines.append("  Connect: /sync connect github-gist|local|git")
            return "\n".join(lines)

        for name, ep in self.endpoints.items():
            status_icon = "●" if ep.status == SyncStatus.SYNCED else "○"
            auto_icon = "⟳" if ep.auto_sync else " "
            last = ep.last_sync.strftime("%Y-%m-%d %H:%M") if ep.last_sync else "never"
            lines.append(f"  {status_icon} {name} ({ep.target.name})")
            lines.append(f"      Status: {ep.status.name}  Last: {last}  Auto: {auto_icon}")
            if ep.url:
                lines.append(f"      URL: {ep.url}")
            if ep.path:
                lines.append(f"      Path: {ep.path}")

        return "\n".join(lines)


# External Service Connectors
class ExternalServiceConnector:
    """Base class for external service integrations."""

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config
        self.connected = False

    async def test_connection(self) -> bool:
        raise NotImplementedError

    async def push_session(self, session_data: dict) -> dict:
        raise NotImplementedError

    async def pull_sessions(self) -> list[dict]:
        raise NotImplementedError

    async def notify(self, message: str, context: dict | None = None) -> None:
        raise NotImplementedError


class GitHubConnector(ExternalServiceConnector):
    """Connect to GitHub for repo operations and notifications."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("github", config)
        self.token = config.get("token", "")
        self.owner = config.get("owner", "")
        self.repo = config.get("repo", "")

    async def test_connection(self) -> bool:
        import httpx
        try:
            resp = httpx.get(
                f"https://api.github.com/repos/{self.owner}/{self.repo}",
                headers={"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            self.connected = False
            return False

    async def push_session(self, session_data: dict) -> dict:
        import httpx
        try:
            resp = httpx.post(
                f"https://api.github.com/repos/{self.owner}/{self.repo}/dispatches",
                headers={"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"},
                json={"event_type": "nexus-session", "client_payload": session_data},
                timeout=15,
            )
            return {"success": resp.status_code == 204, "status": resp.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def notify(self, message: str, context: dict | None = None) -> None:
        import httpx
        try:
            body = {"body": f"[Nexus] {message}"}
            if context:
                body["body"] += f"\n\n```json\n{json.dumps(context, indent=2)}\n```"
            httpx.post(
                f"https://api.github.com/repos/{self.owner}/{self.repo}/issues",
                headers={"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"},
                json=body,
                timeout=10,
            )
        except Exception:
            pass


class SlackConnector(ExternalServiceConnector):
    """Connect to Slack for team notifications."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("slack", config)
        self.webhook_url = config.get("webhook_url", "")

    async def test_connection(self) -> bool:
        import httpx
        try:
            resp = httpx.post(self.webhook_url, json={"text": "Nexus connected ✓"}, timeout=10)
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            self.connected = False
            return False

    async def notify(self, message: str, context: dict | None = None) -> None:
        import httpx
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*[Nexus]*\n{message}"}}]
        if context:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"```json\n{json.dumps(context, indent=2)[:500]}\n```"}})
        try:
            httpx.post(self.webhook_url, json={"blocks": blocks}, timeout=10)
        except Exception:
            pass


class VercelConnector(ExternalServiceConnector):
    """Connect to Vercel for deployment and status."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("vercel", config)
        self.token = config.get("token", "")
        self.team_id = config.get("team_id", "")

    async def test_connection(self) -> bool:
        import httpx
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = httpx.get("https://api.vercel.com/v2/deployments", headers=headers, timeout=10)
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            self.connected = False
            return False

    async def deploy(self, project_path: str, options: dict | None = None) -> dict:
        import httpx
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {"name": options.get("name", "nexus-deploy") if options else "nexus-deploy"}
        try:
            resp = httpx.post("https://api.vercel.com/v13/deployments", headers=headers, json=payload, timeout=30)
            return {"success": resp.status_code in (200, 201), "data": resp.json() if resp.status_code in (200, 201) else None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def notify(self, message: str, context: dict | None = None) -> None:
        pass  # Vercel is push-only


CONNECTOR_REGISTRY: dict[str, type[ExternalServiceConnector]] = {
    "github": GitHubConnector,
    "slack": SlackConnector,
    "vercel": VercelConnector,
}


# Global singleton
_sync_engine: SyncEngine | None = None


def get_sync_engine() -> SyncEngine:
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = SyncEngine()
    return _sync_engine
