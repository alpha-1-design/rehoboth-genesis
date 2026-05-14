"""Core tools for Nexus - filesystem, shell, web, and more."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

from .diff_tool import InteractiveDiffTool

from ..utils import sanitize_error
from .base import BaseTool, ToolDefinition, ToolRegistry, ToolResult


class ReadTool(BaseTool):
    """Read file contents."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description="Read the contents of a file. Use this to view files in the project.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file to read",
                    },
                    "limit": {"type": "integer", "description": "Maximum number of lines to read"},
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed)",
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
        )

    async def execute(
        self, path: str, limit: int | None = None, offset: int | None = None, **kwargs
    ) -> ToolResult:
        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(success=False, content="", error=f"File not found: {path}")

            if not file_path.is_file():
                return ToolResult(success=False, content="", error=f"Not a file: {path}")

            with open(file_path, encoding="utf-8", errors="replace") as f:
                if offset:
                    lines = f.readlines()[offset - 1 :]
                else:
                    lines = f.readlines()

                if limit:
                    lines = lines[:limit]

                content = "".join(lines)

            return ToolResult(success=True, content=content)
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class WriteTool(BaseTool):
    """Write content to a file."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write",
            description="Create a new file or overwrite an existing file with the given content.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to write"},
                    "content": {"type": "string", "description": "Content to write to the file"},
                },
                "required": ["path", "content"],
            },
            requires_permission=True,
            category="filesystem",
        )

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                content=f"File written successfully: {path}",
                metadata={"bytes_written": len(content.encode("utf-8"))},
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class EditTool(BaseTool):
    """Edit a file by replacing exact text with context verification."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit",
            description="Edit a file by replacing exact text. Use 'before' and 'after' context strings to ensure the correct location is modified and to handle duplicate text in the file.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to edit"},
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to replace",
                    },
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "before": {
                        "type": "string",
                        "description": "Text immediately preceding old_string for context",
                    },
                    "after": {
                        "type": "string",
                        "description": "Text immediately following old_string for context",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
            requires_permission=True,
            category="filesystem",
        )

    async def execute(self, path: str, old_string: str, new_string: str, before: str = "", after: str = "", **kwargs) -> ToolResult:
        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(success=False, content="", error=f"File not found: {path}")

            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            full_old_text = before + old_string + after
            
            if full_old_text not in content:
                # Provide helpful debugging info if match fails
                if old_string not in content:
                    return ToolResult(success=False, content="", error=f"Target text 'old_string' not found in {path}.")
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Context mismatch. 'old_string' was found, but the surrounding 'before' or 'after' context did not match exactly.",
                )

            # Check for multiple occurrences of the full context block
            count = content.count(full_old_text)
            if count > 1:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Ambiguous edit: found {count} occurrences of the provided context block. Please provide more 'before' or 'after' context.",
                )

            new_full_text = before + new_string + after
            new_content = content.replace(full_old_text, new_full_text, 1)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                content=f"Edit applied successfully to {path}",
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class GlobTool(BaseTool):
    """Find files matching a glob pattern."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="glob",
            description="Find files matching a glob pattern. Useful for discovering files in the project.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match (e.g., '**/*.py', 'src/**/*.ts')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (defaults to current directory)",
                    },
                },
                "required": ["pattern"],
            },
            category="filesystem",
        )

    async def execute(self, pattern: str, path: str | None = None, **kwargs) -> ToolResult:
        try:
            search_path = Path(path) if path else Path.cwd()

            matches = list(search_path.glob(pattern))

            if not matches:
                return ToolResult(success=True, content="No files found matching pattern.")

            paths = [str(m.absolute()) for m in matches]
            return ToolResult(
                success=True,
                content=f"Found {len(paths)} file(s):\n" + "\n".join(paths),
                metadata={"files": paths},
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class GrepTool(BaseTool):
    """Search for text in files using regex."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="grep",
            description="Search for text in files using regular expressions. Matches lines containing the pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression pattern to search for",
                    },
                    "path": {"type": "string", "description": "Directory or file to search in"},
                    "include": {
                        "type": "string",
                        "description": "Only search in files matching this pattern (e.g., '*.py')",
                    },
                    "outputMode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "Output format",
                    },
                    "case_sensitive": {"type": "boolean", "description": "Case sensitive search"},
                },
                "required": ["pattern"],
            },
            category="filesystem",
        )

    async def execute(
        self,
        pattern: str,
        path: str | None = None,
        include: str | None = None,
        output_mode: str = "content",
        case_sensitive: bool = True,
        **kwargs,
    ) -> ToolResult:
        try:
            search_path = Path(path) if path else Path.cwd()

            cmd = ["rg", "--json"]
            if not case_sensitive:
                cmd.append("-i")

            if output_mode == "count":
                cmd.extend(["-c"])
            elif output_mode == "files_with_matches":
                cmd.append("-l")

            if include:
                cmd.extend(["-g", include])

            cmd.extend(["--", pattern, str(search_path)])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=search_path,
            )

            if result.returncode == 1:
                return ToolResult(success=True, content="No matches found.")

            if result.returncode != 0:
                return ToolResult(success=False, content="", error=result.stderr)

            if output_mode == "files_with_matches":
                files = [line.split(":")[0] for line in result.stdout.strip().split("\n") if line]
                return ToolResult(
                    success=True,
                    content=f"Found {len(files)} file(s) with matches:\n" + "\n".join(set(files)),
                    metadata={"files": list(set(files))},
                )

            if output_mode == "count":
                return ToolResult(success=True, content=result.stdout)

            return ToolResult(success=True, content=result.stdout)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                content="",
                error="ripgrep (rg) not found. Install with: pip install ripgrep",
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class ListTool(BaseTool):
    """List directory contents."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list",
            description="List files and directories at a path.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to list (defaults to current directory)",
                    },
                },
            },
            category="filesystem",
        )

    async def execute(self, path: str | None = None, **kwargs) -> ToolResult:
        try:
            list_path = Path(path) if path else Path.cwd()

            if not list_path.exists():
                return ToolResult(success=False, content="", error=f"Path does not exist: {path}")

            items = []
            for item in sorted(list_path.iterdir()):
                icon = "[dir]" if item.is_dir() else "[file]"
                items.append(f"{icon} {item.name}")

            if not items:
                return ToolResult(success=True, content="(empty directory)")

            return ToolResult(
                success=True,
                content="\n".join(items),
                metadata={"path": str(list_path.absolute())},
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class BashTool(BaseTool):
    """Execute shell commands."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="bash",
            description="Execute a shell command. Use for running scripts, build tools, git, and other command-line tools.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Working directory for the command",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of what this command does",
                    },
                },
                "required": ["command"],
            },
            requires_permission=True,
            category="execution",
        )

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        workdir: str | None = None,
        description: str | None = None,
        **kwargs,
    ) -> ToolResult:
        # Check safety first
        from ..safety import get_safety_engine
        safety = get_safety_engine()
        context = {"tool": "bash", "command": command}
        violations = safety.check(context)
        proceed, reason = safety.should_proceed(violations)
        
        if not proceed:
            return ToolResult(success=False, content="", error=reason)

        try:
            cwd = workdir if workdir else os.getcwd()
            # If in sandbox mode, enforce directory restriction
            if safety.get_mode() == "sandbox":
                # Implementation of restricted chroot/shell jail would go here
                pass

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Command timed out after {timeout} seconds",
                )

            output = []
            if stdout:
                output.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output.append(f"[stderr]\n{stderr.decode('utf-8', errors='replace')}")

            result = "\n".join(output) if output else ""

            if process.returncode != 0 and not result:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Command failed with exit code {process.returncode}",
                )

            return ToolResult(
                success=process.returncode == 0,
                content=result,
                metadata={
                    "exit_code": process.returncode,
                    "command": command,
                },
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class WebFetchTool(BaseTool):
    """Fetch content from a URL."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description="Fetch the content of a web page. Use for retrieving documentation, API responses, or any URL content.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "headers": {"type": "object", "description": "HTTP headers to include"},
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.)",
                        "default": "GET",
                    },
                    "body": {"type": "string", "description": "Request body for POST requests"},
                },
                "required": ["url"],
            },
            requires_permission=True,
            category="web",
        )

    async def execute(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        body: str | None = None,
        **kwargs,
    ) -> ToolResult:
        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                request_headers = headers or {}
                request_headers.setdefault("User-Agent", "Nexus/1.0")

                response = await client.request(
                    method,
                    url,
                    headers=request_headers,
                    content=body.encode() if body else None,
                )

                content = response.text[:50000]

                return ToolResult(
                    success=True,
                    content=f"Status: {response.status_code}\n\n{content}",
                    metadata={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "url": str(response.url),
                    },
                )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class WebSearchTool(BaseTool):
    """Search the web."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description="Search the web for information. Use for finding documentation, tutorials, or answers to questions.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "numResults": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
            category="web",
        )

    async def execute(
        self,
        query: str,
        num_results: int = 8,
        **kwargs,
    ) -> ToolResult:
        try:
            from ..config import load_config

            config = load_config()

            if config.search_provider == "tavily" and config.tavily_api_key:
                return await self._search_tavily(query, num_results, config.tavily_api_key)
            elif config.search_provider == "brave" and config.brave_api_key:
                return await self._search_brave(query, num_results, config.brave_api_key)
            elif config.search_provider == "exa":
                return await self._search_exa(query, num_results, config.exa_api_key)
            else:
                return await self._search_duckduckgo(query, num_results)
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))

    async def _search_exa(self, query: str, num: int, api_key: str | None) -> ToolResult:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "query": query,
                        "numResults": num,
                        "type": "auto",
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("results", []):
                    results.append(
                        f"## {item.get('title', 'Untitled')}\n{item.get('url', '')}\n{item.get('snippet', '')}\n"
                    )

                return ToolResult(
                    success=True,
                    content="\n---\n".join(results) if results else "No results found.",
                    metadata={"provider": "exa"},
                )
        except Exception:
            return await self._search_duckduckgo(query, num)

    async def _search_tavily(self, query: str, num: int, api_key: str) -> ToolResult:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "query": query,
                        "search_depth": "basic",
                        "max_results": num,
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("results", []):
                    results.append(
                        f"## {item.get('title', 'Untitled')}\n{item.get('url', '')}\n{item.get('content', '')}\n"
                    )

                return ToolResult(
                    success=True,
                    content="\n---\n".join(results) if results else "No results found.",
                    metadata={"provider": "tavily"},
                )
        except Exception:
            return await self._search_duckduckgo(query, num)

    async def _search_brave(self, query: str, num: int, api_key: str) -> ToolResult:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                    params={"q": query, "count": num},
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("web", {}).get("results", []):
                    results.append(
                        f"## {item.get('title', 'Untitled')}\n{item.get('url', '')}\n{item.get('description', '')}\n"
                    )

                return ToolResult(
                    success=True,
                    content="\n---\n".join(results) if results else "No results found.",
                    metadata={"provider": "brave"},
                )
        except Exception:
            return await self._search_duckduckgo(query, num)

    async def _search_duckduckgo(self, query: str, num: int) -> ToolResult:
        try:
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=num))
            except ImportError:
                import warnings
                warnings.filterwarnings("ignore", message=".*duckduckgo_search.*")
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=num))

            output = []
            for item in results:
                output.append(
                    f"## {item.get('title', 'Untitled')}\n{item.get('href', '')}\n{item.get('body', '')}\n"
                )

            return ToolResult(
                success=True,
                content="\n---\n".join(output) if output else "No results found.",
                metadata={"provider": "duckduckgo"},
            )
        except ImportError:
            return ToolResult(
                success=False,
                content="",
                error="No search provider configured. Install duckduckgo-search: pip install duckduckgo-search",
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class TodoWriteTool(BaseTool):
    """Create and manage todo lists."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="todowrite",
            description="Create and manage a todo list to track progress on tasks.",
            input_schema={
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "List of todos",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "Todo description"},
                                "status": {
                                    "type": "string",
                                    "enum": ["in_progress", "pending", "completed", "cancelled"],
                                },
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                            },
                        },
                    },
                },
            },
            category="meta",
        )

    async def execute(self, todos: list[dict[str, Any]], **kwargs) -> ToolResult:
        try:
            from ..memory import get_memory

            memory = get_memory()
            memory.save_todos(todos)

            output = []
            for todo in todos:
                status_icon = {
                    "in_progress": "[*]",
                    "pending": "[.]",
                    "completed": "[x]",
                    "cancelled": "[-]",
                }.get(todo.get("status", "pending"), "[*]")
                priority = todo.get("priority", "medium")
                output.append(f"{status_icon} [{priority.upper()}] {todo.get('content', '')}")

            return ToolResult(
                success=True,
                content="Todo list updated:\n\n" + "\n".join(output),
                metadata={"count": len(todos)},
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class QuestionTool(BaseTool):
    """Ask the user a question during execution."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="question",
            description="Ask the user a question. Returns the user's answer.",
            input_schema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "Questions to ask",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "header": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"},
                                        },
                                    },
                                },
                                "multiple": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
            category="meta",
        )

    async def execute(self, questions: list[dict[str, Any]], **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            content="Question asked to user. Awaiting response...",
            metadata={"pending": True, "questions": questions},
        )


class CodeSearchTool(BaseTool):
    """Search for code across the web using semantic search."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="codesearch",
            description="Search for code examples across the web. Use this to find code patterns, library usage examples, or solutions to coding problems.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code search query"},
                    "tokensNum": {
                        "type": "integer",
                        "description": "Number of tokens to return (1000-50000)",
                        "default": 5000,
                    },
                },
                "required": ["query"],
            },
            category="web",
        )

    async def execute(self, query: str, tokens_num: int = 5000, **kwargs) -> ToolResult:
        try:
            from ..config import load_config

            config = load_config()

            if not config.exa_api_key:
                return ToolResult(
                    success=False,
                    content="",
                    error="Exa API key not configured. Set exa_api_key in config.",
                )

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"Authorization": f"Bearer {config.exa_api_key}"},
                    json={
                        "query": query,
                        "numResults": 5,
                        "type": "auto",
                        "category": "github",
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("results", []):
                    results.append(
                        f"## {item.get('title', 'Untitled')}\n{item.get('url', '')}\n{item.get('snippet', '')}\n"
                    )

                return ToolResult(
                    success=True,
                    content="\n---\n".join(results) if results else "No code examples found.",
                    metadata={"provider": "exa"},
                )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class GitTool(BaseTool):
    """Git operations."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git",
            description="Execute git commands. Use for status, diff, commit, branch, and other git operations.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Git command to run (e.g., 'status', 'diff', 'log --oneline -10')",
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Working directory (defaults to current directory)",
                    },
                },
                "required": ["command"],
            },
            category="vcs",
        )

    async def execute(self, command: str, workdir: str | None = None, **kwargs) -> ToolResult:
        try:
            cwd = workdir if workdir else os.getcwd()

            full_command = f"git {command}"

            result = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
            )

            output = result.stdout if result.stdout else result.stderr

            return ToolResult(
                success=result.returncode == 0,
                content=output or "(no output)",
                metadata={"exit_code": result.returncode, "command": full_command},
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


class ClipboardTool(BaseTool):
    """Read from or write to system clipboard."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="clipboard",
            description="Read from or write to the system clipboard. Use for copying generated code or pasting content.",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write"],
                        "description": "Read from or write to clipboard",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to write to clipboard (required for write action)",
                    },
                },
                "required": ["action"],
            },
            category="system",
        )

    async def execute(self, action: str, text: str | None = None, **kwargs) -> ToolResult:
        try:
            if action == "read":
                result = subprocess.run(
                    ["termux-clipboard-get"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    result = subprocess.run(
                        ["xclip", "-selection", "clipboard", "-o"],
                        capture_output=True,
                        text=True,
                    )
                return ToolResult(
                    success=result.returncode == 0,
                    content=result.stdout or "(clipboard empty)",
                )

            elif action == "write":
                if not text:
                    return ToolResult(success=False, content="", error="No text provided")

                result = subprocess.run(
                    ["termux-clipboard-set", text],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    result = subprocess.run(
                        ["xclip", "-selection", "clipboard"],
                        input=text,
                        capture_output=True,
                        text=True,
                    )
                return ToolResult(
                    success=result.returncode == 0,
                    content=f"Copied {len(text)} characters to clipboard",
                )

            return ToolResult(success=False, content="", error="Invalid action")
        except FileNotFoundError:
            return ToolResult(
                success=False,
                content="",
                error="Clipboard tools not available. Install termux-api or xclip.",
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=sanitize_error(e))


def register_all(registry: ToolRegistry) -> None:
    """Register all core tools."""
    from nexus.automation.tools import (
        ApiFetchTool,
        ApiPostTool,
        ApiUploadTool,
        BrowserClickTool,
        BrowserCloseTool,
        BrowserFillFormTool,
        BrowserGetContentTool,
        BrowserNavigateTool,
        BrowserScreenshotTool,
        BrowserScrollTool,
        BrowserSolveCaptchaTool,
        BrowserSubmitFormTool,
        BrowserTypeTool,
        ExtractFormsTool,
    )
    from nexus.termux.clipboard import ClipboardTool as TermuxClipboardTool
    from nexus.termux.notifications import NotificationTool as TermuxNotificationTool

    tools = [
        ReadTool(),
        WriteTool(),
        EditTool(),
        InteractiveDiffTool(),
        GlobTool(),
        GrepTool(),
        ListTool(),
        BashTool(),
        WebFetchTool(),
        WebSearchTool(),
        TodoWriteTool(),
        QuestionTool(),
        CodeSearchTool(),
        GitTool(),
        ClipboardTool(),
        TermuxClipboardTool(),
        TermuxNotificationTool(),
        BrowserNavigateTool(),
        BrowserFillFormTool(),
        BrowserClickTool(),
        BrowserScreenshotTool(),
        BrowserGetContentTool(),
        BrowserSubmitFormTool(),
        BrowserTypeTool(),
        BrowserScrollTool(),
        BrowserCloseTool(),
        BrowserSolveCaptchaTool(),
        ApiFetchTool(),
        ApiPostTool(),
        ExtractFormsTool(),
        ApiUploadTool(),
    ]

    for tool in tools:
        registry.register(tool)
