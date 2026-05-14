"""Task Orchestrator - decomposes complex tasks into ordered execution plans."""

import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)


class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()
    ADAPTED = auto()


class StepType(Enum):
    READ = auto()
    WRITE = auto()
    EDIT = auto()
    BASH = auto()
    WEB_FETCH = auto()
    SEARCH = auto()
    AGENT_TASK = auto()
    VERIFY = auto()
    PLANNING = auto()
    CUSTOM = auto()


@dataclass
class StepDependency:
    step_id: str
    field: str = "result"
    condition: str = "success"


@dataclass
class ExecutionStep:
    id: str
    description: str
    step_type: StepType
    tool_name: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    dependencies: list[StepDependency] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0
    max_retries: int = 2
    can_parallelize_with: list[str] = field(default_factory=list)
    verification_fn: Callable[[Any], bool] | None = None
    fallback_steps: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    agent_role: str | None = None
    agent_task: str | None = None
    estimated_duration_ms: float = 0.0
    actual_duration_ms: float = 0.0

    def duration_ms(self) -> float:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0

    def is_done(self) -> bool:
        return self.status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED)

    def is_blocked_by_dependencies(self, completed: set[str], results: dict[str, Any]) -> bool:
        for dep in self.dependencies:
            if dep.step_id not in completed:
                return True
        return False


@dataclass
class TaskPlan:
    task: str
    goal: str
    steps: list[ExecutionStep]
    created_at: float = field(default_factory=time.time)
    replanned_count: int = 0
    max_replans: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_step(self, step_id: str) -> ExecutionStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self, completed: set[str], results: dict[str, Any]) -> list[ExecutionStep]:
        ready = []
        for step in self.steps:
            if step.is_done():
                continue
            if step.is_blocked_by_dependencies(completed, results):
                continue
            ready.append(step)
        return ready

    def get_parallel_batches(self, completed: set[str], results: dict[str, Any]) -> list[list[ExecutionStep]]:
        batches = []
        remaining = self.get_ready_steps(completed, results)
        seen_ids = set()

        while remaining and len(batches) < 20:
            batch = []
            for step in remaining:
                if step.id in seen_ids:
                    continue
                can_add = True
                for other in batch:
                    if step.id in other.can_parallelize_with or other.id in step.can_parallelize_with:
                        can_add = False
                        break
                if can_add:
                    batch.append(step)
                    seen_ids.add(step.id)

            if not batch:
                if remaining:
                    batch = [remaining[0]]
                    seen_ids.add(remaining[0].id)
                else:
                    break

            batches.append(batch)
            remaining = [s for s in remaining if s.id not in seen_ids]

        return batches


class BaseDecomposer(ABC):
    @abstractmethod
    async def decompose(self, task: str, context: dict[str, Any], registry: Any) -> TaskPlan:
        pass


class SimpleDecomposer(BaseDecomposer):
    def __init__(self):
        self.step_counter = 0

    def _next_id(self) -> str:
        self.step_counter += 1
        return f"step_{self.step_counter}"

    def extract_context(self, task: str) -> dict[str, Any]:
        ctx: dict[str, Any] = {"task": task}
        task_lower = task.lower()

        if re.search(r'\bnpm install\b', task_lower):
            ctx["install_cmd"] = "npm install"
        elif re.search(r'\bpip install\b', task_lower):
            ctx["install_cmd"] = "pip install"

        exts = ['py', 'js', 'ts', 'json', 'txt', 'sh', 'md', 'yaml', 'yml', 'toml', 'html', 'css', 'go', 'rs', 'java', 'cpp', 'c', 'rb', 'php']
        path = None
        for ext in exts:
            m = re.search(rf'\b([\w\-]+\.{ext})\b', task)
            if m:
                path = m.group(1)
                break
        if not path:
            m = re.search(r'^(app\.(?:py|js|ts))\b', task)
            if m:
                path = m.group(1)

        if not path and "python script" in task_lower:
            path = "script.py"
        elif not path and "javascript" in task_lower:
            path = "script.js"
        elif not path and "typescript" in task_lower:
            path = "script.ts"
        elif not path and "web server" in task_lower:
            path = "server.py"
        elif not path and re.search(r'\bcalculator\s*script\b', task_lower):
            path = "calculator.py"
        elif not path and re.search(r'\bsetup\s*(project|script|file)?\b', task_lower):
            path = "setup.py"
            if "new project" not in task_lower and "new script" not in task_lower:
                ctx["_inferred_content"] = True
        elif not path and re.search(r'\bnew\s+project\b', task_lower):
            path = "main.py"
            ctx["content"] = 'print("hello world")\n'
            ctx["test_cmd"] = "python main.py"
        elif not path and re.search(r'\bnew\s+script\b', task_lower):
            path = "script.py"
            ctx["content"] = 'print("hello world")\n'
            ctx["test_cmd"] = "python script.py"

        if path:
            ctx["path"] = path

        if re.search(r'print\s*[\("]', task_lower) or 'hello world' in task_lower:
            ctx["content"] = 'print("hello world")\n'
            if path and path.endswith('.py') and not ctx.get('test_cmd'):
                ctx["test_cmd"] = f"python {path}"
        elif path and path.endswith('.py') and not ctx.get('test_cmd'):
            ctx["test_cmd"] = f"python {path}"
            if not ctx.get('content'):
                ctx["content"] = 'print("hello world")\n'
        elif re.search(r'web\s+server|http\s+server|flask|fastapi|django', task_lower):
            ctx["content"] = (
                "from http.server import HTTPServer, SimpleHTTPRequestHandler\n"
                "HTTPServer(('0.0.0.0', 8000), SimpleHTTPRequestHandler).serve_forever()\n"
            )
            ctx["test_cmd"] = "curl http://localhost:8000"
        elif "calculator" in task_lower:
            ctx["content"] = "a = float(input())\nb = float(input())\nprint(a + b)\n"
            ctx["test_cmd"] = "echo '2 3' | python"
        elif "todo" in task_lower:
            ctx["content"] = "# Todo app\ntodos = []\n\ndef add(item):\n    todos.append(item)\n    return todos\n\ndef list_todos():\n    for t in todos:\n        print(f'- {t}')\n\nif __name__ == '__main__':\n    add('test item')\n    list_todos()\n"
        elif "index.html" in task_lower or ("html" in task_lower and "browser" in task_lower):
            ctx["content"] = "<!DOCTYPE html>\n<html>\n<head><title>App</title></head>\n<body><h1>Hello</h1></body>\n</html>\n"
            if path and path.endswith('.html') and not ctx.get('test_cmd'):
                ctx["test_cmd"] = "open " + path
        elif "web app" in task_lower:
            if path and path.endswith('.js'):
                ctx["content"] = 'console.log("Hello from web app");\n'
                if not ctx.get('test_cmd'):
                    ctx["test_cmd"] = "node " + path
            elif path and path.endswith('.ts'):
                ctx["content"] = 'console.log("Hello from TypeScript");\n'
                if not ctx.get('test_cmd'):
                    ctx["test_cmd"] = "tsc && node " + path.replace('.ts', '.js')
        elif not ctx.get('content') and path and path.endswith('.js'):
            ctx["content"] = 'console.log("hello world");\n'
            ctx["test_cmd"] = "node " + path
        elif not ctx.get('content') and path and path.endswith('.ts'):
            ctx["content"] = 'console.log("hello world");\n'
            ctx["test_cmd"] = "tsc && node " + path.replace('.ts', '.js')
        elif not ctx.get('content'):
            ctx["content"] = 'print("hello world")\n'

        curl_m = re.search(r'curl\s+(https?://[^\s,\n]+)', task_lower)
        if curl_m:
            ctx["test_cmd"] = curl_m.group(0)
        elif "test it with curl" in task_lower or "test with curl" in task_lower:
            if (path and path.endswith(".py")) or "server" in task_lower or "api" in task_lower:
                ctx["test_cmd"] = "curl http://localhost:8000"
        elif "start the server" in task_lower or "run the server" in task_lower or "start it" in task_lower:
            if path and path.endswith(".py"):
                ctx["test_cmd"] = f"python {path} & sleep 1 && curl http://localhost:8000"
        elif "run tests" in task_lower:
            m = re.search(r'run tests with\s+([a-zA-Z0-9_\-\.]+)', task_lower)
            if m:
                ctx["test_cmd"] = m.group(1).strip()
            else:
                ctx["test_cmd"] = "pytest -v"
        elif "pytest" in task_lower:
            ctx["test_cmd"] = "pytest -v"
        elif "run in a browser" in task_lower or "open in browser" in task_lower:
            if path and path.endswith('.html'):
                ctx["test_cmd"] = "open " + path

        return ctx

    async def decompose(self, task: str, context: dict[str, Any], registry: Any) -> TaskPlan:
        task_lower = task.lower()
        self.step_counter = 0

        goal = task if len(task) < 100 else task[:100] + "..."
        steps: list[ExecutionStep] = []

        has_multi = (" and " in task_lower or " then " in task_lower or "+" in task or "," in task)

        if has_multi:
            if any(k in task_lower for k in ["fix", "bug", "error", "crash"]):
                steps.extend(self._decompose_bug_fix(task, context))
            elif any(k in task_lower for k in ["install", "setup", "configure", "initialize"]):
                has_action = any(v in task_lower for v in ["run it", "start it", "stop it", "restart it", "build it", "compile it", "test it", "verify it", "check it", "deploy it"]) or re.search(r'\b(?:test|verify|check|start|stop|restart)\b', task_lower)
                if has_action:
                    steps.extend(self._decompose_multi_action(task, context))
                else:
                    steps.extend(self._decompose_deployment(task, context))
            elif any(k in task_lower for k in ["create", "write", "make file", "set up", "make a new"]):
                has_deploy_like = any(k in task_lower for k in ["build it", "deploy", "compile it", "release", "publish"])
                if has_deploy_like:
                    steps.extend(self._decompose_deployment(task, context))
                else:
                    steps.extend(self._decompose_multi_action(task, context))
            elif any(k in task_lower for k in ["build", "compile", "package"]):
                steps.extend(self._decompose_multi_action(task, context))
            elif any(k in task_lower for k in ["deploy", "release", "publish"]):
                steps.extend(self._decompose_deployment(task, context))
            elif any(k in task_lower for k in ["analyze", "audit", "review", "assess"]):
                steps.extend(self._decompose_analysis(task, context))
            else:
                steps.extend(self._decompose_multi_action(task, context))
        elif any(k in task_lower for k in ["fix", "bug", "error", "crash"]):
            steps.extend(self._decompose_bug_fix(task, context))
        elif any(k in task_lower for k in ["install", "setup", "configure", "initialize"]):
            steps.extend(self._decompose_deployment(task, context))
        elif any(k in task_lower for k in ["build", "compile", "package"]):
            steps.extend(self._decompose_deployment(task, context))
        elif any(k in task_lower for k in ["deploy", "release", "publish"]):
            steps.extend(self._decompose_deployment(task, context))
        elif any(k in task_lower for k in ["analyze", "audit", "review", "assess"]):
            steps.extend(self._decompose_analysis(task, context))
        elif any(k in task_lower for k in ["create", "write", "make file", "set up"]):
            steps.extend(self._decompose_file_creation(task, context))
        elif any(k in task_lower for k in ["test", "run tests"]):
            steps.extend(self._decompose_testing(task, context))
        else:
            steps.extend(self._decompose_multi_action(task, context))

        if not steps:
            steps.append(ExecutionStep(
                id=self._next_id(), description=task, step_type=StepType.CUSTOM,
                tool_name=None, args={"task": task},
            ))

        return TaskPlan(task=task, goal=goal, steps=steps)

    def _extract_install_command(self, text_lower: str, context: dict) -> str:
        setup_with_m = re.search(r'\b(?:setup|install|configure)\s+(?:project|it|this)\s+(?:using|with)\s+([a-zA-Z0-9_\-\.]+)', text_lower)
        if setup_with_m:
            tool = setup_with_m.group(1).strip()
            if tool == "poetry": return "poetry install"
            if tool == "pipenv": return "pipenv install"
            if tool == "pnpm": return "pnpm install"
            if tool == "yarn": return "yarn install"
            return f"{tool} install"

        if "npm" in text_lower or "node" in text_lower: return "npm install"
        if "pip" in text_lower: return "pip install"
        if "cargo" in text_lower or "rust" in text_lower: return "cargo build"
        if "go" in text_lower: return "go mod tidy"

        return context.get("install_cmd", "pip install -r requirements.txt")

    def _decompose_multi_action(self, task: str, context: dict) -> list[ExecutionStep]:
        task_lower = task.lower()
        path = context.get("path", "unknown")
        content = context.get("content", "")
        test_cmd = context.get("test_cmd", "")

        raw_parts = re.split(r'\s+and\s+|\s+then\s+|\s+\+\s+', task)
        all_parts = []
        for part in raw_parts:
            commas = re.split(r',(?=\s+(?:and\s+)?(?:run it|test it|execute it|build it|deploy it|start it|compile it|check|verify|curl))', part)
            all_parts.extend([p.strip() for p in commas if p.strip()])

        steps = []
        prev_id = None
        wrote = False

        for part in all_parts:
            part = re.sub(r'^(and|then)\s+', '', part, flags=re.IGNORECASE).strip()
            if not part:
                continue
            part_lower = part.lower()

            create_kws = ["create", "write", "make file", "save file", "build a web app", "build an app", "build a project", "build a script", "set up a new", "setup project", "setup a project"]
            create_explicit_run_kws = ["create", "write"]
            is_create_with_run = any(k in part_lower for k in create_explicit_run_kws)
            if any(k in part_lower for k in create_kws):
                if path != "unknown" and content:
                    sid = self._next_id()
                    deps = [StepDependency(prev_id)] if prev_id else []
                    steps.append(ExecutionStep(
                        id=sid, description=f"Write file: {path}",
                        step_type=StepType.WRITE, tool_name="Write",
                        args={"filePath": path, "content": content},
                        dependencies=deps, verification_fn=self._verify_write,
                    ))
                    prev_id = sid
                    wrote = True

            elif re.search(r'\b(?:initialize|setup)\s+(?:a\s+)?new\s+(?:project|script)\b', part_lower):
                cmd = self._extract_install_command(part_lower, context)
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Setup: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif any(re.search(rf'\b{k}\b(?!\.[a-z]{{1,5}})', part_lower) for k in ["run it", "test it", "execute it", "start it"]) and not is_create_with_run:
                cmd = ""
                # Try to extract explicit command like "run it with python3"
                run_with_m = re.search(r'\b(?:run|test|execute|start)\s+it\s+with\s+([a-zA-Z0-9_\-\.\/ ]+)', part_lower)
                if run_with_m:
                    tool = run_with_m.group(1).strip()
                    cmd = f"{tool} {path}" if path != "unknown" else tool

                if not cmd and test_cmd:
                    cmd = test_cmd

                if not cmd and wrote and path != "unknown":
                    if path.endswith(".py"): cmd = f"python {path}"
                    elif path.endswith(".js"): cmd = f"node {path}"
                    elif path.endswith(".sh"): cmd = f"bash {path}"
                    elif path.endswith(".ts"): cmd = f"tsc && node {path.replace('.ts','.js')}"

                if not cmd and ("node" in task_lower or "npm" in task_lower): cmd = "npm start"
                if not cmd: cmd = "pytest -v" if "pytest" in task_lower else f"python {path}" if path.endswith(".py") else ""

                if cmd:
                    sid = self._next_id()
                    deps = [StepDependency(prev_id)] if prev_id else []
                    steps.append(ExecutionStep(
                        id=sid, description=f"Run: {cmd}",
                        step_type=StepType.BASH, tool_name="Bash",
                        args={"command": cmd}, dependencies=deps,
                        verification_fn=self._verify_bash_success,
                    ))
                    prev_id = sid

            elif "install" in part_lower and ("npm" in task_lower or "pip" in task_lower or "install" in part_lower):
                cmd = self._extract_install_command(part_lower, context)
                if cmd:
                    sid = self._next_id()
                    deps = [StepDependency(prev_id)] if prev_id else []
                    steps.append(ExecutionStep(
                        id=sid, description=f"Install: {cmd}",
                        step_type=StepType.BASH, tool_name="Bash",
                        args={"command": cmd}, dependencies=deps,
                        verification_fn=self._verify_bash_success,
                    ))
                    prev_id = sid

            elif part_lower in ["start", "restart", "stop"]:
                cmd = ""
                if "npm" in task_lower or "node" in task_lower: cmd = "npm start"
                elif "pip" in task_lower: cmd = "pip install"
                else: cmd = context.get("test_cmd", "python app.py")
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Run: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif re.search(r'\b(?:initialize|configure|setup)\b', part_lower) and not re.search(r'\b(new|a)\s+(project|script|file)\b', part_lower):
                cmd = ""
                if "npm" in task_lower or "node" in task_lower: cmd = "npm install"
                elif "pip" in task_lower or "python" in task_lower: cmd = "pip install"
                else: cmd = context.get("install_cmd", "make setup")
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Setup: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif re.search(r'^test with\b', part_lower):
                cmd = "pytest -v" if "pytest" in task_lower else test_cmd
                if not cmd: cmd = "pytest -v"
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Test: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif part_lower in ["test", "verify", "check"]:
                cmd = test_cmd
                if not cmd:
                    if "pytest" in task_lower: cmd = "pytest -v"
                    elif wrote and path.endswith(".py"): cmd = f"python {path}"
                    elif wrote and path.endswith(".js"): cmd = f"node {path}"
                    elif wrote and path.endswith(".ts"): cmd = f"tsc && node {path.replace('.ts','.js')}"
                if not cmd: cmd = "pytest -v"
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Test: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif "build it" in part_lower or "compile it" in part_lower or "package it" in part_lower or re.search(r'\b(?:build|compile)\s+(?:the\s+)?(?:project|it)\b', part_lower):
                cmd = ""
                if "npm" in task_lower or "node" in task_lower: cmd = "npm run build"
                elif "cargo" in task_lower or "rust" in task_lower: cmd = "cargo build --release"
                elif "go" in task_lower: cmd = "go build ./..."
                elif wrote and path.endswith((".js", ".ts")): cmd = f"node {path}" if path.endswith(".js") else f"tsc {path}"
                elif wrote and path.endswith(".py"): cmd = f"python {path}"
                if not cmd: cmd = "make build"
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Build: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif "deploy it" in part_lower or "release it" in part_lower or "publish it" in part_lower or re.match(r'^(deploy|release|publish)$', part_lower.strip()):
                cmd = context.get("deploy_cmd", "make deploy")
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Deploy: {cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif "curl " in part_lower or "test with curl" in part_lower or "check with curl" in part_lower:
                curl_cmd = "curl http://localhost:8000"
                m = re.search(r'curl[^\s,]+', part)
                if m: curl_cmd = m.group()
                sid = self._next_id()
                deps = [StepDependency(prev_id)] if prev_id else []
                steps.append(ExecutionStep(
                    id=sid, description=f"Test: {curl_cmd}",
                    step_type=StepType.BASH, tool_name="Bash",
                    args={"command": curl_cmd}, dependencies=deps,
                    verification_fn=self._verify_bash_success,
                ))
                prev_id = sid

            elif re.search(r'\b(?:check|verify)\b', part_lower) and not re.search(r'\b(?:setup|testing)\b', part_lower):
                if "log" in part_lower:
                    cmd = "tail -20 /var/log/app.log || echo 'no logs'"
                elif wrote and path != "unknown":
                    if path.endswith(".py"): cmd = f"python {path}"
                    elif path.endswith(".js"): cmd = f"node {path}"
                    else: cmd = test_cmd or ""
                else:
                    cmd = test_cmd or ""
                if cmd:
                    sid = self._next_id()
                    deps = [StepDependency(prev_id)] if prev_id else []
                    steps.append(ExecutionStep(
                        id=sid, description=f"Check: {cmd}",
                        step_type=StepType.BASH, tool_name="Bash",
                        args={"command": cmd}, dependencies=deps,
                        verification_fn=self._verify_bash_success,
                    ))
                    prev_id = sid

            elif re.search(r'\btest it\b', part_lower) or (re.search(r'\btest with\b', part_lower) and not re.search(r'\btest with\b.*\b(pytest|junit|jest|mocha)\b', part_lower)):
                cmd = test_cmd
                if not cmd:
                    if "pytest" in task_lower: cmd = "pytest -v"
                    elif wrote and path.endswith(".py"): cmd = f"python {path}"
                    elif wrote and path.endswith(".js"): cmd = f"node {path}"
                    elif wrote and path.endswith(".ts"): cmd = f"tsc && node {path.replace('.ts','.js')}"
                    elif wrote and path.endswith(".sh"): cmd = f"bash {path}"
                if cmd:
                    sid = self._next_id()
                    deps = [StepDependency(prev_id)] if prev_id else []
                    steps.append(ExecutionStep(
                        id=sid, description=f"Test: {cmd}",
                        step_type=StepType.BASH, tool_name="Bash",
                        args={"command": cmd}, dependencies=deps,
                        verification_fn=self._verify_bash_success,
                    ))
                    prev_id = sid

        return steps

    def _decompose_file_creation(self, task: str, context: dict) -> list[ExecutionStep]:
        path = context.get("path", "unknown")
        content = context.get("content", "")
        test_cmd = context.get("test_cmd", "")
        steps = []

        if path != "unknown" and content:
            sid = self._next_id()
            steps.append(ExecutionStep(
                id=sid, description=f"Write file: {path}",
                step_type=StepType.WRITE, tool_name="Write",
                args={"filePath": path, "content": content},
                verification_fn=self._verify_write,
            ))

            task_lower = task.lower()
            explicit_run = any(k in task_lower for k in ["run it", "test it", "execute it", "start it", "start the", "open in browser", "run in browser"])
            if explicit_run or (test_cmd and any(k in task_lower for k in ["run ", "test with", "execute ", "curl ", "verify ", "open "])):
                sid2 = self._next_id()
                cmd = test_cmd or f"python {path}" if path.endswith(".py") else ""
                if cmd:
                    steps.append(ExecutionStep(
                        id=sid2, description=f"Run: {cmd}",
                        step_type=StepType.BASH, tool_name="Bash",
                        args={"command": cmd},
                        dependencies=[StepDependency(sid)],
                        verification_fn=self._verify_bash_success,
                    ))
        return steps

    def _decompose_bug_fix(self, task: str, context: dict) -> list[ExecutionStep]:
        target = context.get("path", "") or context.get("target", "")
        sid1 = self._next_id()
        sid2 = self._next_id()
        return [
            ExecutionStep(
                id=sid1, description=f"Edit {target} to fix the bug",
                step_type=StepType.EDIT, tool_name="Edit",
                args={"filePath": target},
            ),
            ExecutionStep(
                id=sid2, description=f"Verify fix in {target}",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": context.get("test_cmd", f"python {target}")},
                dependencies=[StepDependency(sid1)],
                verification_fn=self._verify_bash_success,
            ),
        ]

    def _decompose_analysis(self, task: str, context: dict) -> list[ExecutionStep]:
        target = context.get("path", "")
        cmd = f"python -m py_compile {target} && echo 'OK'" if target else "find . -name '*.py' | head -20"
        return [
            ExecutionStep(
                id=self._next_id(), description=f"Analyze: {task}",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": cmd},
            )
        ]

    def _decompose_deployment(self, task: str, context: dict) -> list[ExecutionStep]:
        task_lower = task.lower()
        steps = []
        prev_id = None
        path = context.get("path", "unknown")
        content = context.get("content", "")

        if path != "unknown" and content and not context.get("_inferred_content"):
            sid = self._next_id()
            steps.append(ExecutionStep(
                id=sid, description=f"Write file: {path}",
                step_type=StepType.WRITE, tool_name="Write",
                args={"filePath": path, "content": content},
                verification_fn=self._verify_write,
            ))
            prev_id = sid

        install_kws = ["install", "setup", "configure", "initialize"]
        has_install = any(k in task_lower for k in install_kws)
        has_build = any(k in task_lower for k in ["build the project", "compile", "build it", "compile it"]) and not re.search(r'install the \w+ package', task_lower)
        has_deploy = any(k in task_lower for k in ["deploy", "release", "publish"])
        has_test = any(k in task_lower for k in ["test", "run tests", "verify"]) and not has_install

        if has_install:
            sid = self._next_id()
            cmd = self._extract_install_command(task_lower, context)
            steps.append(ExecutionStep(
                id=sid, description="Install dependencies",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": cmd},
            ))
            prev_id = sid

        if has_build:
            sid = self._next_id()
            cmd = "make build"
            if "npm" in task_lower or "node" in task_lower: cmd = "npm run build"
            elif "cargo" in task_lower or "rust" in task_lower: cmd = "cargo build --release"
            elif "go" in task_lower: cmd = "go build ./..."
            steps.append(ExecutionStep(
                id=sid, description="Build/package the application",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": cmd},
                dependencies=[StepDependency(prev_id)] if prev_id else [],
            ))
            prev_id = sid

        if has_deploy:
            sid = self._next_id()
            cmd = context.get("deploy_cmd", "make deploy")
            steps.append(ExecutionStep(
                id=sid, description="Deploy",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": cmd},
                dependencies=[StepDependency(prev_id)] if prev_id else [],
            ))
            prev_id = sid

        if has_test:
            sid = self._next_id()
            cmd = context.get("test_cmd", "pytest")
            steps.append(ExecutionStep(
                id=sid, description="Run tests",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": cmd},
                dependencies=[StepDependency(prev_id)] if prev_id else [],
                verification_fn=self._verify_bash_success,
            ))
            prev_id = sid

        if not steps:
            cmd = context.get("test_cmd", "pytest")
            steps.append(ExecutionStep(
                id=self._next_id(), description="Run command",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": cmd},
            ))

        return steps

    def _decompose_testing(self, task: str, context: dict) -> list[ExecutionStep]:
        return [
            ExecutionStep(
                id=self._next_id(), description="Run test suite",
                step_type=StepType.BASH, tool_name="Bash",
                args={"command": context.get("test_cmd", "pytest")},
                verification_fn=self._verify_bash_success,
            )
        ]

    def _verify_write(self, result: Any) -> bool:
        if isinstance(result, dict):
            return result.get("success", False)
        return bool(result)

    def _verify_bash_success(self, result: Any) -> bool:
        if isinstance(result, dict):
            return result.get("success", False)
        return True


class LLMAwareDecomposer(SimpleDecomposer):
    def __init__(self, llm_callback: Callable[[str], Coroutine[Any, Any, str]] | None = None):
        super().__init__()
        self.llm_callback = llm_callback

    async def decompose(self, task: str, context: dict[str, Any], registry: Any) -> TaskPlan:
        if self.llm_callback:
            plan = await self._llm_decompose(task, context)
            if plan:
                return plan
        return await super().decompose(task, context, registry)

    async def _llm_decompose(self, task: str, context: dict[str, Any]) -> TaskPlan | None:
        prompt = f"""Analyze this task and create an execution plan:\n\nTask: {task}\n\nBreak it down into ordered steps. Return JSON with goal and steps array."""
        try:
            response = await self.llm_callback(prompt)
            import json
            plan_data = json.loads(response)
            goal = plan_data.get("goal", task)
            steps = []
            for i, step_data in enumerate(plan_data.get("steps", [])):
                steps.append(ExecutionStep(
                    id=f"step_{i+1}",
                    description=step_data.get("description", ""),
                    step_type=StepType.CUSTOM,
                    tool_name=step_data.get("tool"),
                    args=step_data.get("args", {}),
                ))
            return TaskPlan(task=task, goal=goal, steps=steps)
        except Exception as e:
            logger.warning(f"LLM decomposition failed: {e}")
            return None
