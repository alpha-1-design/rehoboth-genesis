"""Nexus Doctor — Self-diagnostic and system health monitor."""

import os
import shutil
import json
import sys
from typing import Dict, Any
from .config import load_config, save_config, ProviderConfig, NexusConfig
from .steward import NexusSteward
from pathlib import Path

class NexusDoctor:
    """Performs deep diagnostics and environment health checks."""

    def __init__(self):
        self.config = load_config()
        self.steward = NexusSteward(Path("."))
        self.health_checks = {
            "dependencies": self._check_dependencies,
            "environment": self._check_environment,
            "config": self._check_config,
            "git": self._check_git,
            "cache": self._check_cache,
        }

    def _check_cache(self) -> Dict[str, Any]:
        """Check for non-essential cache files that can be cleaned."""
        targets = {
            "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
            ".tox", ".ipynb_checkpoints", ".eslintcache", ".DS_Store"
        }
        found = []
        total_size = 0
        
        for root, dirs, files in os.walk("."):
            # Prune directories in place to skip them entirely
            if ".git" in dirs:
                dirs.remove(".git")
            
            # Special case for node_modules: we only care about .cache inside it
            if "node_modules" in dirs:
                cache_path = Path(root) / "node_modules" / ".cache"
                if cache_path.exists():
                    found.append(str(cache_path))
                    for f in cache_path.rglob('*'):
                        if f.is_file():
                            total_size += f.stat().st_size
                dirs.remove("node_modules")

            for target in targets:
                if target in dirs:
                    path = Path(root) / target
                    found.append(str(path))
                    for f in path.rglob('*'):
                        if f.is_file():
                            total_size += f.stat().st_size
                    # Don't descend into the target we just found
                    if target in dirs:
                        dirs.remove(target)
                
                if target in files:
                    path = Path(root) / target
                    found.append(str(path))
                    total_size += path.stat().st_size
        
        return {
            "passed": total_size < 100 * 1024 * 1024, # Pass if less than 100MB
            "found_count": len(found),
            "total_size_bytes": total_size,
            "paths": found[:10],
            "all_paths": found
        }

    def tactical_cleanup(self, dry_run: bool = True) -> Dict[str, Any]:
        """Scans and removes non-essential cache artifacts to free space."""
        report = self._check_cache()
        all_paths = report.get("all_paths", [])
        total_size = report.get("total_size_bytes", 0)
        
        if not dry_run:
            for path_str in all_paths:
                path = Path(path_str)
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                except Exception:
                    pass
        
        from .utils import format_bytes
        return {
            "freed_bytes": total_size if not dry_run else 0,
            "potential_savings": format_bytes(total_size),
            "files_removed": len(all_paths) if not dry_run else 0,
            "dry_run": dry_run
        }
    
    def _check_git(self) -> Dict[str, Any]:
        """Check if environment is a git repo."""
        return {"passed": self.steward._is_git_repo(), "status": self.steward.get_status().strip() or "Clean"}

    def run_all(self) -> Dict[str, Any]:
        results = {}
        for name, check in self.health_checks.items():
            results[name] = check()
        return results

    def discover_skills(self):
        """Invoke skill discovery."""
        from .skills.discovery import SkillDiscoverer
        discoverer = SkillDiscoverer(self.config.config_dir.parent)
        discoverer.discover()

    def _check_dependencies(self) -> Dict[str, Any]:
        """Verify essential tools are present."""
        required = {"textual": "textual", "requests": "requests", "openai": "openai"}
        details = {}
        for pkg, pip_name in required.items():
            try:
                import importlib
                importlib.import_module(pkg)
                details[pkg] = True
            except ImportError:
                details[pkg] = False
        return {"passed": all(details.values()), "details": details}

    def _check_environment(self) -> Dict[str, Any]:
        """Check environment constraints."""
        return {"os": os.name, "writable": os.access(".", os.W_OK)}

    def _check_config(self) -> Dict[str, Any]:
        """Check if providers are configured."""
        return {"configured": len(self.config.providers) > 0}

    def interactive_setup(self):
        """Guide the user through provider configuration."""
        print("\n[!] Nexus configuration not found. Let's configure your agent.")
        providers = [
            {"name": "OpenAI", "type": "openai", "model": "gpt-4o"},
            {"name": "Groq", "type": "groq", "model": "llama-3.3-70b-versatile"},
            {"name": "Anthropic", "type": "anthropic", "model": "claude-3-5-sonnet-latest"},
            {"name": "Google Gemini", "type": "google", "model": "gemini-2.0-flash"}
        ]
        
        print("Select an AI provider:")
        for i, p in enumerate(providers):
            print(f"{i+1}. {p['name']} (Recommended: {p['model']})")
        
        choice = input("Enter choice (1-4): ")
        if not choice.isdigit() or int(choice) not in range(1, 5):
            print("Invalid selection. Using default environment configuration.")
            return

        p = providers[int(choice)-1]
        key = input(f"Enter your {p['name']} API key: ")
        
        # Save to persistent config
        new_provider = ProviderConfig(
            name=p['type'],
            provider_type=p['type'],
            api_key=key,
            model=p['model']
        )
        self.config.providers[p['type']] = new_provider
        self.config.active_provider = p['type']
        save_config(self.config)
        
        print(f"\n[✓] Nexus is now bound to {p['name']}.")

def run_doctor(interactive: bool = True):
    doctor = NexusDoctor()
    report = doctor.run_all()
    print("\n" + "─"*50)
    print("NEXUS SYSTEM DIAGNOSTICS")
    print("─"*50)
    for category, result in report.items():
        status = "[OK]" if result.get("passed", True) else "[!] "
        print(f"{status} {category.upper()}")
        if category == "cache" and result.get("found_count", 0) > 0:
            from .utils import format_bytes
            size = format_bytes(result['total_size_bytes'])
            print(f"    -> {result['found_count']} artifacts found ({size} potential savings)")
    
    if interactive and not report["config"]["configured"]:
        doctor.interactive_setup()
    
    doctor.discover_skills()
    print("─"*50 + "\n")
