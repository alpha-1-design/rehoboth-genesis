"""Nexus CLI entry point."""

import asyncio
import sys
from pathlib import Path

# Add nexus to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Main entry point for the Nexus CLI."""
    try:
        # 1. Governance Initialization
        from nexus.core import get_core

        core = get_core()
        asyncio.run(core.initialize())

        from nexus.cli import main as cli_main

        cli_main()
    except ImportError:
        print("\n\033[91m[CRITICAL ERROR] Package 'nexus' not found in Python path.\033[0m")
        sys.exit(1)
    except Exception as e:
        print(f"\n\033[91m[FATAL] Unexpected system failure: {e}\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    main()
