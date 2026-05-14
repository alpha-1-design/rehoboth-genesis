"""Nexus Steward — Environment-aware code and security guardian."""

import os
import shutil
import subprocess
from pathlib import Path
import re

class NexusSteward:
    """The silent, powerful guardian of the Nexus codebase."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.secrets_patterns = [
            re.compile(r"(sk-[a-zA-Z0-9]{20,})"),
            re.compile(r"(ghp_[a-zA-Z0-9]{36})"),
            re.compile(r"(AIza[0-9A-Za-z-_]{35})")
        ]

    def _is_git_repo(self) -> bool:
        return (self.workspace / ".git").exists()

    def get_status(self) -> str:
        if not self._is_git_repo():
            return "No repository detected."
        return subprocess.check_output(["git", "status", "--short"], cwd=self.workspace).decode()

    def check_for_secrets(self, path: Path) -> list[str]:
        """Scan file for potential secrets."""
        violations = []
        if path.is_file():
            with open(path, "r", errors="ignore") as f:
                content = f.read()
                for pattern in self.secrets_patterns:
                    if pattern.search(content):
                        violations.append(str(path))
        return violations

    def propose_commit(self, message: str) -> bool:
        """Intelligently manage git commits after safety verification."""
        if not self._is_git_repo():
            return False
            
        # 1. Scan for secrets in staging area
        staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=self.workspace).decode().splitlines()
        for path in staged:
            if self.check_for_secrets(self.workspace / path):
                print(f"[!] SECURITY BLOCK: Secret detected in {path}. Aborting commit.")
                return False
        
        # 2. Perform silent commit
        try:
            subprocess.run(["git", "commit", "-m", message], cwd=self.workspace, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def create_github_issue(self, title: str, body: str):
        """Interact with GitHub CLI silently if available."""
        if shutil.which("gh"):
            subprocess.run(["gh", "issue", "create", "-t", title, "-b", body], cwd=self.workspace)
