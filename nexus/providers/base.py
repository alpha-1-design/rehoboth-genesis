"""Unified AI Provider Layer for Nexus.

Supports: OpenAI, Anthropic, Google Gemini, Groq, DeepSeek, Ollama, LM Studio,
and any OpenAI-compatible endpoint.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ModelInfo:
    """Information about a model."""

    id: str
    name: str
    provider: str
    context_window: int = 128000
    supports_vision: bool = False
    supports_function_calling: bool = True
    supports_streaming: bool = True
    max_output_tokens: int | None = None


@dataclass
class ToolCall:
    """Represents a tool call from the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """A message in the conversation."""

    role: str  # system, user, assistant, tool
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class Response:
    """A response from the model."""

    content: str
    model: str
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None


@dataclass
class StreamChunk:
    """A chunk from a streaming response."""

    content: str = ""
    tool_call: ToolCall | None = None
    finish_reason: str | None = None
    done: bool = False


class BaseProvider(ABC):
    """Base class for all AI providers."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    async def complete(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> Response:
        """Generate a completion."""
        pass

    @abstractmethod
    async def stream(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> AsyncIterator[StreamChunk]:
        """Generate a streaming completion."""
        pass

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models."""
        pass

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class OpenAIProvider(BaseProvider):
    """OpenAI API provider (also OpenAI-compatible endpoints)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gpt-4o")
        self.timeout = config.get("timeout", 120)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> Response:
        client = self._get_client()

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": [self._format_message(m) for m in messages],
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await client.post("/chat/completions", json=payload)
        if response.status_code != 200:
            response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    async def stream(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": [self._format_message(m) for m in messages],
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                yield StreamChunk(done=True)
                return

            chunk_data = json.loads(data)
            yield self._parse_stream_chunk(chunk_data)

    async def list_models(self) -> list[ModelInfo]:
        client = self._get_client()
        response = await client.get("/models")
        response.raise_for_status()
        data = response.json()

        models = []
        for m in data.get("data", []):
            models.append(
                ModelInfo(
                    id=m["id"],
                    name=m.get("name", m["id"]),
                    provider="openai",
                    context_window=m.get("context_window", 128000),
                )
            )
        return models

    def _format_message(self, msg: Message) -> dict[str, Any]:
        result: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.name:
            result["name"] = msg.name
        if msg.tool_call_id:
            result["tool_call_id"] = msg.tool_call_id
        return result

    def _parse_response(self, data: dict[str, Any]) -> Response:
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content", "")
        tool_calls = []

        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=json.loads(tc["function"]["arguments"]),
                    )
                )

        return Response(
            content=content,
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls,
            usage=data.get("usage"),
        )

    def _parse_stream_chunk(self, data: dict[str, Any]) -> StreamChunk:
        delta = data["choices"][0].get("delta", {})
        content = delta.get("content", "")

        tool_call = None
        if "tool_calls" in delta:
            for tc in delta["tool_calls"]:
                if tc.get("function"):
                    args_str = tc["function"].get("arguments", "")
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        args = {}  # Incomplete JSON, skip for now
                    tool_call = ToolCall(
                        id=tc.get("id", ""),
                        name=tc["function"].get("name", ""),
                        arguments=args,
                    )
                    break

        return StreamChunk(
            content=content,
            tool_call=tool_call,
            finish_reason=data["choices"][0].get("finish_reason"),
            done=data["choices"][0].get("finish_reason") is not None,
        )


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "claude-3-5-sonnet-20241022")
        self.base_url = "https://api.anthropic.com/v1"
        self.timeout = config.get("timeout", 120)
        self.api_version = "2023-06-01"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.api_version,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def _format_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Convert OpenAI-style tools to Anthropic format."""
        if not tools:
            return []

        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append(
                {
                    "name": tool["function"]["name"],
                    "description": tool["function"].get("description", ""),
                    "input_schema": tool["function"]["parameters"],
                }
            )
        return anthropic_tools

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> Response:
        client = self._get_client()

        # Convert messages to Anthropic format
        anthropic_messages = []
        system_prompt = ""

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                anthropic_messages.append(
                    {
                        "role": msg.role,
                        "content": msg.content,
                    }
                )

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools:
            payload["tools"] = self._format_tools(tools)

        response = await client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    async def stream(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        anthropic_messages = []
        system_prompt = ""

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                anthropic_messages.append(
                    {
                        "role": msg.role,
                        "content": msg.content,
                    }
                )

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools:
            payload["tools"] = self._format_tools(tools)

        async with client.stream("POST", "/messages", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    yield StreamChunk(done=True)
                    return

                chunk_data = json.loads(data)
                yield self._parse_stream_chunk(chunk_data)

    async def list_models(self) -> list[ModelInfo]:
        # Anthropic doesn't have a public model list endpoint
        return [
            ModelInfo(
                id="claude-opus-4-5",
                name="Claude Opus 4",
                provider="anthropic",
                context_window=200000,
                supports_vision=True,
            ),
            ModelInfo(
                id="claude-sonnet-4-5",
                name="Claude Sonnet 4",
                provider="anthropic",
                context_window=200000,
                supports_vision=True,
            ),
            ModelInfo(
                id="claude-haiku-4-5",
                name="Claude Haiku 4",
                provider="anthropic",
                context_window=200000,
                supports_vision=True,
            ),
        ]

    def _parse_response(self, data: dict[str, Any]) -> Response:
        content = ""
        tool_calls = []

        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block["input"],
                    )
                )

        return Response(
            content=content,
            model=data.get("model", self.model),
            finish_reason=data.get("stop_reason"),
            tool_calls=tool_calls,
            usage=data.get("usage"),
        )

    def _parse_stream_chunk(self, data: dict[str, Any]) -> StreamChunk:
        content = ""
        tool_call = None

        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_call = ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block["input"],
                )

        return StreamChunk(
            content=content,
            tool_call=tool_call,
            done=data.get("type") == "message_stop",
        )


class GeminiProvider(BaseProvider):
    """Google Gemini API provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-2.0-flash")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout = config.get("timeout", 120)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
            )
        return self._client

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert messages to Gemini format."""
        contents = []
        system_instruction = ""

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append(
                    {
                        "role": role,
                        "parts": [{"text": msg.content}],
                    }
                )

        return contents, system_instruction

    def _format_tools(self, tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        """Convert OpenAI-style tools to Gemini format."""
        if not tools:
            return {}

        function_declarations = []
        for tool in tools:
            function_declarations.append(tool["function"])

        return {"function_declarations": function_declarations}

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> Response:
        client = self._get_client()
        model = kwargs.get("model", self.model)

        contents, system_instruction = self._format_messages(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generation_config": {
                "max_output_tokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
            },
        }

        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        if tools:
            payload["tools"] = self._format_tools(tools)

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    async def stream(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, **kwargs) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        model = kwargs.get("model", self.model)

        contents, system_instruction = self._format_messages(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generation_config": {
                "max_output_tokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
            },
        }

        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        if tools:
            payload["tools"] = self._format_tools(tools)

        url = f"{self.base_url}/models/{model}:streamGenerateContent?key={self.api_key}&alt=sse"

        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if not data:
                    continue

                chunk_data = json.loads(data)
                yield self._parse_stream_chunk(chunk_data)

    async def list_models(self) -> list[ModelInfo]:
        client = self._get_client()
        url = f"{self.base_url}/models?key={self.api_key}"

        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            models = []
            for m in data.get("models", []):
                models.append(
                    ModelInfo(
                        id=m["name"].split("/")[-1],
                        name=m.get("displayName", m["name"]),
                        provider="google",
                        context_window=m.get("inputTokenLimit", 32000),
                        supports_vision=True,
                    )
                )
            return models
        except Exception:
            return [
                ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", provider="google", context_window=1000000),
                ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro", provider="google", context_window=1000000),
            ]

    def _parse_response(self, data: dict[str, Any]) -> Response:
        content = ""
        tool_calls = []

        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    content += part["text"]
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append(
                        ToolCall(
                            id=str(id(fc)),  # Gemini doesn't have IDs
                            name=fc["name"],
                            arguments=fc["args"],
                        )
                    )

        return Response(
            content=content,
            model=data.get("modelVersion", self.model),
            tool_calls=tool_calls,
        )

    def _parse_stream_chunk(self, data: dict[str, Any]) -> StreamChunk:
        content = ""
        tool_call = None

        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    content += part["text"]
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_call = ToolCall(
                        id=str(id(fc)),
                        name=fc["name"],
                        arguments=fc["args"],
                    )

        return StreamChunk(
            content=content,
            tool_call=tool_call,
            done=data.get("candidates", [{}])[0].get("finishReason") is not None,
        )


class OllamaProvider(OpenAIProvider):
    """Ollama local models provider (OpenAI-compatible API)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(
            {
                **config,
                "base_url": config.get("base_url", "http://localhost:11434/v1"),
                "model": config.get("model", "llama3.2"),
            }
        )
        self.provider_type = "ollama"

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._get_client()
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for m in data.get("models", []):
                models.append(
                    ModelInfo(
                        id=m.get("name", ""),
                        name=m.get("name", ""),
                        provider="ollama",
                        context_window=m.get("details", {}).get("context_length", 4096),
                    )
                )
            return models
        except Exception:
            return [ModelInfo(id="llama3.2", name="Llama 3.2", provider="ollama", context_window=128000)]


class GroqProvider(OpenAIProvider):
    """Groq API provider (OpenAI-compatible)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(
            {
                **config,
                "base_url": "https://api.groq.com/openai/v1",
                "model": config.get("model", "mixtral-8x7b-32768"),
            }
        )
        self.provider_type = "groq"

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="llama-3.3-70b-versatile", name="Llama 3.3 70B", provider="groq", context_window=128000),
            ModelInfo(id="mixtral-8x7b-32768", name="Mixtral 8x7B", provider="groq", context_window=32768),
            ModelInfo(id="gemma2-9b-it", name="Gemma 2 9B", provider="groq", context_window=8192),
        ]


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek API provider (OpenAI-compatible)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(
            {
                **config,
                "base_url": "https://api.deepseek.com/v1",
                "model": config.get("model", "deepseek-chat"),
            }
        )
        self.provider_type = "deepseek"

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="deepseek-chat", name="DeepSeek Chat", provider="deepseek", context_window=64000),
            ModelInfo(id="deepseek-coder", name="DeepSeek Coder", provider="deepseek", context_window=64000),
        ]


class MistralProvider(OpenAIProvider):
    """Mistral AI provider (OpenAI-compatible)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(
            {
                **config,
                "base_url": "https://api.mistral.ai/v1",
                "model": config.get("model", "mistral-large-latest"),
            }
        )
        self.provider_type = "mistral"

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="mistral-large-latest", name="Mistral Large", provider="mistral", context_window=128000),
            ModelInfo(id="mistral-small-latest", name="Mistral Small", provider="mistral", context_window=32000),
            ModelInfo(id="codestral-latest", name="Codestral", provider="mistral", context_window=32000),
        ]


PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GeminiProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "groq": GroqProvider,
    "deepseek": DeepSeekProvider,
    "mistral": MistralProvider,
    "openai-compatible": OpenAIProvider,
    "opencode-zen": OpenAIProvider,
    "opencode-go": OpenAIProvider,
}


async def create_provider(
    provider_type: str,
    config: dict[str, Any],
) -> BaseProvider:
    """Factory function to create a provider instance."""
    provider_class = PROVIDER_REGISTRY.get(provider_type.lower())
    if not provider_class:
        raise ValueError(f"Unknown provider type: {provider_type}")
    return provider_class(config)


async def detect_provider(base_url: str) -> str:
    """Auto-detect the provider type from the base URL."""
    if "ollama" in base_url or "lmstudio" in base_url:
        return "openai-compatible"
    elif "groq" in base_url:
        return "groq"
    elif "deepseek" in base_url:
        return "deepseek"
    elif "mistral" in base_url:
        return "mistral"
    elif "anthropic" in base_url:
        return "anthropic"
    elif "google" in base_url or "generativelanguage" in base_url:
        return "gemini"
    elif "openai" in base_url:
        return "openai"
    else:
        return "openai-compatible"
