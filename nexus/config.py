"""Configuration management for Nexus."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".nexus"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_MEMORY_DIR = DEFAULT_CONFIG_DIR / "memory"
DEFAULT_SKILLS_DIR = DEFAULT_CONFIG_DIR / "skills"
DEFAULT_PLUGINS_DIR = DEFAULT_CONFIG_DIR / "plugins"
DEFAULT_MCP_DIR = DEFAULT_CONFIG_DIR / "mcp_servers"


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""
    name: str
    provider_type: str  # openai, anthropic, google, ollama, groq, deepseek, etc.
    api_key: str | None = None
    base_url: str | None = None
    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider_type": self.provider_type,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "enabled": self.enabled,
        }


@dataclass
class NexusConfig:
    """Main configuration for Nexus."""
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    active_provider: str = "openai"
    planner_model: str | None = None
    worker_model: str | None = None
    config_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG_DIR)
    memory_dir: Path = field(default_factory=lambda: DEFAULT_MEMORY_DIR)
    skills_dir: Path = field(default_factory=lambda: DEFAULT_SKILLS_DIR)
    plugins_dir: Path = field(default_factory=lambda: DEFAULT_PLUGINS_DIR)
    mcp_dir: Path = field(default_factory=lambda: DEFAULT_MCP_DIR)
    log_level: str = "INFO"
    sandbox_mode: str = "off"  # off, non-main, all
    tool_profile: str = "coding"  # minimal, default, coding, all

    # Search providers
    search_provider: str = "exa"
    tavily_api_key: str | None = None
    brave_api_key: str | None = None
    exa_api_key: str | None = None

    # Termux-specific
    termux_mode: bool = False
    clipboard_tool: str = "termux-clipboard-set"

    def ensure_dirs(self) -> None:
        """Ensure all required directories exist."""
        for d in [self.memory_dir, self.skills_dir, self.plugins_dir, self.mcp_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "active_provider": self.active_provider,
            "planner_model": self.planner_model,
            "worker_model": self.worker_model,
            "memory_dir": str(self.memory_dir),
            "skills_dir": str(self.skills_dir),
            "plugins_dir": str(self.plugins_dir),
            "mcp_dir": str(self.mcp_dir),
            "log_level": self.log_level,
            "sandbox_mode": self.sandbox_mode,
            "tool_profile": self.tool_profile,
            "search_provider": self.search_provider,
            "tavily_api_key": self.tavily_api_key,
            "brave_api_key": self.brave_api_key,
            "exa_api_key": self.exa_api_key,
            "termux_mode": self.termux_mode,
            "clipboard_tool": self.clipboard_tool,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NexusConfig":
        config = cls()
        if "providers" in data:
            config.providers = {
                k: ProviderConfig(**v) for k, v in data["providers"].items()
            }
        config.active_provider = data.get("active_provider", "openai")
        config.planner_model = data.get("planner_model")
        config.worker_model = data.get("worker_model")
        if "memory_dir" in data:
            config.memory_dir = Path(data["memory_dir"])
        if "skills_dir" in data:
            config.skills_dir = Path(data["skills_dir"])
        if "plugins_dir" in data:
            config.plugins_dir = Path(data["plugins_dir"])
        if "mcp_dir" in data:
            config.mcp_dir = Path(data["mcp_dir"])
        config.log_level = data.get("log_level", "INFO")
        config.sandbox_mode = data.get("sandbox_mode", "off")
        config.tool_profile = data.get("tool_profile", "coding")
        config.search_provider = data.get("search_provider", "exa")
        config.tavily_api_key = data.get("tavily_api_key")
        config.brave_api_key = data.get("brave_api_key")
        config.exa_api_key = data.get("exa_api_key")
        config.termux_mode = data.get("termux_mode", False)
        config.clipboard_tool = data.get("clipboard_tool", "termux-clipboard-set")
        return config


def load_config(config_path: Path | None = None) -> NexusConfig:
    """Load configuration from file, auto-creating from env vars if needed."""
    path = config_path or DEFAULT_CONFIG_FILE
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        return NexusConfig.from_dict(data)

    config = NexusConfig()

    # Auto-detect Termux
    if os.path.exists("/data/data/com.termux"):
        config.termux_mode = True

    # Auto-detect providers from env vars
    if os.environ.get("OPENAI_API_KEY"):
        config.providers["openai"] = ProviderConfig(
            name="openai", provider_type="openai",
            api_key=os.environ["OPENAI_API_KEY"],
            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        )
        config.active_provider = "openai"

    if os.environ.get("ANTHROPIC_API_KEY"):
        config.providers["anthropic"] = ProviderConfig(
            name="anthropic", provider_type="anthropic",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        )
        if config.active_provider == "openai":
            config.active_provider = "anthropic"

    if os.environ.get("GOOGLE_API_KEY"):
        config.providers["google"] = ProviderConfig(
            name="google", provider_type="google",
            api_key=os.environ["GOOGLE_API_KEY"],
            model=os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash"),
        )

    if os.environ.get("OLLAMA_HOST"):
        config.providers["ollama"] = ProviderConfig(
            name="ollama", provider_type="ollama",
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            model=os.environ.get("OLLAMA_MODEL", "llama3"),
        )

    if os.environ.get("GROQ_API_KEY"):
        config.providers["groq"] = ProviderConfig(
            name="groq", provider_type="groq",
            api_key=os.environ["GROQ_API_KEY"],
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        )

    if os.environ.get("DEEPSEEK_API_KEY"):
        config.providers["deepseek"] = ProviderConfig(
            name="deepseek", provider_type="deepseek",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )

    if os.environ.get("MISTRAL_API_KEY"):
        config.providers["mistral"] = ProviderConfig(
            name="mistral", provider_type="mistral",
            api_key=os.environ["MISTRAL_API_KEY"],
            model=os.environ.get("MISTRAL_MODEL", "mistral-large-latest"),
        )

    if os.environ.get("OPENCODE_ZEN_API_KEY"):
        config.providers["opencode-zen"] = ProviderConfig(
            name="opencode-zen", provider_type="opencode-zen",
            api_key=os.environ["OPENCODE_ZEN_API_KEY"],
            base_url="https://opencode.ai/zen/v1",
            model=os.environ.get("OPENCODE_ZEN_MODEL", "minimax-m2.5-free"),
        )
        if config.active_provider == "openai":
            config.active_provider = "opencode-zen"

    if os.environ.get("OPENCODE_GO_API_KEY"):
        config.providers["opencode-go"] = ProviderConfig(
            name="opencode-go", provider_type="opencode-go",
            api_key=os.environ["OPENCODE_GO_API_KEY"],
            base_url="https://opencode.ai/zen/go/v1",
            model=os.environ.get("OPENCODE_GO_MODEL", "kimi-k2.5"),
        )

    # Auto-save detected config
    save_config(config, path)

    return config


def save_config(config: NexusConfig, config_path: Path | None = None) -> None:
    """Save configuration to file."""
    path = config_path or DEFAULT_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
