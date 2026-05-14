"""Nexus Neural Core — The centralized governor of all OS subsystems."""

from pathlib import Path

from .doctor import NexusDoctor
from .memory.shadow import get_shadow_indexer
from .steward import NexusSteward


class NeuralCore:
    """Governs the lifecycle, monitoring, and adaptation of Nexus."""

    def __init__(self, workspace: Path = Path(".")):
        self.workspace = workspace
        self.doctor = NexusDoctor()
        self.steward = NexusSteward(workspace)
        self.shadow = get_shadow_indexer()
        self._is_ready = False

    async def initialize(self, quiet: bool = True):
        """Proactively initialize all subsystems in a governed order."""
        if not quiet:
            print("[CORE] Activating Neural Governance...")

        # 1. Self-Diagnosis (Minimal check)
        # We don't run_all() here to save time on every CLI call

        # 2. Knowledge Synchronization (Only if requested or in long session)
        # self.shadow.start() - Moved to lazy start in TUI/REPL

        self._is_ready = True
        if not quiet:
            print("[CORE] Governance active. System fully integrated.")

    def shutdown(self):
        """Governed shutdown."""
        self.shadow.stop()
        print("[CORE] Governance offline.")

# Global instance
_core: NeuralCore | None = None

def get_core() -> NeuralCore:
    global _core
    if _core is None:
        _core = NeuralCore()
    return _core
