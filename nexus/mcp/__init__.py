"""MCP (Model Context Protocol) client for Nexus.

MCP is a protocol for connecting AI models to external tools and data sources.
Nexus MCP client supports:
  - stdio transport (local servers)
  - SSE transport (remote servers)
  - Lazy tool loading (only load when needed)
  - Tool registry integration

Inspired by: Claude Code's lazy-loading MCP tools, Gemini CLI's ToolRegistry cloning.
"""

import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ..tools.base import BaseTool, ToolDefinition, ToolResult


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    transport: str = "stdio"
    auto_load: bool = True


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


class MCPClient:
    """
    MCP client that connects to MCP servers and exposes their tools.
    Implements the MCP protocol over stdio or SSE transport.
    """

    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._tools: dict[str, MCPTool] = {}
        self._initialized: set[str] = set()

    def add_server(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration."""
        self._servers[config.name] = config

    def remove_server(self, name: str) -> None:
        """Remove and stop an MCP server."""
        if name in self._processes:
            self._processes[name].terminate()
            del self._processes[name]
        self._servers.pop(name, None)
        self._initialized.discard(name)
        self._tools = {k: v for k, v in self._tools.items() if v.server_name != name}

    async def initialize_server(self, name: str) -> None:
        """Initialize an MCP server via JSON-RPC handshake."""
        config = self._servers.get(name)
        if not config:
            raise ValueError(f"MCP server '{name}' not configured")

        if config.transport == "stdio":
            await self._init_stdio(config)
        elif config.transport == "sse":
            await self._init_sse(config)

        self._initialized.add(name)

    async def _init_stdio(self, config: MCPServerConfig) -> None:
        """Initialize a stdio-based MCP server."""
        env = {**os.environ, **config.env}
        proc = subprocess.Popen(
            [config.command] + config.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._processes[config.name] = proc

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "nexus", "version": "0.1.0"},
            },
        }
        await self._send_request(config.name, request)
        await self._send_notification(config.name, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        tools_response = await self._send_request(config.name, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
        })
        for tool_data in tools_response.get("result", {}).get("tools", []):
            self._tools[f"{config.name}/{tool_data['name']}"] = MCPTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_name=config.name,
            )

    async def _init_sse(self, config: MCPServerConfig) -> None:
        """Initialize an SSE-based MCP server."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{config.url}/initialize",
                json={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "nexus", "version": "0.1.0"},
                },
                timeout=10.0,
            )
            resp.raise_for_status()

    async def _send_request(self, server_name: str, request: dict) -> dict:
        """Send a JSON-RPC request to a stdio server."""
        proc = self._processes.get(server_name)
        if not proc or proc.stdin is None or proc.stdout is None:
            raise RuntimeError(f"Server '{server_name}' not running")

        data = (json.dumps(request) + "\n").encode()
        proc.stdin.write(data)
        await asyncio.get_event_loop().run_in_executor(proc.stdin.flush, None)

        line = await asyncio.get_event_loop().run_in_executor(proc.stdout.readline, None)
        if not line:
            raise RuntimeError(f"Server '{server_name}' disconnected")
        return json.loads(line)

    async def _send_notification(self, server_name: str, notification: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        proc = self._processes[server_name]
        if proc.stdin:
            data = (json.dumps(notification) + "\n").encode()
            proc.stdin.write(data)
            await asyncio.get_event_loop().run_in_executor(proc.stdin.flush, None)

    async def call_tool(self, full_name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Call an MCP tool by its full name (server/tool).
        Returns ToolResult for integration with the tool registry.
        """
        if "/" not in full_name:
            return ToolResult(success=False, content="", error=f"Invalid MCP tool name: {full_name}")

        server_name, tool_name = full_name.split("/", 1)
        if server_name not in self._initialized:
            try:
                await self.initialize_server(server_name)
            except Exception as e:
                return ToolResult(success=False, content="", error=f"Failed to initialize {server_name}: {e}")

        config = self._servers[server_name]
        if config.transport == "stdio":
            return await self._call_stdio_tool(server_name, tool_name, arguments)
        elif config.transport == "sse":
            return await self._call_sse_tool(config, tool_name, arguments)
        return ToolResult(success=False, content="", error=f"Unknown transport: {config.transport}")

    async def _call_stdio_tool(self, server_name: str, tool_name: str, args: dict) -> ToolResult:
        """Call a tool on a stdio MCP server."""
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }
        try:
            response = await self._send_request(server_name, request)
            result = response.get("result", {})
            content = result.get("content", [])
            if isinstance(content, list):
                text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
            else:
                text = str(content)
            return ToolResult(success=True, content=text)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))

    async def _call_sse_tool(self, config: MCPServerConfig, tool_name: str, args: dict) -> ToolResult:
        """Call a tool on an SSE MCP server."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{config.url}/tools/call",
                    json={"name": tool_name, "arguments": args},
                    timeout=30.0,
                )
                resp.raise_for_status()
                result = resp.json()
                return ToolResult(success=True, content=json.dumps(result))
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))

    def list_tools(self) -> list[MCPTool]:
        """List all available MCP tools."""
        return list(self._tools.values())

    def get_tool(self, full_name: str) -> MCPTool | None:
        """Get an MCP tool by full name."""
        return self._tools.get(full_name)

    async def close(self) -> None:
        """Stop all MCP servers."""
        for proc in self._processes.values():
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._processes.clear()
        self._initialized.clear()


def mcp_tool_from_server(mcp: MCPClient, server_name: str) -> type[BaseTool]:
    """Create a BaseTool subclass that wraps all tools from an MCP server."""

    class MCPAdapterTool(BaseTool):
        _mcp = mcp
        _server = server_name

        @property
        def definition(self) -> ToolDefinition:
            tools = [t for t in self._mcp.list_tools() if t.server_name == self._server]
            desc = f"MCP server '{self._server}' with {len(tools)} tools: " + ", ".join(t.name for t in tools)
            return ToolDefinition(
                name=f"mcp_{self._server}",
                description=desc,
                input_schema={"type": "object", "properties": {"tool": {"type": "string"}, "args": {"type": "object"}}},
            )

        async def execute(self, **kwargs) -> ToolResult:
            tool_name = kwargs.get("tool", "")
            args = kwargs.get("args", {})
            if not tool_name:
                return ToolResult(success=False, content="", error="No tool specified")
            return await self._mcp.call_tool(f"{self._server}/{tool_name}", args)

    return MCPAdapterTool


import os
