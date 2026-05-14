"""Dependency Guard - Handles just-in-time installation of missing libraries."""

import importlib
import os
import subprocess
import sys


def is_termux() -> bool:
    """Check if we are running in Termux."""
    return os.path.exists("/data/data/com.termux/files/usr/bin/termux-setup-storage")


def get_env_warning(package_name: str) -> str | None:
    """Return a warning message if the environment might be incompatible with the package."""
    if is_termux():
        if package_name in ("playwright", "playwright-python"):
            return "Playwright requires a full browser engine which is often unstable or non-functional in standard Termux environments."
        if package_name in ("faster-whisper", "whisper"):
            return "Whisper models are computationally heavy and may cause high CPU usage or crashes on mobile devices."
        if package_name in ("pyaudio",):
            return "PyAudio requires system-level audio headers (portaudio) which can be tricky to configure in Termux."
    return None


def ensure_dependency(package_name: str, import_name: str | None = None) -> bool:
    """Checks if a package is installed, offers to install if missing."""
    import_name = import_name or package_name
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        cyan = "\033[36m"
        blue = "\033[34m"
        yellow = "\033[33m"
        red = "\033[31m"
        bold = "\033[1m"
        reset = "\033[0m"
        dim = "\033[90m"

        print(f"\n  {blue}╼{reset} {cyan}nexus/system{reset} {bold}module '{package_name}' missing{reset}")

        warning = get_env_warning(package_name)
        if warning:
            print(f"    {yellow}⚠ WARNING:{reset} {warning}")
            choice = input(f"    {bold}Proceed anyway?{reset} (y/N): ").strip().lower()
            if choice not in ("y", "yes"):
                print(f"    {dim}Aborting installation for safety.{reset}")
                return False

            print(f"    {red}Nexus:{reset} {bold}Don't say I didn't warn you...{reset}")

        choice = input(f"    {bold}Initialize extension?{reset} (y/N): ").strip().lower()

        if choice in ("y", "yes"):
            print(f"    {dim}Installing {package_name}...{reset}")
            try:
                # Use --no-cache-dir and other flags if helpful for mobile
                cmd = [sys.executable, "-m", "pip", "install", package_name]
                subprocess.check_call(cmd)
                print(f"    {blue}✔{reset} {package_name} initialized. Restarting module...")
                return True
            except Exception as e:
                print(f"    {blue}✘{reset} Installation failed: {e}")
                return False
        return False
