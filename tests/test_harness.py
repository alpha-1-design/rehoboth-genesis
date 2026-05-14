"""Sanity Fire - Core integrity tests for the Nexus Harness."""

import pytest

from nexus.cli.repl import REPL
from nexus.safety import SafetyMode, get_safety_engine


def test_safety_engine_initialization():
    """Verify that the Safety Engine boots in USER_REVIEW mode."""
    safety = get_safety_engine()
    assert safety.get_mode() == SafetyMode.USER_REVIEW

def test_safety_mode_switching():
    """Verify that switching safety modes updates the Harness state."""
    safety = get_safety_engine()
    safety.set_mode(SafetyMode.READ_ONLY)
    assert safety.get_mode() == SafetyMode.READ_ONLY

    # Switch back
    safety.set_mode(SafetyMode.USER_REVIEW)
    assert safety.get_mode() == SafetyMode.USER_REVIEW

def test_read_before_edit_rule():
    """Verify that the Harness enforces the 'Read Before Edit' rule."""
    safety = get_safety_engine()
    # Mock a context where a file is being edited without being read
    context = {"tool": "edit", "path": "non_existent_file.py"}
    violations = safety.check(context)

    # It should have at least one violation for reading before editing
    assert any(v.rule.id == "read-before-edit" for v in violations)

@pytest.mark.asyncio
async def test_refiners_fire_syntax_check(tmp_path):
    """Verify that the Refiner's Fire catches syntax impurities."""
    repl = REPL()

    # Create a file with invalid syntax
    bad_file = tmp_path / "impure.py"
    bad_file.write_text("def unclosed_function(:", encoding="utf-8")

    passed, error = await repl._run_refiners_fire(str(bad_file))
    assert passed is False
    assert "Syntax Error" in error

@pytest.mark.asyncio
async def test_refiners_fire_solid_work(tmp_path):
    """Verify that solid work stands the fire."""
    repl = REPL()

    # Create a file with valid syntax
    good_file = tmp_path / "solid.py"
    good_file.write_text("def solid_work():\n    return True", encoding="utf-8")

    passed, error = await repl._run_refiners_fire(str(good_file))
    assert passed is True
    assert error is None
