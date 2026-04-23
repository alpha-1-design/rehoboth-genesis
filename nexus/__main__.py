"""Nexus CLI entry point."""

import sys
from pathlib import Path

# Add nexus to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus.cli import main

def main():
    """Main entry point for the Nexus CLI."""
    try:
        from nexus.cli import main as cli_main
        cli_main()
    except ImportError:
        print("\n\033[91m[CRITICAL ERROR] Package 'nexus' not found in Python path.\033[0m")
        print("\nThis usually happens when the project is moved to a 'src' layout")
        print("without being installed.")
        print("\n\033[1mFIX:\033[0m Run the following command in the project root:")
        print("\033[92mpip install -e .\033[0m\n")
        sys.exit(1)
    except Exception:
        print("\n\033[91m[FATAL] Unexpected system failure\033[0m")
        print("Please check your configuration and try again.")
        sys.exit(1)

>>>>>>> 8b77f00 (feat: implement dynamic ReAct loop and enhance CLI/TUI)

if __name__ == "__main__":
    main()
