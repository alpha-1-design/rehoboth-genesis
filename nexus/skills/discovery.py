"""Skill Discovery - Nexus explores its own environment and registers capabilities."""

import shutil
from pathlib import Path


class SkillDiscoverer:
    """Probes the environment to discover and suggest new skills."""

    def __init__(self, nexus_dir: Path):
        self.nexus_dir = nexus_dir
        self.skills_dir = nexus_dir / "skills"
        self.known_tools = {"docker": "docker-manager", "node": "node-dev-tool", "rustc": "rust-expert", "pytest": "test-runner", "sqlite3": "db-admin"}

    def discover(self):
        """Scan system and propose new skills."""
        print("\n[Nexus] Scanning environment for new skills...")
        discovered = []
        for tool, skill in self.known_tools.items():
            if shutil.which(tool):
                if not (self.skills_dir / f"{skill}.py").exists():
                    discovered.append((tool, skill))

        if discovered:
            print(f"[!] Found new capabilities: {[d[0] for d in discovered]}")
            for tool, skill in discovered:
                if input(f"Register skill '{skill}' for {tool}? [y/n]: ").lower() == "y":
                    self._register_skill(skill)
        else:
            print("[✓] No new skills discovered. All known tools integrated.")

    def _register_skill(self, skill_name: str):
        """Simulate registration of a new skill."""
        (self.skills_dir / f"{skill_name}.py").touch()
        print(f"[✓] Skill {skill_name} registered successfully.")
