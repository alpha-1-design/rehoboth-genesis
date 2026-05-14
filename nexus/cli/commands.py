"""Nexus CLI - Command line interface for Nexus."""

import asyncio
import os
import sys
from pathlib import Path

import click

from nexus import __version__
from nexus.config import NexusConfig, save_config
from nexus.providers import Message, get_manager
from nexus.tools import get_registry


@click.group()
@click.version_option(version=__version__)
@click.option("--config", type=click.Path(), help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """Nexus - Your AI Coding Agent.

    A powerful, self-hosted AI coding agent that combines the best features
    of OpenClaw, Claude Code, Gemini CLI, OpenCode, and NemoClaw.
    """
    from nexus.config import load_config

    ctx.ensure_object(dict)
    if config:
        ctx.obj["config"] = load_config(Path(config))
    else:
        ctx.obj["config"] = load_config()


@cli.command("upgrade")
def upgrade() -> None:
    """Upgrade Nexus to the latest version."""
    import subprocess

    click.echo(f"\n{chr(0x2728)} Checking for updates...")
    try:
        # Fetch latest
        subprocess.run(["git", "pull", "origin", "main"], check=True)
        # Re-install
        subprocess.run(["bash", "install.sh"], check=True)
        click.echo(f"\n{chr(0x2705)} Nexus upgraded successfully.")
    except Exception as e:
        click.echo(f"\n{chr(0x274C)} Upgrade failed: {e}")


# Provider commands
@cli.group()
def provider():
    """Manage AI providers."""
    pass


@provider.command("list")
@click.pass_context
def provider_list(ctx: click.Context) -> None:
    """List all configured providers."""
    from nexus.providers import get_manager

    config: NexusConfig = ctx.obj["config"]
    get_manager()

    click.echo("Configured providers:\n")
    for name, cfg in config.providers.items():
        status = "active" if name == config.active_provider else "inactive"
        click.echo(f"  {name} ({cfg.provider_type}) - {cfg.model} [{status}]")
        if cfg.base_url:
            click.echo(f"    URL: {cfg.base_url}")


@provider.command("add")
@click.argument("name")
@click.option(
    "--type",
    "provider_type",
    required=True,
    help="Provider type (openai, anthropic, google, ollama, groq, deepseek)",
)
@click.option("--api-key", help="API key")
@click.option("--base-url", help="Base URL (for custom endpoints)")
@click.option("--model", default="gpt-4o", help="Default model")
@click.pass_context
def provider_add(
    ctx: click.Context,
    name: str,
    provider_type: str,
    api_key: str | None,
    base_url: str | None,
    model: str,
) -> None:
    """Add a new AI provider."""
    from nexus.config import ProviderConfig, save_config

    config: NexusConfig = ctx.obj["config"]

    config.providers[name] = ProviderConfig(
        name=name,
        provider_type=provider_type,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    save_config(config)
    click.echo(f"Added provider: {name}")


@provider.command("remove")
@click.argument("name")
@click.pass_context
def provider_remove(ctx: click.Context, name: str) -> None:
    """Remove a provider."""
    from nexus.config import save_config

    config: NexusConfig = ctx.obj["config"]

    if name in config.providers:
        del config.providers[name]
        save_config(config)
        click.echo(f"Removed provider: {name}")
    else:
        click.echo(f"Provider not found: {name}", err=True)


@provider.command("set-active")
@click.argument("name")
@click.pass_context
def provider_set_active(ctx: click.Context, name: str) -> None:
    """Set the active provider."""
    from nexus.config import save_config
    from nexus.providers import get_manager

    config: NexusConfig = ctx.obj["config"]

    if name not in config.providers:
        click.echo(f"Provider not found: {name}", err=True)
        return

    config.active_provider = name
    save_config(config)

    manager = get_manager()
    manager.set_active(name)

    click.echo(f"Active provider set to: {name}")


# Model commands
@cli.group()
def model():
    """Manage AI models."""
    pass


@model.command("list")
@click.option("--provider", help="Filter by provider")
@click.pass_context
def model_list(ctx: click.Context, provider: str | None) -> None:
    """List available models."""

    async def run():
        manager = get_manager()
        try:
            models = await manager.list_models(provider)
            click.echo("Available models:\n")
            for m in models:
                click.echo(f"  {m.id}")
                click.echo(f"    Provider: {m.provider}")
                click.echo(f"    Context: {m.context_window:,} tokens")
                click.echo(f"    Vision: {'Yes' if m.supports_vision else 'No'}")
                click.echo()
        finally:
            await manager.close_all()

    asyncio.run(run())


@model.command("set")
@click.argument("model")
@click.option("--provider", help="Provider name")
@click.pass_context
def model_set(ctx: click.Context, model: str, provider: str | None) -> None:
    """Set the model for a provider."""

    async def run():
        manager = get_manager()
        try:
            await manager.switch_model(model, provider)
            p = provider or manager.active_provider
            click.echo(f"Model set to: {model} for provider: {p}")
        finally:
            await manager.close_all()

    asyncio.run(run())


# Tool commands
@cli.group()
def tool():
    """Manage tools."""
    pass


@tool.command("list")
@click.option("--category", help="Filter by category")
@click.pass_context
def tool_list(ctx: click.Context, category: str | None) -> None:
    """List available tools."""
    registry = get_registry()

    if category:
        tools = registry.list_by_category(category)
        click.echo(f"Tools in '{category}':\n")
    else:
        tools = registry.list_all()
        click.echo(f"All tools ({len(tools)}):\n")
        for cat in registry.get_categories():
            click.echo(f"\n## {cat}")

    for t in tools:
        click.echo(f"\n### {t.name}")
        click.echo(f"   {t.description}")


# Session commands
@cli.group()
def session():
    """Manage sessions."""
    pass


@session.command("list")
@click.option("--limit", default=20, help="Number of sessions to show")
@click.pass_context
def session_list(ctx: click.Context, limit: int) -> None:
    """List recent sessions."""
    from ..memory import get_memory

    memory = get_memory()
    sessions = memory.list_sessions(limit)

    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo("Recent sessions:\n")
    for s in sessions:
        date = s.created_at.strftime("%Y-%m-%d %H:%M")
        outcome = s.outcome or "in progress"
        click.echo(f"  [{date}] {s.id} - {outcome}")


@session.command("show")
@click.argument("session_id")
@click.pass_context
def session_show(ctx: click.Context, session_id: str) -> None:
    """Show a session's details."""
    from ..memory import get_memory

    memory = get_memory()
    session = memory.load_session(session_id)

    if not session:
        click.echo(f"Session not found: {session_id}", err=True)
        return

    click.echo(f"Session: {session.id}\n")
    click.echo(f"Created: {session.created_at}")
    click.echo(f"Updated: {session.updated_at}")
    click.echo(f"Outcome: {session.outcome or 'in progress'}")
    click.echo(f"Tools used: {', '.join(session.tools_used) if session.tools_used else 'none'}")
    click.echo(f"\nMessages: {len(session.messages)}")


# Memory commands
# Sync commands
@cli.group()
def sync():
    """Sync sessions across devices and services."""
    pass


@sync.command("status")
def sync_status() -> None:
    """Show sync status."""
    from ..sync import get_sync_engine

    engine = get_sync_engine()
    print(engine.format_status())


@sync.command("connect")
@click.argument("target_type")
@click.option("--name", default=None, help="Endpoint name")
@click.option("--token", help="API token (GitHub)")
@click.option("--path", type=click.Path(), help="Local path or git remote URL")
@click.option("--url", help="Service URL")
def sync_connect(target_type: str, name: str | None, token: str | None, path: str | None, url: str | None) -> None:
    """Connect a sync target (github-gist, local, git)."""
    from ..sync import SyncEndpoint, SyncTarget, get_sync_engine

    target_map = {
        "github-gist": SyncTarget.GITHUB_GIST,
        "github": SyncTarget.GITHUB_GIST,
        "local": SyncTarget.LOCAL,
        "git": SyncTarget.GIT_REMOTE,
    }

    target = target_map.get(target_type.lower())
    if not target:
        click.echo(f"Unknown target type: {target_type}. Valid: {', '.join(target_map.keys())}", err=True)
        return

    engine = get_sync_engine()
    endpoint_name = name or f"{target_type}-{target.value}"

    endpoint = SyncEndpoint(
        name=endpoint_name,
        target=target,
        token=token,
        path=Path(path) if path else None,
        url=url,
    )

    if engine.connect(endpoint):
        click.echo(f"Connected: {endpoint_name} ({target.name})")
    else:
        click.echo(f"Connection test failed for: {endpoint_name}", err=True)


@sync.command("push")
@click.argument("endpoint_name", default="default")
@click.option("--session", help="Specific session ID to push")
def sync_push(endpoint_name: str, session: str | None) -> None:
    """Push sessions to sync endpoint."""
    from ..sync import get_sync_engine

    engine = get_sync_engine()
    result = engine.push(endpoint_name, session)

    if result.get("success"):
        click.echo(f"Pushed: {result.get('items', 0)} item(s)")
        if result.get("gist_url"):
            click.echo(f"Gist: {result['gist_url']}")
    else:
        click.echo(f"Push failed: {result.get('error')}", err=True)


@sync.command("pull")
@click.argument("endpoint_name", default="default")
@click.option("--session", help="Specific session ID to pull")
def sync_pull(endpoint_name: str, session: str | None) -> None:
    """Pull sessions from sync endpoint."""
    from ..sync import get_sync_engine

    engine = get_sync_engine()
    result = engine.pull(endpoint_name, session)

    if result.get("success"):
        click.echo(f"Pulled: {result.get('items', 0)} item(s)")
        if result.get("conflicts"):
            click.echo(f"Conflicts: {', '.join(result['conflicts'])}")
    else:
        click.echo(f"Pull failed: {result.get('error')}", err=True)


@sync.command("disconnect")
@click.argument("endpoint_name")
def sync_disconnect(endpoint_name: str) -> None:
    """Disconnect a sync endpoint."""
    from ..sync import get_sync_engine

    engine = get_sync_engine()
    if engine.disconnect(endpoint_name):
        click.echo(f"Disconnected: {endpoint_name}")
    else:
        click.echo(f"Endpoint not found: {endpoint_name}", err=True)


# Learn commands
@cli.group()
def learn():
    """Failure learning and self-improvement."""
    pass


@learn.command("stats")
def learn_stats() -> None:
    """Show learning statistics."""
    from ..learn import get_learning_engine

    engine = get_learning_engine()
    print(engine.format_summary())


@learn.command("lessons")
@click.option("--show", default=5, help="Number of lessons to show")
def learn_lessons(show: int) -> None:
    """Show recent lessons."""
    from ..learn import get_learning_engine

    engine = get_learning_engine()
    lessons = engine._load_all_lessons()[:show]

    if not lessons:
        click.echo("No lessons yet. Keep working!")
        return

    for lesson in lessons:
        rate = lesson.success_count / max(1, lesson.success_count + lesson.failure_count)
        click.echo(f"\n  [{lesson.lesson_id}] {lesson.title}")
        click.echo(f"    {lesson.summary[:100]}...")
        click.echo(f"    Success rate: {rate:.0%} ({lesson.success_count} ok / {lesson.failure_count} fail)")
        for tc in lesson.trigger_conditions[:3]:
            click.echo(f"    Trigger: {tc}")


@learn.command("failures")
@click.option("--limit", default=10, help="Number of failures to show")
def learn_failures(limit: int) -> None:
    """Show recent failure records."""
    import json

    from ..learn import get_learning_engine

    engine = get_learning_engine()
    failures = sorted(
        engine.failures_dir.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]

    if not failures:
        click.echo("No failures recorded.")
        return

    for f in failures:
        data = json.loads(f.read_text())
        date = data["timestamp"][:16]
        click.echo(f"\n  [{date}] {data['tool_name']} — {data['error_type']}")
        click.echo(f"    {data['error'][:80]}...")
        if data.get("resolution"):
            click.echo(f"    Resolved: {data['resolution'][:60]}")


@learn.command("clear")
@click.confirmation_option(prompt="Clear all failure records and lessons?")
def learn_clear() -> None:
    """Clear all learning data."""

    from ..learn import get_learning_engine

    engine = get_learning_engine()

    for d in [engine.failures_dir, engine.lessons_dir, engine.patterns_dir]:
        if d.exists():
            for f in d.glob("*.json"):
                f.unlink()
            for f in d.glob("*.md"):
                f.unlink()

    click.echo("Learning data cleared.")


# Memory commands
@cli.group()
def memory():
    """Manage memory."""
    pass


@memory.command("facts")
@click.pass_context
def memory_facts(ctx: click.Context) -> None:
    """Show stored facts."""
    from ..memory import get_memory

    memory = get_memory()
    facts = memory.get_all_facts()

    if not facts:
        click.echo("No facts stored.")
        return

    click.echo("Stored facts:\n")
    for key, value in facts.items():
        click.echo(f"  {key}: {value}")


@memory.command("add-fact")
@click.argument("key")
@click.argument("value")
@click.option("--category", default="general", help="Fact category")
@click.pass_context
def memory_add_fact(ctx: click.Context, key: str, value: str, category: str) -> None:
    """Add a fact to memory."""
    from ..memory import get_memory

    memory = get_memory()
    memory.add_fact(key, value, category)
    click.echo(f"Added fact: {key} = {value}")


# Settings commands
@cli.group()
def config():
    """Manage configuration."""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration."""
    cfg: NexusConfig = ctx.obj["config"]
    import json

    click.echo(json.dumps(cfg.to_dict(), indent=2, default=str))


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a configuration value."""
    config: NexusConfig = ctx.obj["config"]

    # Handle nested keys like 'providers.openai.model'
    if "." in key:
        parts = key.split(".")
        obj = config.to_dict()
        for p in parts[:-1]:
            obj = obj[p]
        obj[parts[-1]] = value
        new_config = NexusConfig.from_dict(config.to_dict())
        new_config.ensure_dirs()
        save_config(new_config)
    else:
        setattr(config, key, value)
        save_config(config)

    click.echo(f"Set {key} = {value}")


# Setup command
OPENCODE_ZEN_FREE_MODELS = [
    ("minimax-m2.5-free", "MiniMax M2.5 — Best all-around, fastest", "free"),
    ("big-pickle", "Big Pickle — OpenCode's own model", "free"),
    ("qwen3.6-plus-free", "Qwen 3.6 Plus — Large context window", "free"),
    ("nemotron-3-super-free", "Nemotron 3 Super — NVIDIA's best free", "free"),
]

PROVIDER_OPTIONS = [
    (
        "opencode-zen",
        "OpenCode Zen",
        "Recommended",
        "Best free models, no key needed for free tier",
    ),
    ("opencode-go", "OpenCode Go", "Premium", "Kimi K2.5, GLM 5, MiniMax M2.7 (paid)"),
    ("groq", "Groq", "Free tier", "Llama-3.3-70B, Mixtral — fast inference"),
    ("openrouter", "OpenRouter", "100+ models", "Access to dozens of providers, has free models"),
    ("anthropic", "Anthropic", "Premium", "Claude Sonnet 4, Opus 4 — best reasoning"),
    ("openai", "OpenAI", "Premium", "GPT-4o, GPT-4o-mini — reliable"),
    ("google", "Google Gemini", "Free + Paid", "Gemini 2.0 Flash — fast, good free tier"),
    ("ollama", "Ollama", "Local", "Run models locally on your machine (private)"),
]

API_KEY_INSTRUCTIONS = {
    "opencode-zen": "Get your free key at https://opencode.ai/zen (optional for free models)",
    "opencode-go": "Get your subscription key at https://opencode.ai/zen/go",
    "groq": "Get free key at https://console.groq.com/keys",
    "openrouter": "Get key at https://openrouter.ai/keys",
    "anthropic": "Get key at https://console.anthropic.com/settings/keys",
    "openai": "Get key at https://platform.openai.com/api-keys",
    "google": "Get key at https://aistudio.google.com/app/apikey",
    "ollama": "No key needed — runs locally (run: ollama serve)",
}


@cli.command("setup")
@click.option("--provider", help="Provider name (skip interactive mode)")
@click.option("--model", help="Model name (skip interactive mode)")
@click.option("--api-key", help="API key (skip interactive mode)")
@click.option("--non-interactive", is_flag=True, help="Use defaults or env vars (for CI)")
@click.pass_context
def setup_cmd(
    ctx: click.Context,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    non_interactive: bool,
) -> None:
    """Interactive setup wizard — configure your AI provider in seconds.

    Guides you through selecting a provider, model, and API key.
    OpenCode Zen is recommended for zero-cost setup.

    Examples:

        nexus setup                     Interactive wizard
        nexus setup --non-interactive   Use env vars or defaults
        nexus setup --provider groq      Quick setup for a specific provider
    """
    config: NexusConfig = ctx.obj["config"]

    # Auto-detect Termux
    is_termux = os.path.exists("/data/data/com.termux/files/usr/bin/termux-audio") or os.environ.get("TERMUX_VERSION")

    # Banner
    click.echo("\n" + "=" * 50)
    click.echo("  NEXUS SETUP WIZARD")
    click.echo("=" * 50)
    if is_termux:
        click.echo("  [Detected: Termux/Android]")
    else:
        click.echo("  [Detected: Linux/macOS/Windows]")
    click.echo("")

    # --- Provider selection ---
    if not provider:
        from .onboarding import OnboardingManager

        manager = OnboardingManager(config)
        manager.run()
        # After onboarding, we need to extract the selected provider for the rest of the function
        provider = config.active_provider
        # We also need the model and api_key from the config since manager.run() updated it
        model = config.providers[provider].model
        api_key = config.providers[provider].api_key

        click.echo("\n[+] Setup complete!\n")
        print_cheatsheet(provider, model, is_termux)
        click.echo("\n[+] You're all set! Try: \033[1mnexus repl\033[0m to start chatting.")
        return


def test_provider_connection(provider: str, model: str, api_key: str, base_url: str | None) -> dict:
    """Test if a provider+model works."""
    try:
        import httpx

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if provider in ("opencode-zen", "opencode-go"):
            url = f"{base_url}/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            }
        elif provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            }
        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers["x-api-key"] = api_key or ""
            headers["anthropic-version"] = "2023-06-01"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            }
        elif provider == "google":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            params = {"key": api_key or ""}
            payload = {"contents": [{"parts": [{"text": "hi"}]}]}
        elif provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            }
        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            }
        elif provider == "ollama":
            url = f"{base_url}/api/chat"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            }
        else:
            return {"ok": False, "error": f"Unknown provider: {provider}"}

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers=headers, params=params if provider == "google" else None)

        if resp.status_code == 200:
            return {"ok": True}
        elif resp.status_code == 401:
            return {"ok": False, "error": "Invalid API key"}
        elif resp.status_code == 429:
            return {"ok": False, "error": "Rate limited — try again in a moment"}
        else:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text[:100])
            except Exception:
                msg = resp.text[:100]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {msg}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


def get_default_model(provider: str) -> str:
    defaults = {
        "groq": "llama-3.3-70b-versatile",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-20250514",
        "google": "gemini-2.0-flash",
        "openrouter": "google/gemma-3-27b-it:free",
        "ollama": "qwen2.5-coder:7b",
        "opencode-zen": "minimax-m2.5-free",
        "opencode-go": "kimi-k2.5",
    }
    return defaults.get(provider, "gpt-4o")


def get_provider_type(provider: str) -> str:
    types = {
        "opencode-zen": "openai",
        "opencode-go": "openai",
        "anthropic": "anthropic",
        "google": "google",
        "ollama": "openai",
    }
    return types.get(provider, provider)


def get_base_url(provider: str) -> str | None:
    urls = {
        "opencode-zen": "https://opencode.ai/zen/v1",
        "opencode-go": "https://opencode.ai/zen/go/v1",
        "ollama": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    }
    return urls.get(provider)


def print_cheatsheet(provider: str, model: str, is_termux: bool) -> None:
    click.echo("=" * 50)
    click.echo("  QUICK REFERENCE")
    click.echo("=" * 50)
    click.echo("")
    click.echo("  # Start chatting")
    if is_termux:
        click.echo("  nexus repl")
    else:
        click.echo("  nexus repl")
    click.echo("")
    click.echo("  # Run a single task")
    click.echo('  nexus run "Fix the login bug"')
    click.echo("")
    click.echo("  # Dashboard (optional web UI)")
    click.echo("  nexus dashboard")
    click.echo("")
    click.echo("  # Voice mode (speak to Nexus)")
    click.echo("  nexus voice")
    click.echo("")
    click.echo("  # Help")
    click.echo("  nexus repl  # then type /help")
    click.echo("")
    click.echo("  Current: " + provider + " / " + model)
    click.echo("")


# Doctor command
@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check system health and diagnose issues."""
    from ..config import DEFAULT_CONFIG_DIR

    click.echo("[*] Running diagnostics...\n")

    issues = []

    # Check config directory
    if not DEFAULT_CONFIG_DIR.exists():
        issues.append(f"Config directory missing: {DEFAULT_CONFIG_DIR}")
        click.echo("  [-] Config directory missing")
    else:
        click.echo("  [+] Config directory exists")

    # Check config file
    from ..config import DEFAULT_CONFIG_FILE

    if not DEFAULT_CONFIG_FILE.exists():
        issues.append(f"Config file missing: {DEFAULT_CONFIG_FILE}")
        click.echo("  [-] Config file missing")
    else:
        click.echo("  [+] Config file exists")

    # Check providers
    config: NexusConfig = ctx.obj["config"]
    if not config.providers:
        issues.append("No providers configured")
        click.echo("  [-] No providers configured")
    else:
        click.echo(f"  [+] {len(config.providers)} provider(s) configured")

    # Check for common tools
    import shutil

    for tool in ["git", "python", "pip"]:
        if shutil.which(tool):
            click.echo(f"  [+] {tool} found")
        else:
            issues.append(f"{tool} not found in PATH")
            click.echo(f"  [-] {tool} not found")

    # Check for ripgrep
    if shutil.which("rg"):
        click.echo("  [+] ripgrep found (for search)")
    else:
        click.echo("  [!] ripgrep not found (install with: pip install ripgrep)")

    # Check learning system
    try:
        from ..learn import get_learning_engine

        le = get_learning_engine()
        stats = le.get_stats()
        click.echo(f"  [+] Learning engine: {stats['total_lessons']} lessons, {stats['total_failures']} failures")
    except Exception as e:
        click.echo(f"  [!] Learning engine error: {e}")

    # Check sync system
    try:
        from ..sync import get_sync_engine

        se = get_sync_engine()
        status = se.get_status()
        ep_count = len(status.get("endpoints", {}))
        click.echo(f"  [+] Sync engine: {ep_count} endpoint(s) configured")
    except Exception as e:
        click.echo(f"  [!] Sync engine error: {e}")

    # Check safety engine
    try:
        from ..safety import get_safety_engine

        se = get_safety_engine()
        click.echo(f"  [+] Safety engine: {len(se.rules)} rules loaded")
    except Exception as e:
        click.echo(f"  [!] Safety engine error: {e}")

    # Check self-improvement
    try:
        from ..self_improve import get_self_improver

        si = get_self_improver()
        pending = len(si.get_improvement_queue())
        click.echo(f"  [+] Self-improvement: {pending} improvement(s) pending")
    except Exception as e:
        click.echo(f"  [!] Self-improvement error: {e}")

    # Check phone mode
    try:
        from ..phone import get_phone_mode

        pm = get_phone_mode()
        click.echo(f"  [+] Phone mode: {pm.profile.name} profile (auto-detected)")
    except Exception as e:
        click.echo(f"  [!] Phone mode error: {e}")

    # Check voice system
    try:
        from ..voice import get_voice_engine, list_tts_voices

        engine = get_voice_engine()
        voices = list_tts_voices()
        click.echo(f"  [+] Voice: TTS={engine.config.tts_provider} ({len(voices)} voices), STT={engine.config.stt_provider}")
    except Exception as e:
        click.echo(f"  [!] Voice system error: {e}")

    if issues:
        click.echo(f"\n[!] {len(issues)} issue(s) found:")
        for issue in issues:
            click.echo(f"  - {issue}")
        click.echo("\n[*] Fix these issues by running: \033[1mnexus setup\033[0m")
    else:
        click.echo("\n[+] All checks passed!")


from ..utils.dependencies import ensure_dependency


# Dashboard command (optional — lazy loaded)
@cli.command("dashboard")
@click.option("--port", default=5000, help="Port to run on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--open/--no-open", default=True, help="Open browser automatically")
@click.pass_context
def dashboard(ctx: click.Context, port: int, host: str, open: bool) -> None:
    """Launch the optional web dashboard (lazy-loaded).

    The dashboard provides a visual overview of sessions, stats, and provider status.
    Run 'nexus dashboard --help' for options.
    """
    if not ensure_dependency("flask"):
        return

    from ..dashboard.app import create_app

    app = create_app()

    if open:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    click.echo(f"Dashboard starting on http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")
    app.run(host=host, port=port, debug=False)


# TUI command
@cli.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Launch the rich Textual TUI."""
    if not ensure_dependency("textual"):
        return

    from .welcome import display_welcome

    display_welcome()

    from ..tui.app import NexusTUI

    app = NexusTUI()
    app.run()


# Voice command
@cli.command()
@click.option("--tts", "tts_override", help="TTS provider override (e.g., freetts, openai)")
@click.option("--stt", "stt_override", help="STT provider override (e.g., whisper, assemblyai)")
@click.option("--voice", "voice_override", help="Voice name (e.g., en-US-Neural2-F)")
@click.option("--continuous", is_flag=True, default=False, help="Keep listening after each response")
@click.pass_context
def voice(
    ctx: click.Context,
    tts_override: str | None,
    stt_override: str | None,
    voice_override: str | None,
    continuous: bool,
) -> None:
    """Enter voice mode — Nexus speaks and listens like a partner.

    This starts an interactive voice conversation where Nexus responds
    using text-to-speech and listens via speech-to-text. Works with
    microphone and speakers.

    Examples:

        nexus voice                     Start with defaults
        nexus voice --tts freetts        Use FreeTTS (no API key needed)
        nexus voice --stt whisper       Use local Whisper for STT
        nexus voice --voice en-US-Neural2-F  Use a specific voice
        nexus voice --continuous        Keep listening after each response

    Provider options:
      TTS: freetts (default, no key), openai, espeak, pico
      STT: assemblyai, deepgram, whisper, freetts
    """
    if not ensure_dependency("pyaudio"):
        return

    if stt_override == "whisper" or (not stt_override and "whisper" in str(ctx.obj.get("config", {}))):
        if not ensure_dependency("faster-whisper"):
            return

    from .welcome import display_welcome

    display_welcome()

    import asyncio

    from ..personality import get_personality
    from ..voice import get_voice_engine

    async def _run():
        overrides = {}
        if tts_override:
            overrides["tts_provider"] = tts_override
        if stt_override:
            overrides["stt_provider"] = stt_override
        if voice_override:
            overrides["voice"] = voice_override

        engine = get_voice_engine(**overrides)
        personality = get_personality()

        click.echo(f"\n{engine.config.tts_provider.upper()} | {engine.config.stt_provider.upper()}")
        click.echo("Say something or press Ctrl+C to exit...\n")

        async def _llm_callback(text: str) -> str:
            from ..personality import get_personality
            from ..providers import get_manager
            from ..tools import get_registry

            manager = get_manager()
            registry = get_registry()
            personality = get_personality()

            tools = [t.to_definition() for t in registry.list_all()]
            system_msg = Message(
                role="system",
                content=personality.get_voice_system_prompt(),
            )
            messages = [system_msg, Message(role="user", content=text)]

            try:
                resp = await manager.complete(messages, tools)
                return resp.content or "I didn't get a response."
            except Exception as e:
                return f"Oops: {e}"
            finally:
                await manager.close_all()

        engine.llm_callback = _llm_callback

        await engine.speak(personality.greet())

        async with engine.voice_mode():
            if continuous:
                while engine._running:
                    await asyncio.sleep(0.5)
            else:
                await engine.listen_and_transcribe()
                if engine.last_transcription:
                    response = await _llm_callback(engine.last_transcription)
                    await engine.speak(response)

    asyncio.run(_run())


# REPL command
@cli.command("repl")
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Start an interactive REPL session.

    The REPL provides an interactive chat interface with Nexus.
    Use /help inside the REPL for available slash commands.
    """
    from .welcome import display_welcome

    display_welcome()

    from ..cli.repl import run_repl
    from ..config import load_config

    config = load_config()
    config_dict = {
        "providers": {k: v.to_dict() for k, v in config.providers.items()},
        "active_provider": config.active_provider,
        "config_dir": str(config.config_dir),
    }
    asyncio.run(run_repl(config=config_dict))


# Run command (single task)
@cli.command("run")
@click.argument("task")
@click.pass_context
def run(ctx: click.Context, task: str) -> None:
    """Run a single task and exit.

    Useful for scripting and one-shot automation tasks.
    """
    from ..cli.repl import run_task
    from ..config import load_config

    config = load_config()
    config_dict = {
        "providers": {k: v.to_dict() for k, v in config.providers.items()},
        "active_provider": config.active_provider,
        "config_dir": str(config.config_dir),
    }
    result, was_streamed = asyncio.run(run_task(task, config=config_dict))
    if result and not was_streamed:
        click.echo(result)


# Automation commands
@cli.group()
def automation():
    """Browser and API automation tools."""
    pass


@automation.command("status")
def automation_status() -> None:
    """Check automation system status."""
    from ..automation import is_browser_available
    from ..automation.browser import PLAYWRIGHT_AVAILABLE

    click.echo("\nAutomation Status:\n")

    click.echo(f"  Playwright:     {'[+] installed' if PLAYWRIGHT_AVAILABLE else '[-] not installed'}")
    click.echo(f"  Chromium:       {'[+] available' if is_browser_available() else '[-] not installed (run: nexus automation install-browser)'}")

    if PLAYWRIGHT_AVAILABLE:
        click.echo("\n  Browser:        Configured for stealth/anti-detection")
        click.echo("  User-Agent:     Randomized rotation enabled")
        click.echo("  CAPTCHA detect: Built-in (recaptcha, hcaptcha, cloudflare)")
        click.echo("  Human-like:    Mouse curves, keystroke delays, scroll")

    click.echo("\n  API Client:     httpx (always available)")
    click.echo("  Rate limiting:  1-3s delay between requests")
    click.echo("  Header rotate:  Referrer, Sec-Fetch, Accept-Language\n")


@automation.command("install-browser")
@click.option("--browser", default="chromium", help="Browser to install (chromium, firefox, webkit)")
@click.option("--with-deps", is_flag=True, default=False, help="Install system dependencies")
def automation_install_browser(browser: str, with_deps: bool) -> None:
    """Install browser for automation. Run this once on a new machine."""
    from ..automation.browser import PLAYWRIGHT_AVAILABLE

    if not PLAYWRIGHT_AVAILABLE:
        click.echo("Playwright not installed. Run: pip install playwright")
        return

    click.echo(f"Installing {browser}...")
    import subprocess

    cmd = ["playwright", "install"]
    if with_deps:
        cmd.append("--with-deps")
    cmd.append(browser)

    result = subprocess.run(cmd)
    if result.returncode == 0:
        click.echo(f"[+] {browser} installed successfully")
    else:
        click.echo(f"[-] Installation failed (exit code: {result.returncode})")
        click.echo(f"  Try: playwright install {browser} --with-deps")


# Initialize providers from config
def initialize_providers(config) -> None:
    """Initialize providers from configuration."""
    from nexus.providers import get_manager

    manager = get_manager()
    for _name, cfg in config.providers.items():
        manager.add_provider(cfg)

    if config.active_provider in config.providers:
        manager.set_active(config.active_provider)


def main():
    """Main entry point."""
    # Fast path for version and help to keep it 'clean'
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "--help"):
        cli(obj={})
        return

    from nexus.config import load_config

    # Load config and initialize
    config = load_config()
    config.ensure_dirs()

    # Check for providers
    if not config.providers:
        from nexus.doctor import run_doctor

        # If we are in the main CLI (not tui/voice/repl), assume interactive unless --non-interactive
        is_interactive = sys.stdin.isatty() and "--non-interactive" not in sys.argv
        run_doctor(interactive=is_interactive)
        # Reload config after setup
        config = load_config()

    initialize_providers(config)

    # Run CLI
    cli(obj={"config": config})


if __name__ == "__main__":
    main()
