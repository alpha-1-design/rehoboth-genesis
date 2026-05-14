<img width="720" height="1600" alt="1000419577" src="https://github.com/user-attachments/assets/98b18818-eaee-4820-a945-594bfa839859" />

# Nexus - Your AI Coding Agent

**A self-hosted AI coding agent CLI that actually works out of the box.**

Nexus is designed to be dynamic, responsive, and deeply integrated into your workflow, especially on mobile environments like Termux. It offers a seamless blend of natural language interaction, intelligent tool usage, and a visually engaging CLI experience.

<img width="720" height="1600" alt="Nexus Logo" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA... (binary data embedded)" />

```
░▒█║  ░▒█║ ░▒█║▀▀▀ ░▒█║  ░▒█║ ░▒█║  ░▒█║ ░▒█║▀▀▀
░▒█║▀█░▒█║ ░▒█║▀▀  ░▒█║  ░▒█║ ░▒█║  ░▒█║ ░▒█║▀▀ 
░▒█║  ░▒█║ ░▒█║▄▄▄ ░▒█║▄█░▒█║ ░▒█║▄█░▒█║ ░▒█║▄▄▄
▀▀▀▀  ▀▀▀▀ ▀▀▀▀▀▀▀  ▀▀▀ ▀▀▀▀   ▀▀▀ ▀▀▀▀  ▀▀▀▀▀▀▀

N E X U S   O S   I N I T I A L I Z E D  [build 2026.04.22]
──────────────────────────────────────────────────────────
[NEURAL] Synaptic weights loaded... OK
[MEMRY] SQLite vector-mesh active... OK
[TOOLS] Execution registry online... OK
[SYNC ] Cross-device uplink standby... OK

Welcome to the Nexus.
Enter a command or type /help to begin the cycle.
```

## Key Features

*   **Dynamic ReAct Loop:** Nexus reasons, acts, and observes in real-time, adapting to task results and errors. No more rigid planning.
*   **Atmospheric UI:** A visually engaging CLI experience with sci-fi styling, pulsing animations, and clear status indicators.
*   **Proactive Dependency Management:** Optional features (Voice, Automation) prompt for installation when first used.
*   **Smart Provider Fallbacks:** If one LLM provider fails, Nexus automatically switches to another.
*   **Hands-Free Voice Commands:** Integrated `/voice` command for speaking commands.
*   **Update Notifications:** Get notified of new versions upon startup.
*   **Hardened Tooling:** Reliable file editing and execution.
*   **Termux-Native:** Optimized for mobile environments.

---

## Quick Start

### 1. Install Nexus (Global Deployment)
```bash
git clone https://github.com/alpha-1-design/Nexus.git && cd Nexus
bash install.sh
```
This installer creates a self-contained environment and links the `nexus` command globally. You never need to activate a `venv` manually.

### 2. Launch Interactive Session

**REPL Mode:**
```bash
nexus repl
```
This starts the command-line interface where you can interact with Nexus using natural language or slash commands (type `/help` for a list).

**TUI Mode:**
```bash
nexus tui
```
This launches the full Textual TUI application with panels for Chat, Thinking, Tools, and Agents.

---

## Providers & Configuration

Nexus uses an OpenAI-compatible provider abstraction. Configure your preferred LLMs:

| Provider     | API Key          | Free Tier | Notes                               |
|--------------|------------------|-----------|-------------------------------------|
| **OpenCode Zen** | None             | Yes (default) | Works immediately                   |
| **Groq**     | `GROQ_API_KEY`   | Yes       | Fast inference                      |
| **OpenAI**   | `OPENAI_API_KEY` | No        | Full model range                    |
| **Anthropic**| `ANTHROPIC_API_KEY`| No        | Claude models                       |
| **Gemini**   | `GOOGLE_API_KEY` | Limited   | Google's models                     |
| **Ollama**   | None             | Yes       | Local models                        |
| **Deepseek** | `DEEPSEEK_API_KEY`| Limited   | Cost-effective                      |
| **Custom**   | Varies           | Varies    | Any OpenAI-compatible API           |

```bash
# Quick setup with OpenCode Zen (default)
nexus setup

# Or configure manually
nexus provider add groq --type groq --api-key $GROQ_API_KEY --model llama-3.3-70b

# Switch active provider
nexus provider set-active groq
```

---

## Extending Nexus

Adding new tools or features is designed to be simple:

1.  **New Tool:** Create a Python class inheriting from `nexus.tools.base.BaseTool` in `nexus/tools/core.py`. Register it in `nexus/tools/core.py`'s `register_all` function.
2.  **New Extension (e.g., Voice):** Install necessary libraries (e.g., `pip install faster-whisper`). Nexus will prompt for installation if they're missing when the feature is used.
3.  **New Provider:** Add its configuration via `nexus provider add`.

---

## License

MIT
