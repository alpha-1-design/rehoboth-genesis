"""Shadow Indexer - Proactive background learning system for Nexus.

Creeps through the workspace over time to understand the tech stack,
project architecture, and user coding patterns.
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Any, List

from ..memory import Memory, get_memory, ProjectIndexer
from ..utils import sanitize_error

class ShadowIndexer:
    """Background task that proactively learns about the codebase."""

    def __init__(self, memory: Memory | None = None):
        self.memory = memory or get_memory()
        self.indexer = ProjectIndexer(self.memory)
        self.running = False
        self._task: asyncio.Task | None = None
        self._scan_interval = 300  # Scan every 5 minutes
        self._files_per_chunk = 5   # Process 5 files at a time to stay lightweight

    def start(self):
        """Start the shadow indexing process."""
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._run_loop())

    def stop(self):
        """Stop the shadow indexing process."""
        self.running = False
        if self._task:
            self._task.cancel()

    async def _run_loop(self):
        """Main background loop."""
        while self.running:
            try:
                # 1. Global Workspace Sweep
                await self._global_workspace_sweep()

                # 2. Deep Learn - Chunked File Analysis
                await self._learn_codebase_patterns()

                # 3. Generate Proactive Insights
                await self._generate_proactive_insights()

                # Wait for next cycle
                await asyncio.sleep(self._scan_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                pass

    async def _global_workspace_sweep(self):
        """Scan the entire home directory for projects."""
        home = Path.home()
        projects = []
        # Look for directories with .git, pyproject.toml, or package.json
        for path in home.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                if (path / ".git").exists() or (path / "pyproject.toml").exists() or (path / "package.json").exists():
                    projects.append(str(path))

        self.memory.add_fact("workspace_projects", projects, category="architecture", confidence=1.0)

    async def _generate_proactive_insights(self):
        """Analyze gathered facts to suggest improvements."""
        facts = self.memory.get_facts_by_category("coding_patterns")
        tech = self.memory.get_facts_by_category("tech_stack")

        insights = []
        # Logic to cross-reference facts
        # Example: If Python but no Ruff config
        projects = self.memory.get_fact("workspace_projects")
        if projects and isinstance(projects.value, list):
            for p in projects.value[:3]: # Only analyze first 3
                if not os.path.exists(os.path.join(p, "pyproject.toml")):
                    insights.append(f"Project '{os.path.basename(p)}' is missing a pyproject.toml. Should we standardize it?")

        if insights:
            self.memory.add_fact("proactive_insights", insights, category="proactive", confidence=0.9)

    async def _analyze_file_style(self, path: str):
        """Analyze a small chunk of files to infer project patterns."""
        all_files = self.indexer._index.get("files", [])
        if not all_files:
            return

        # Pick a random chunk of files to analyze
        import random
        chunk = random.sample(all_files, min(len(all_files), self._files_per_chunk))
        
        for file_info in chunk:
            path = file_info.get("path")
            if not path or not os.path.exists(path):
                continue
            
            # Analyze patterns (indentation, naming conventions, imports)
            await self._analyze_file_style(path)

    async def _analyze_file_style(self, path: str):
        """Infer style facts from a file."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            # 1. Indentation Check
            if "\t" in content[:1000]:
                self.memory.add_fact("coding_style_indent", "tabs", category="coding_patterns", confidence=0.8)
            elif "    " in content[:1000]:
                self.memory.add_fact("coding_style_indent", "4 spaces", category="coding_patterns", confidence=0.8)
            
            # 2. Naming Conventions (Python specific)
            if path.endswith(".py"):
                if "_" in content[:2000] and not any(c.isupper() for c in content[:2000] if c.isalpha()):
                    self.memory.add_fact("coding_style_naming", "snake_case", category="coding_patterns", confidence=0.7)
                elif any(c.isupper() for c in content[:2000] if c.isalpha() and not c.islower()):
                    self.memory.add_fact("coding_style_naming", "mixed/camelCase", category="coding_patterns", confidence=0.7)

            # 3. Library Usage
            if "import pandas" in content:
                self.memory.add_fact("tech_stack_data", "pandas", category="tech_stack", confidence=0.9)
            if "import torch" in content or "import tensorflow" in content:
                self.memory.add_fact("tech_stack_ml", "active", category="tech_stack", confidence=0.9)

        except Exception:
            pass

# Global instance
_shadow_indexer: ShadowIndexer | None = None

def get_shadow_indexer() -> ShadowIndexer:
    global _shadow_indexer
    if _shadow_indexer is None:
        _shadow_indexer = ShadowIndexer()
    return _shadow_indexer
