"""Stability Gate for Nexus Evolution.
Verifies that proposed core changes do not degrade system stability or a professional DX.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StabilityResult:
    passed: bool
    report: str
    metrics: dict


class StabilityGate:
    """
    Executes a series of 'Torture Tests' and static analysis to validate
    proposed code changes before they are merged into the core.
    """

    def __init__(self, workspace_path: Path):
        self.workspace = workspace_path

    async def verify(self) -> StabilityResult:
        """
        Run the full stability suite.
        Returns a StabilityResult indicating if the evolution is safe to merge.
        """
        results = []

        # 1. Syntax Check (The most basic gate)
        syntax_ok, syntax_log = self._check_syntax()
        results.append(f"Syntax Check: {'✓' if syntax_ok else '✗'}")
        if not syntax_ok:
            return StabilityResult(False, f"Syntax Error: {syntax_log}", {})

        # 2. DX Stress Test (Verify 'Senior Engineer' voice and Orchestration Lock)
        dx_ok, dx_log = self._run_dx_stress_test()
        results.append(f"DX Stress Test: {'✓' if dx_ok else '✗'}")
        if not dx_ok:
            return StabilityResult(False, f"DX Violation: {dx_log}", {})

        # 3. Core Regression Tests (Pytest)
        test_ok, test_log = self._run_pytest()
        results.append(f"Core Regression: {'✓' if test_ok else '✗'}")
        if not test_ok:
            return StabilityResult(False, f"Regression Detected: {test_log}", {})

        return StabilityResult(passed=True, report="\n".join(results), metrics={"status": "STABLE"})

    def _check_syntax(self) -> tuple[bool, str]:
        """Compile-check all python files in the core."""
        try:
            # Find all python files in src/nexus
            import glob

            files = glob.glob("src/nexus/**/*.py", recursive=True)
            for f in files:
                subprocess.run([sys.executable, "-m", "py_compile", f], check=True, capture_output=True)
            return True, "All files compile."
        except subprocess.CalledProcessError as e:
            return False, e.stderr.decode()

    def _run_dx_stress_test(self) -> tuple[bool, str]:
        """Run the professional standard verification suite."""
        try:
            # We use the specific DX stress test script we built
            # Setting PYTHONPATH to ensure it can find the core logic
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{self.workspace}/src"

            result = subprocess.run(
                [sys.executable, "tests/dx_stress_test.py"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            # The stress test prints '✓' for each pass
            if "✓" in result.stdout and "✗" not in result.stdout:
                return True, "DX standards maintained."
            return False, result.stdout or result.stderr
        except Exception as e:
            return False, str(e)

    def _run_pytest(self) -> tuple[bool, str]:
        """Run the standard pytest suite."""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{self.workspace}/src"
            result = subprocess.run(["pytest", "tests/"], capture_output=True, text=True, env=env, timeout=60)
            return result.returncode == 0, result.stdout or result.stderr
        except Exception as e:
            return False, str(e)
