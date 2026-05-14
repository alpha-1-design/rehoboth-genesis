import click

from ..config import NexusConfig, ProviderConfig, save_config
from ..personality import get_personality


class OnboardingManager:
    """
    Handles the first-run experience for Nexus.
    Transforms a technical setup into a welcoming journey.
    """

    def __init__(self, config: NexusConfig):
        self.config = config
        self.personality = get_personality()

    def run(self):
        """The main onboarding loop."""
        self._display_intro()

        # 1. Model Selection
        provider = self._select_provider()

        # 2. Key Acquisition
        api_key = self._handle_api_key(provider)

        # 3. Model Specification
        model = self._select_model(provider)

        # 4. Finalize
        self._finalize_setup(provider, model, api_key)

    def _display_intro(self):
        click.echo("\n" + "✧" * 60)
        # Use personality for the greeting to make it feel human
        greeting = self.personality.greet() if hasattr(self.personality, "greet") else "Welcome to Nexus."
        click.echo(f"\033[1;36m{greeting}\033[0m")
        click.echo("\033[90mI'm here to help you build the future. Let's get you synchronized.\033[0m")
        click.echo("✧" * 60 + "\n")

    def _select_provider(self) -> str:
        options = [
            ("ollama", "Ollama", "Local", "Private, runs on your machine. Unlimited power."),
            ("opencode-zen", "OpenCode Zen", "Free", "Fast, accessible, no keys needed for free tier."),
            ("anthropic", "Anthropic", "Elite", "Claude 3.5 Sonnet/Opus — unparalleled reasoning."),
            ("openai", "OpenAI", "Elite", "GPT-4o — the industry standard."),
            ("groq", "Groq", "Fast", "Llama 3.3 — near-instant inference."),
        ]

        click.echo("\033[1mWhere shall we connect your intelligence?\033[0m\n")
        for i, (pid, name, badge, desc) in enumerate(options, 1):
            color = "green" if badge == "Free" else "cyan" if badge == "Elite" else "yellow"
            click.echo(f"  {i}. {name} \033[3{color}m[{badge}]\033[0m")
            click.echo(f"     \033[90m{desc}\033[0m")

        choice = click.prompt("\nChoose your provider", type=click.IntRange(1, len(options)), default=1)
        return options[choice - 1][0]

    def _handle_api_key(self, provider: str) -> str:
        if provider == "ollama":
            click.echo("\n\033[92mLocal core detected. No API key required.\033[0m")
            return ""

        # Key Map
        key_map = {
            "anthropic": "https://console.anthropic.com/settings/keys",
            "openai": "https://platform.openai.com/api-keys",
            "groq": "https://console.groq.com/keys",
            "opencode-zen": "https://opencode.ai/zen",
        }

        url = key_map.get(provider, "Check provider documentation")

        click.echo(f"\n\033[1mTo connect to {provider}, I'll need an API key.\033[0m")
        click.echo(f"If you don't have one, you can find it here: \033[34m{url}\033[0m")

        api_key = click.prompt("Enter your API key (or press Enter to skip)", hide_input=True, default="")
        return api_key

    def _select_model(self, provider: str) -> str:
        # Simplified model selection for onboarding
        defaults = {
            "ollama": "qwen2.5-coder:7b",
            "opencode-zen": "minimax-m2.5-free",
            "anthropic": "claude-3-5-sonnet-20240620",
            "openai": "gpt-4o",
            "groq": "llama-3.3-70b-versatile",
        }
        default_m = defaults.get(provider, "gpt-4o")
        return click.prompt(f"Which model should we use? (Default: {default_m})", default=default_m)

    def _finalize_setup(self, provider: str, model: str, api_key: str):
        # This mirrors the existing ProviderConfig creation but with the new flow

        # Basic provider type mapping
        types = {"ollama": "openai", "opencode-zen": "openai"}
        p_type = types.get(provider, provider)

        p_cfg = ProviderConfig(
            name=provider,
            provider_type=p_type,
            api_key=api_key,
            model=model,
        )

        self.config.providers = {provider: p_cfg}
        self.config.active_provider = provider
        self.config.first_run = False
        save_config(self.config)

        click.echo("\n" + "✧" * 60)
        click.echo("\033[1;32mSynchronization complete.\033[0m")
        click.echo("\033[90mNexus is now online and tuned to your preferences.\033[0m")
        click.echo("✧" * 60 + "\n")
