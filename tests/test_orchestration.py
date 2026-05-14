
import pytest
from nexus.agent import get_orchestrator

def test_orchestrator_singleton():
    """Verify that get_orchestrator returns the same instance (singleton)."""
    orch1 = get_orchestrator()
    orch2 = get_orchestrator()
    assert orch1 is orch2

def test_orchestrator_initialization():
    """Verify orchestrator is initialized correctly."""
    orch = get_orchestrator()
    assert orch is not None
    assert orch.pm is not None
    assert orch.tools is not None
    assert orch.memory is not None
