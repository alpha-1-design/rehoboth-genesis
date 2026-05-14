"""REST API for the Nexus dashboard.

Provides HTTP endpoints for the Flask dashboard to interact with:
  - Agent orchestrator
  - Provider manager
  - Tool registry
  - Memory system
  - Skills manager
"""

import asyncio
from dataclasses import asdict
from typing import Any

from ..agent import AgentOrchestrator
from ..config import NexusConfig, load_config
from ..memory import VectorMemory, get_memory
from ..providers import ProviderConfig, ProviderManager, get_manager
from ..skills import SkillsManager
from ..tools import get_registry


def _run_async(coro):
    """Run an async coroutine from a sync context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


class NexusAPI:
    """REST API layer for the Nexus dashboard."""

    def __init__(self):
        self._orchestrator: AgentOrchestrator | None = None
        self._skills_manager: SkillsManager | None = None
        self._vector_memory: VectorMemory | None = None

    def _get_config(self) -> NexusConfig:
        return load_config()

    def _get_pm(self) -> ProviderManager:
        return get_manager()

    def _get_skills(self) -> SkillsManager:
        if self._skills_manager is None:
            self._skills_manager = SkillsManager()
            self._skills_manager.load_all()
        return self._skills_manager

    def _get_vector_memory(self) -> VectorMemory:
        if self._vector_memory is None:
            cfg = self._get_config()
            self._vector_memory = VectorMemory(backend=cfg.search_provider or "keyword")
        return self._vector_memory

    def get_status(self) -> dict[str, Any]:
        """Get overall system status."""
        cfg = self._get_config()
        pm = self._get_pm()
        skills = self._get_skills()
        memory = get_memory()

        return {
            "nexus_version": "0.1.0",
            "config_dir": str(cfg.config_dir),
            "providers": {
                "configured": list(pm.configs.keys()),
                "active": pm.active_provider,
            },
            "skills": {
                "total": len(skills.list_all()),
                "active": skills.list_active(),
                "categories": skills.list_categories(),
            },
            "memory": {
                "facts": len(memory._facts),
                "sessions": len(memory.list_sessions(limit=1)),
            },
            "vector_memory": {
                "entries": _run_async(self._get_vector_memory().count()),
            },
            "system": {
                "python_version": __import__("sys").version.split()[0],
                "platform": __import__("platform").platform(),
            },
            "termux_env": cfg.termux_mode,
        }

    def get_providers(self) -> dict[str, Any]:
        """List all configured providers."""
        pm = self._get_pm()
        return {
            "providers": [
                {
                    "name": name,
                    "type": cfg.provider_type,
                    "model": cfg.model or "default",
                    "base_url": cfg.base_url or "",
                    "active": name == pm.active_provider,
                }
                for name, cfg in pm.configs.items()
            ]
        }

    def add_provider(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add a new provider configuration."""
        pm = self._get_pm()
        cfg = ProviderConfig(
            name=data["name"],
            provider_type=data["provider_type"],
            model=data.get("model"),
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
        )
        pm.add_provider(cfg)
        return {"status": "success", "provider": data["name"]}

    def get_tools(self) -> dict[str, Any]:
        """List all available tools."""
        registry = get_registry()
        tools = registry.list_all()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "requires_permission": t.requires_permission,
                }
                for t in tools
            ]
        }

    def get_skills(self) -> dict[str, Any]:
        """List all available skills."""
        skills = self._get_skills()
        active = skills.list_active()
        return {
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                    "tags": s.tags,
                    "active": s.name in active,
                    "auto_activated": s.name in active,
                }
                for s in skills.list_all()
            ]
        }

    def activate_skill(self, name: str) -> dict[str, Any]:
        """Activate a skill."""
        skills = self._get_skills()
        success = skills.activate(name)
        return {"status": "success" if success else "error", "skill": name}

    def search_memory(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search vector memory."""
        vm = self._get_vector_memory()
        entries = _run_async(vm.recall(query, limit=limit))
        return [
            {
                "id": e.id,
                "content": e.content[:200],
                "metadata": e.metadata,
                "created_at": e.created_at,
                "access_count": e.access_count,
            }
            for e in entries
        ]

    def store_memory(self, content: str, metadata: dict | None = None) -> dict[str, Any]:
        """Store a new memory."""
        vm = self._get_vector_memory()
        entry_id = _run_async(vm.store(content, metadata))
        return {"status": "success", "id": entry_id}

    def get_facts(self) -> dict[str, Any]:
        """Get all stored facts."""
        memory = get_memory()
        return {
            "facts": [asdict(fact) for fact in memory._facts.values()]
        }

    def add_fact(self, key: str, value: Any, category: str = "general") -> dict[str, Any]:
        """Add a fact."""
        memory = get_memory()
        memory.add_fact(key, value, category)
        return {"status": "success", "key": key}

    def list_sessions(self, limit: int = 20) -> dict[str, Any]:
        """List conversation sessions."""
        memory = get_memory()
        return {
            "sessions": [s.to_dict() for s in memory.list_sessions(limit=limit)]
        }

    async def run_agent_task(self, task: str, stream_callback=None) -> dict[str, Any]:
        """Run a task through the agent orchestrator."""
        if self._orchestrator is None:
            pm = self._get_pm()
            registry = get_registry()
            self._orchestrator = AgentOrchestrator(
                provider_manager=pm,
                tool_registry=registry,
                memory=get_memory(),
            )

        turn = await self._orchestrator.run(task, stream_callback=stream_callback)
        return {
            "message": turn.assistant_message,
            "tool_calls": len(turn.tool_calls),
            "duration_ms": turn.duration_ms,
            "error": turn.error,
        }

    def get_agent_stats(self) -> dict[str, Any]:
        """Get agent session stats."""
        if self._orchestrator is None:
            return {"turns": 0, "tool_calls": 0, "history": []}
        return {
            "turns": self._orchestrator.turn_count,
            "tool_calls": self._orchestrator.tool_call_count,
            "history": [
                {
                    "user": t.user_message[:100],
                    "assistant": t.assistant_message[:100] if t.assistant_message else "",
                    "tool_calls": len(t.tool_calls),
                    "error": t.error,
                }
                for t in self._orchestrator.get_history()
            ],
        }

    def get_automation_status(self) -> dict[str, Any]:
        """Get browser/API automation status."""
        try:
            from ..automation.browser import BrowserManager, is_browser_available
            browser_available = is_browser_available()
            has_session = BrowserManager.get() is not None
        except Exception:
            browser_available = False
            has_session = False

        try:
            import httpx
            httpx_available = True
        except ImportError:
            httpx_available = False

        registry = get_registry()
        tools = registry.list_all()
        browser_tools = [t for t in tools if t.category == "automation"]
        automation_tool_names = [t.name for t in browser_tools]

        return {
            "playwright_available": browser_available,
            "browser_session_active": has_session,
            "httpx_available": httpx_available,
            "automation_tools": automation_tool_names,
            "tool_count": len(automation_tool_names),
            "anti_detection": {
                "stealth_scripts": 10,
                "user_agent_rotation": True,
                "captcha_detection": True,
                "human_like_behavior": True,
            },
        }

    def run_automation_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an automation tool from the dashboard."""
        registry = get_registry()
        tool = registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        if tool.category != "automation":
            return {"success": False, "error": f"Tool '{tool_name}' is not an automation tool"}
        try:
            result = _run_async(tool.execute(**params))
            return {"success": result.success, "content": result.content, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}


_api: NexusAPI | None = None


def get_api() -> NexusAPI:
    """Get the global API instance."""
    global _api
    if _api is None:
        _api = NexusAPI()
    return _api
