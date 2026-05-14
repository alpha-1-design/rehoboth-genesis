"""Provider manager - handles multiple AI providers with fallback and routing."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import (
    PROVIDER_REGISTRY,
    BaseProvider,
    Message,
    Response,
    StreamChunk,
)


@dataclass
class CostTracker:
    """Track usage costs per provider."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0

    def add_usage(self, usage: dict[str, int], cost_per_million: dict[str, float]) -> None:
        if not usage:
            return
        self.requests += 1
        self.input_tokens += usage.get("prompt_tokens", 0)
        self.output_tokens += usage.get("completion_tokens", 0)

        input_cost = (usage.get("prompt_tokens", 0) / 1_000_000) * cost_per_million.get("input", 0)
        output_cost = (usage.get("completion_tokens", 0) / 1_000_000) * cost_per_million.get("output", 0)
        self.total_cost += input_cost + output_cost


class ProviderManager:
    """Manages multiple AI providers with fallback and routing."""

    def __init__(self):
        self.providers: dict[str, BaseProvider] = {}
        self.configs: dict[str, ProviderConfig] = {}
        self.active_provider: str = "openai"
        self.cost_tracker: CostTracker = CostTracker()

        # Cost per million tokens (approximate)
        self.cost_rates: dict[str, dict[str, float]] = {
            "openai": {"input": 2.5, "output": 10.0},  # GPT-4o
            "anthropic": {"input": 3.0, "output": 15.0},  # Claude 3.5
            "google": {"input": 0.0, "output": 0.0},  # Free tier
            "groq": {"input": 0.0, "output": 0.0},  # Free tier
            "deepseek": {"input": 0.14, "output": 0.28},  # DeepSeek Coder
            "ollama": {"input": 0.0, "output": 0.0},  # Local
            "mistral": {"input": 2.0, "output": 6.0},
        }

    def add_provider(self, config: ProviderConfig) -> None:
        """Add a provider configuration."""
        self.configs[config.name] = config

    def get_provider_config(self, name: str) -> ProviderConfig | None:
        """Get provider configuration by name."""
        return self.configs.get(name)

    def set_active(self, name: str) -> None:
        """Set the active provider."""
        if name not in self.providers:
            config = self.configs.get(name)
            if not config:
                raise ValueError(f"Provider '{name}' not found. Add it first with provider add.")
            self.providers[name] = self._create_provider(config)
        self.active_provider = name

    def _create_provider(self, config: ProviderConfig) -> BaseProvider:
        """Create a provider instance from config."""
        provider_config = {
            "api_key": config.api_key or "",
            "base_url": config.base_url,
            "model": config.model,
            "timeout": config.timeout,
        }
        return PROVIDER_REGISTRY[config.provider_type](provider_config)

    async def get_provider(self, name: str | None = None) -> BaseProvider:
        """Get a provider instance, creating if needed."""
        name = name or self.active_provider

        if name not in self.providers:
            config = self.configs.get(name)
            if not config:
                raise ValueError(f"Provider '{name}' not found")
            self.providers[name] = self._create_provider(config)

        return self.providers[name]

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        provider_name: str | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion with smart fallback support."""
        # Try active first, then fallback to others
        active = provider_name or self.active_provider
        provider_names = [active] + [n for n in self.configs.keys() if n != active]

        last_error = None
        max_retries = 2

        for name in provider_names:
            for attempt in range(max_retries + 1):
                try:
                    provider = await self.get_provider(name)
                    response = await provider.complete(messages, tools, **kwargs)

                    # Track costs
                    if response.usage:
                        rates = self.cost_rates.get(name, {"input": 0, "output": 0})
                        self.cost_tracker.add_usage(response.usage, rates)

                    return response
                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = (attempt + 1) * 2
                        print(f"  \033[34m╼\033[0m \033[90mnexus/providers\033[0m \033[33mNetwork error on {name}, retrying in {wait}s...\033[0m")
                        await asyncio.sleep(wait)
                        continue
                    break  # Exhausted retries for this provider
                except Exception as e:
                    last_error = e
                    cyan = "\033[36m"
                    blue = "\033[34m"
                    dim = "\033[90m"
                    reset = "\033[0m"
                    print(f"  {blue}╼{reset} {dim}nexus/providers{reset} {cyan}{name}{reset} {dim}failed: {e}{reset}")
                    # traceback.print_exc() # Too verbose for regular use
                    print(f"  {blue}╼{reset} {dim}Switching fallback...{reset}")
                    break

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        provider_name: str | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion with smart fallback support."""
        # Disable streaming when tools are needed (OpenCode Zen has issues with streaming tool calls)
        if tools:
            raise RuntimeError("Streaming with tools not supported, use complete() instead")

        active = provider_name or self.active_provider
        provider_names = [active] + [n for n in self.configs.keys() if n != active]

        last_error = None
        for name in provider_names:
            try:
                provider = await self.get_provider(name)
                async for chunk in provider.stream(messages, tools, **kwargs):
                    yield chunk
                return
            except Exception as e:
                last_error = e
                cyan = "\033[36m"
                blue = "\033[34m"
                dim = "\033[90m"
                reset = "\033[0m"
                print(f"  {blue}╼{reset} {dim}nexus/providers{reset} {cyan}{name}{reset} {dim}stream failure. Switching fallback...{reset}")
                continue

        # If we get here, all failed
        raise RuntimeError(f"All providers failed to stream. Last error: {last_error}")

    async def parallel_complete(
        self,
        tasks: list[dict[str, Any]],  # List of {"messages": [], "tools": [], "provider_name": str}
        **kwargs,
    ) -> list[Response | Exception]:
        """Execute multiple completions in parallel using different providers/keys."""

        async def _run_task(task_data: dict[str, Any]) -> Response:
            return await self.complete(messages=task_data["messages"], tools=task_data.get("tools"), provider_name=task_data.get("provider_name"), **kwargs)

        return await asyncio.gather(*[_run_task(t) for t in tasks], return_exceptions=True)

    def get_enabled_providers(self) -> list[str]:
        """Get names of all enabled providers."""
        return [name for name, cfg in self.configs.items() if cfg.enabled]

    async def switch_model(self, model: str, provider_name: str | None = None) -> None:
        """Switch the model for a provider."""
        name = provider_name or self.active_provider
        config = self.configs.get(name)
        if not config:
            raise ValueError(f"Provider '{name}' not found")

        config.model = model

        # Recreate the provider with new model
        if name in self.providers:
            await self.providers[name].close()
            self.providers[name] = self._create_provider(config)

    def get_stats(self) -> dict[str, Any]:
        """Get provider statistics."""
        return {
            "active_provider": self.active_provider,
            "total_requests": self.cost_tracker.requests,
            "total_input_tokens": self.cost_tracker.input_tokens,
            "total_output_tokens": self.cost_tracker.output_tokens,
            "total_cost": self.cost_tracker.total_cost,
            "providers": {
                name: {
                    "model": config.model,
                    "provider_type": config.provider_type,
                    "enabled": config.enabled,
                }
                for name, config in self.configs.items()
            },
        }

    async def close_all(self) -> None:
        """Close all provider connections."""
        for provider in self.providers.values():
            await provider.close()


# Global provider manager instance
_manager: ProviderManager | None = None


def get_manager() -> ProviderManager:
    """Get the global provider manager instance."""
    global _manager
    if _manager is None:
        _manager = ProviderManager()
        _load_config_into_manager(_manager)
    return _manager


def _load_config_into_manager(manager: ProviderManager) -> None:
    """Load provider configurations from config file."""
    try:
        from ..config import load_config

        cfg = load_config()

        for name, prov_config in cfg.providers.items():
            from ..config import ProviderConfig

            manager.configs[name] = ProviderConfig(
                name=prov_config.name,
                provider_type=prov_config.provider_type,
                api_key=prov_config.api_key or "",
                base_url=prov_config.base_url,
                model=prov_config.model,
                max_tokens=prov_config.max_tokens,
                temperature=prov_config.temperature,
                timeout=prov_config.timeout,
                enabled=prov_config.enabled,
            )

        if cfg.active_provider and cfg.active_provider in manager.configs:
            manager.active_provider = cfg.active_provider
    except Exception:
        pass


async def reset_manager() -> None:
    """Reset the global provider manager."""
    global _manager
    if _manager:
        await _manager.close_all()
    _manager = None
