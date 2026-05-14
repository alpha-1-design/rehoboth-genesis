"""Status bar component that shows Termux status in REPL/TUI.

Creates a compact status string like:
  NEXUS v0.1  ● ONLINE  ⚡87%  📶 WiFi  🧠 ollama/llama3
"""

from dataclasses import dataclass


@dataclass
class StatusBar:
    """Compact status bar for the terminal."""

    version: str = "0.1.0"
    termux_mode: bool = False
    battery_pct: int = 0
    is_charging: bool = False
    network: str = "offline"
    model: str = "none"
    provider: str = "none"
    agent_count: int = 0

    def format(self, width: int = 80) -> str:
        parts = [f"NEXUS v{self.version}"]

        parts.append("● ONLINE")

        if self.termux_mode:
            batt_icon = "⚡" if self.is_charging else "🔋"
            parts.append(f"{batt_icon}{self.battery_pct}%")

        parts.append(f"📶 {self.network}")
        parts.append(f"🧠 {self.model}")

        if self.agent_count > 0:
            parts.append(f"👥 ×{self.agent_count}")

        status = "  ".join(parts)

        # Pad or truncate to width
        if len(status) < width:
            status = status + " " * (width - len(status))
        else:
            status = status[:width]

        return status

    @classmethod
    def from_config(cls, config) -> "StatusBar":
        """Build from NexusConfig."""
        bar = cls()
        bar.termux_mode = getattr(config, "termux_mode", False)
        return bar
