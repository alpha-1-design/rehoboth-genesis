"""Termux API wrapper for Nexus.

Provides a clean interface to Termux API tools.
Detects Termux environment automatically.
"""

import asyncio
import json
import os
import subprocess
from typing import Any


class TermuxAPI:
    """Interface to Termux API tools.

    All methods return tuples of (success: bool, result: str).
    Gracefully degrade on non-Termux platforms.
    """

    def __init__(self):
        self._termux_available = self._detect_termux()
        self._cache: dict[str, tuple[bool, Any]] = {}

    def _detect_termux(self) -> bool:
        """Detect if running in Termux."""
        return os.path.exists("/data/data/com.termux") or os.environ.get("TERMUX_VERSION") or os.path.exists("/system/bin/termux-api")

    @property
    def is_available(self) -> bool:
        return self._termux_available

    def _run(self, command: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run a Termux API command. Returns (success, output)."""
        if not self._termux_available:
            return False, "Termux not available"

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip() or f"Exit code: {result.returncode}"
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except FileNotFoundError:
            return False, f"Command not found: {command[0]}"
        except Exception as e:
            return False, str(e)

    async def _arun(self, command: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Async version of _run."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._run(command, timeout))

    # === Clipboard ===

    def clipboard_get(self) -> tuple[bool, str]:
        """Get clipboard content."""
        return self._run(["termux-clipboard-get"])

    def clipboard_set(self, text: str) -> tuple[bool, str]:
        """Set clipboard content."""
        return self._run(["termux-clipboard-set", text])

    # === Notifications ===

    def notify(self, title: str, content: str, id: int = 0, sound: bool = True, priority: str = "default") -> tuple[bool, str]:
        """Show a notification.

        Args:
            title: Notification title
            content: Notification body
            id: Notification ID (replaces existing notification with same ID)
            sound: Play sound
            priority: "low", "default", "high"
        """
        cmd = [
            "termux-notification",
            "--title",
            title,
            "--text",
            content,
            "--id",
            str(id),
            sound and "--sound" or "--no-sound",
            "--priority",
            priority,
        ]
        return self._run(cmd)

    def notify_complete(self, task: str, duration: str = "") -> tuple[bool, str]:
        """Notify task completion."""
        msg = f"Done: {task}"
        if duration:
            msg += f" ({duration})"
        return self.notify("Nexus Complete", msg, priority="default")

    def notify_error(self, error: str) -> tuple[bool, str]:
        """Notify an error."""
        return self.notify("⚠️ Nexus Error", error, priority="high")

    def remove_notification(self, id: int) -> tuple[bool, str]:
        """Remove a notification by ID."""
        return self._run(["termux-notification-remove", str(id)])

    # === Battery ===

    def battery_status(self) -> tuple[bool, dict[str, Any]]:
        """Get battery status."""
        success, output = self._run(["termux-battery-status"])
        if success:
            try:
                return True, json.loads(output)
            except json.JSONDecodeError:
                return False, "Invalid JSON response"
        return False, output

    # === WiFi ===

    def wifi_status(self) -> tuple[bool, dict[str, Any]]:
        """Get WiFi status."""
        success, output = self._run(["termux-wifi-connectioninfo"])
        if success:
            try:
                return True, json.loads(output)
            except json.JSONDecodeError:
                return False, "Invalid JSON response"
        return False, output

    # === Share ===

    def share(self, text: str | None = None, file: str | None = None, title: str = "Nexus Share") -> tuple[bool, str]:
        """Share text or a file."""
        cmd = ["termux-share", "--title", title]
        if text:
            cmd.extend(["--text", text])
        if file:
            cmd.extend(["--file", file])
        return self._run(cmd)

    # === Sensors ===

    def sensors_list(self) -> tuple[bool, str]:
        """List available sensors."""
        return self._run(["termux-sensor", "-l"])

    def sensor_read(self, sensor: str, duration: int = 5) -> tuple[bool, str]:
        """Read a sensor for specified duration (seconds)."""
        return self._run(["termux-sensor", "-s", sensor, "-d", str(duration)])

    # === Camera ===

    def camera_photo(self, file: str) -> tuple[bool, str]:
        """Take a photo with the camera."""
        return self._run(["termux-camera-photo", file])

    # === SMS ===

    def sms_list(self, limit: int = 10) -> tuple[bool, str]:
        """List recent SMS messages."""
        return self._run(["termux-sms-list", "-l", str(limit)])

    def sms_send(self, number: str, message: str) -> tuple[bool, str]:
        """Send an SMS."""
        return self._run(["termux-sms-send", "-n", number, "--", message])

    # === Downloads ===

    def download(self, url: str, filename: str | None = None) -> tuple[bool, str]:
        """Download a file."""
        cmd = ["termux-download", url]
        if filename:
            cmd.extend(["-f", filename])
        return self._run(cmd)

    # === Job Scheduler ===

    def job_schedule(self, script: str, period_ms: int = 60000, after: int = 0) -> tuple[bool, str]:
        """Schedule a recurring job."""
        cmd = [
            "termux-job-scheduler",
            "--script",
            script,
            "--period",
            str(period_ms),
            "--after",
            str(after),
        ]
        return self._run(cmd)

    def job_unschedule(self) -> tuple[bool, str]:
        """Unschedule all jobs."""
        return self._run(["termux-job-scheduler", "--unschedule"])


# Singleton
_termux_api: TermuxAPI | None = None


def get_termux_api() -> TermuxAPI:
    global _termux_api
    if _termux_api is None:
        _termux_api = TermuxAPI()
    return _termux_api
