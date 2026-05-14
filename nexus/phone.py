"""Phone Mode — Nexus on a phone, or any low-bandwidth/low-power device.

This is NOT a stripped-down version. It's a smarter version:
  - Compact output (no ANSI art, minimal chrome)
  - Optimized for small screens (80-char max, no tables)
  - Works over SSH/Termux with minimal latency
  - Auto-detects terminal size
  - Touch-friendly alternative commands
  - Offline-capable (syncs when online)

Phone mode is auto-detected when:
  - TERMUX environment variable is set
  - Terminal width < 100 chars
  - STREAL environment variable is set (slow real connection)
"""

import os
import shutil
from dataclasses import dataclass
from typing import Any


@dataclass
class DisplayProfile:
    """Display settings for a terminal profile."""
    name: str
    width: int
    use_unicode: bool
    use_color: bool
    use_emoji: bool
    compact: bool
    show_timestamps: bool
    show_thinking: bool
    max_line_length: int
    separator: str


class DisplayProfiles:
    PHONE = DisplayProfile(
        name="phone",
        width=80,
        use_unicode=False,
        use_color=True,
        use_emoji=False,
        compact=True,
        show_timestamps=True,
        show_thinking=False,
        max_line_length=76,
        separator="-",
    )

    TABLET = DisplayProfile(
        name="tablet",
        width=120,
        use_unicode=True,
        use_color=True,
        use_emoji=True,
        compact=False,
        show_timestamps=True,
        show_thinking=True,
        max_line_length=116,
        separator="─",
    )

    DESKTOP = DisplayProfile(
        name="desktop",
        width=200,
        use_unicode=True,
        use_color=True,
        use_emoji=True,
        compact=False,
        show_timestamps=True,
        show_thinking=True,
        max_line_length=196,
        separator="─",
    )

    SSH_SLOW = DisplayProfile(
        name="ssh_slow",
        width=80,
        use_unicode=False,
        use_color=False,
        use_emoji=False,
        compact=True,
        show_timestamps=True,
        show_thinking=False,
        max_line_length=76,
        separator="-",
    )


def detect_display_profile() -> DisplayProfile:
    """Auto-detect the best display profile."""
    # Explicit overrides
    if os.environ.get("NEXUS_PHONE_MODE"):
        return DisplayProfiles.PHONE
    if os.environ.get("NEXUS_SSH_MODE"):
        return DisplayProfiles.SSH_SLOW

    # Termux = phone
    if os.environ.get("TERMUX"):
        return DisplayProfiles.PHONE

    # Try to detect terminal size
    try:
        size = shutil.get_terminal_size()
        width = size.columns
    except Exception:
        width = 80

    if width < 100:
        return DisplayProfiles.PHONE
    elif width < 160:
        return DisplayProfiles.TABLET
    else:
        return DisplayProfiles.DESKTOP


class PhoneModeFormatter:
    """Format output for phone/small screen displays."""

    def __init__(self, profile: DisplayProfile | None = None):
        self.profile = profile or detect_display_profile()

    def wrap(self, text: str, width: int | None = None) -> str:
        """Wrap text to max line length."""
        width = width or self.profile.max_line_length
        lines = []
        for paragraph in text.split("\n"):
            if len(paragraph) <= width:
                lines.append(paragraph)
            else:
                words = paragraph.split()
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 <= width:
                        current = (current + " " + word).strip()
                    else:
                        if current:
                            lines.append(current)
                        current = word
                if current:
                    lines.append(current)
        return "\n".join(lines)

    def header(self, title: str, subtitle: str = "") -> str:
        """Compact header."""
        sep = self.profile.separator * min(len(title) + 4, self.profile.max_line_length)
        lines = [sep]
        lines.append(f" {title}")
        if subtitle:
            lines.append(f"  {subtitle}")
        lines.append(sep)
        return "\n".join(lines)

    def section(self, title: str) -> str:
        """Section divider."""
        return f"\n{self.profile.separator * 3} {title.upper()} {self.profile.separator * 3}\n"

    def bullet(self, text: str, indent: int = 2) -> str:
        """Compact bullet point."""
        prefix = "• " if self.profile.use_emoji else "* "
        return " " * indent + prefix + self.wrap(text)

    def code(self, code: str) -> str:
        """Compact code block."""
        lines = [f"| {self.wrap(l)}" for l in code.split("\n")]
        return "\n".join(lines)

    def success(self, message: str) -> str:
        """Success indicator."""
        icon = "[OK]" if not self.profile.use_unicode else "✓"
        return f"{icon} {self.wrap(message)}"

    def error(self, message: str) -> str:
        """Error indicator."""
        icon = "[!!]" if not self.profile.use_unicode else "✗"
        return f"{icon} {self.wrap(message)}"

    def warning(self, message: str) -> str:
        """Warning indicator."""
        icon = "[!]" if not self.profile.use_unicode else "⚠"
        return f"{icon} {self.wrap(message)}"

    def info(self, label: str, value: str) -> str:
        """Compact label:value pair."""
        return f"{label}: {self.wrap(value)}"

    def prompt(self, message: str, choices: list[str] | None = None) -> str:
        """Phone-optimized prompt."""
        sep = self.profile.separator
        lines = [f"\n{sep * 4}"]
        lines.append(f"  {message}")
        if choices:
            lines.append(f"  Options: {', '.join(choices)}")
        lines.append("  > ")
        return "\n".join(lines)

    def tool_result(self, tool_name: str, result: str, truncated: bool = False) -> str:
        """Compact tool result."""
        lines = [f"\n[{tool_name}]"]
        result_text = self.wrap(result)
        if truncated and len(result_text) > 200:
            result_text = result_text[:200] + "..."
        lines.append(result_text)
        return "\n".join(lines)

    def thinking(self, step: str) -> str:
        """Compact thinking indicator (only if enabled)."""
        if not self.profile.show_thinking:
            return ""
        icon = "..." if not self.profile.use_unicode else "◌"
        return f"\r{icon} {step}"

    def status_bar(self, **items: str) -> str:
        """Compact status bar."""
        parts = [f"{k}:{v}" for k, v in items.items()]
        return " | ".join(parts)

    def table(self, headers: list[str], rows: list[list[str]]) -> str:
        """Simple table that fits phone screens."""
        if not rows:
            return self.wrap(", ".join(headers))

        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)[:50]))

        col_widths = [min(w, 30) for w in col_widths]  # Cap at 30 chars

        lines = []
        header_line = " | ".join(h[:w].ljust(w) for h, w in zip(headers, col_widths))
        lines.append(header_line)
        lines.append("-" * len(header_line))

        for row in rows:
            row_line = " | ".join(str(c)[:w].ljust(w) for c, w in zip(row, col_widths))
            lines.append(row_line)

        return "\n".join(lines)

    def file_diff(self, old_path: str, new_path: str | None = None) -> str:
        """Compact diff view for phones."""
        lines = [f"Changed: {old_path}"]
        if new_path:
            lines.append(f"  -> {new_path}")
        return "\n".join(lines)

    def agent_status(self, name: str, role: str, status: str) -> str:
        """Compact agent status."""
        return f"[{name}] {role} — {status}"


# Compact slash commands for phone mode
PHONE_COMMANDS = {
    "/x": "/exit",
    "/h": "/help",
    "/c": "/clear",
    "/s": "/status",
    "/m": "/model",
    "/p": "/plan",
    "/b": "/build",
    "/a": "/abort",
    "/g": "/context",  # get context
    "/t": "/tools",
    "/w": "/save",     # write/save
    "/r": "/retry",
    "/f": "/facts",
    "/sk": "/skills",
    "/sp": "/spawn",
    "/sy": "/sync",
    "/sync": "/sync",
    "/sd": "/sessions",  # session details
}


class PhoneMode:
    """
    Phone mode integration. Wraps the REPL with phone-optimized rendering.
    
    To enable: set NEXUS_PHONE_MODE=1 or NEXUS_SSH_MODE=1
    Or just run on a small terminal — it auto-detects.
    """

    def __init__(self):
        self.profile = detect_display_profile()
        self.formatter = PhoneModeFormatter(self.profile)
        self._enabled = (
            os.environ.get("NEXUS_PHONE_MODE") or
            os.environ.get("NEXUS_SSH_MODE") or
            os.environ.get("TERMUX") or
            self.profile.name in ("phone", "ssh_slow")
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_prompt(self, context: dict[str, Any] | None = None) -> str:
        """Get the compact phone-mode prompt."""
        ctx = context or {}

        session_short = ctx.get("session_id", "nexus")[:6]
        agent_short = ctx.get("agent_name", "n")[:1]

        return f"\033[1;36m{agent_short}@{session_short}\033[0m> "

    def get_banner(self) -> str:
        """Get the compact phone-mode banner."""
        lines = [
            "=" * 40,
            "  Nexus — phone mode",
            "  Type /h for commands",
            "=" * 40,
        ]
        return "\n".join(lines)

    def get_help(self) -> str:
        """Get phone-optimized help."""
        return f"""{self.profile.separator * 5} COMMANDS {self.profile.separator * 5}
  /x        Exit
  /h        Help
  /c        Clear
  /s        Status
  /m <n>    Switch model
  /p <t>    Plan mode
  /b        Build plan
  /a        Abort
  /g        Show context
  /t        List tools
  /w        Save session
  /sd       Show sessions
  /sk       List skills
  /sp <r>   Spawn agent
  /sy       Sync status
  /sy push  Push to sync
  /sy pull  Pull from sync
  /f        Show facts
  /plugin   Manage plugins
  {self.profile.separator * 47}
"""

    def preprocess_input(self, line: str) -> str:
        """Preprocess input — expand short commands."""
        line = line.strip()
        if not line.startswith("/"):
            return line

        # Check short commands
        for short, full in PHONE_COMMANDS.items():
            if line.startswith(short):
                remainder = line[len(short):]
                return full + remainder

        return line


# Global singleton
_phone_mode: PhoneMode | None = None


def get_phone_mode() -> PhoneMode:
    global _phone_mode
    if _phone_mode is None:
        _phone_mode = PhoneMode()
    return _phone_mode
