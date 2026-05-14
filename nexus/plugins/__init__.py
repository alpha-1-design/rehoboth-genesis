"""Plugin system for Nexus.

Plugins can hook into: tools, providers, lifecycle events.
Drop-in structure: ~/.nexus/plugins/<name>/plugin.yaml + __init__.py
"""

import importlib
import importlib.util
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PluginHook(Enum):
    ON_TOOL_CALL = auto()
    ON_TOOL_RESULT = auto()
    ON_MESSAGE = auto()
    ON_RESPONSE = auto()
    ON_AGENT_SPAWN = auto()
    ON_PROVIDER_ERROR = auto()
    ON_SESSION_START = auto()
    ON_SESSION_END = auto()
    REGISTER_TOOL = auto()
    REGISTER_PROVIDER = auto()
    ON_STARTUP = auto()
    ON_SHUTDOWN = auto()


@dataclass
class PluginMetadata:
    name: str
    version: str
    description: str = ""
    author: str = ""
    hooks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    min_nexus_version: str = "0.1.0"


@dataclass
class Plugin:
    metadata: PluginMetadata
    instance: Any = None
    enabled: bool = True
    error: str | None = None


class PluginBase:
    name: str = "unnamed-plugin"
    version: str = "1.0.0"
    description: str = ""
    hooks: list[PluginHook] = []

    def on_tool_call(self, tool_name: str, args: dict, ctx: dict) -> dict:
        return args

    def on_tool_result(self, tool_name: str, result: Any, ctx: dict) -> Any:
        return result

    def on_message(self, message: str, ctx: dict) -> str:
        return message

    def on_response(self, content: str, ctx: dict) -> str:
        return content

    def on_agent_spawn(self, agent_config: dict, ctx: dict) -> dict:
        return agent_config

    def on_provider_error(self, provider_name: str, error: Exception, ctx: dict) -> tuple[bool, Any]:
        return False, None

    def on_session_start(self, session_id: str, ctx: dict) -> None:
        pass

    def on_session_end(self, session_id: str, summary: dict, ctx: dict) -> None:
        pass

    def on_startup(self) -> None:
        pass

    def on_shutdown(self) -> None:
        pass


class PluginManager:
    def __init__(self, plugins_dir: Path | None = None):
        self.plugins_dir = plugins_dir or (Path.home() / ".nexus" / "plugins")
        self._plugins: dict[str, Plugin] = {}
        self._hooks: dict[PluginHook, list[tuple[str, Callable]]] = {h: [] for h in PluginHook}
        self._enabled: dict[str, bool] = {}

    def discover(self) -> list[Plugin]:
        plugins = []
        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return plugins

        for item in self.plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                plugin = self._load_plugin(item)
                if plugin:
                    plugins.append(plugin)
        return plugins

    def _load_plugin(self, plugin_dir: Path) -> Plugin | None:
        metadata_file = plugin_dir / "plugin.yaml"
        init_file = plugin_dir / "__init__.py"

        if not metadata_file.exists():
            return None

        try:
            metadata_data = yaml.safe_load(metadata_file.read_text()) or {}
        except Exception as e:
            logger.error(f"Plugin {plugin_dir.name}: {e}")
            return None

        metadata = PluginMetadata(
            name=metadata_data.get("name", plugin_dir.name),
            version=metadata_data.get("version", "1.0.0"),
            description=metadata_data.get("description", ""),
            author=metadata_data.get("author", ""),
            hooks=[h.strip() for h in metadata_data.get("hooks", [])],
            dependencies=metadata_data.get("dependencies", []),
            min_nexus_version=metadata_data.get("min_nexus_version", "0.1.0"),
        )

        instance = None
        error = None

        if init_file.exists():
            try:
                spec = importlib.util.spec_from_file_location(f"nexus_plugin_{plugin_dir.name}", init_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                            instance = attr()
                            break
                    if not instance:
                        instance = module
            except Exception as e:
                error = str(e)
                logger.error(f"Plugin {plugin_dir.name}: {e}")

        plugin = Plugin(metadata=metadata, instance=instance, error=error)
        self._plugins[metadata.name] = plugin
        self._enabled[metadata.name] = True

        if instance:
            for hook_name in metadata.hooks:
                try:
                    hook = PluginHook[hook_name.upper()]
                    method_name = hook.name.lower()
                    if hasattr(instance, method_name):
                        self._hooks[hook].append((metadata.name, getattr(instance, method_name)))
                except KeyError:
                    pass

        logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")
        return plugin

    def enable(self, name: str) -> bool:
        if name in self._plugins:
            self._enabled[name] = True
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self._plugins:
            self._enabled[name] = False
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)

    def list_all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def list_enabled(self) -> list[Plugin]:
        return [p for p in self._plugins.values() if self._enabled.get(p.metadata.name)]

    def call_tool_hooks(self, tool_name: str, args: dict, ctx: dict) -> dict:
        for plugin_name, callback in self._hooks.get(PluginHook.ON_TOOL_CALL, []):
            if not self._enabled.get(plugin_name):
                continue
            try:
                args = callback(tool_name, args, ctx) or args
            except Exception as e:
                logger.error(f"Plugin {plugin_name} ON_TOOL_CALL failed: {e}")
        return args

    def call_result_hooks(self, tool_name: str, result: Any, ctx: dict) -> Any:
        for plugin_name, callback in self._hooks.get(PluginHook.ON_TOOL_RESULT, []):
            if not self._enabled.get(plugin_name):
                continue
            try:
                result = callback(tool_name, result, ctx) or result
            except Exception as e:
                logger.error(f"Plugin {plugin_name} ON_TOOL_RESULT failed: {e}")
        return result

    def on_startup(self) -> None:
        for p in self.list_enabled():
            if hasattr(p.instance, "on_startup"):
                try:
                    p.instance.on_startup()
                except Exception as e:
                    logger.error(f"Plugin {p.metadata.name} ON_STARTUP failed: {e}")

    def on_shutdown(self) -> None:
        for p in self.list_enabled():
            if hasattr(p.instance, "on_shutdown"):
                try:
                    p.instance.on_shutdown()
                except Exception as e:
                    logger.error(f"Plugin {p.metadata.name} ON_SHUTDOWN failed: {e}")


_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        from ..config import load_config

        cfg = load_config()
        _plugin_manager = PluginManager(plugins_dir=cfg.plugins_dir)
        _plugin_manager.discover()
    return _plugin_manager
