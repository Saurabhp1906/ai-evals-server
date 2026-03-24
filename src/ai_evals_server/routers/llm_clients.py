"""
Shared LLM client abstractions used by playground.py and agents.py.
"""
import json
from typing import Protocol

import anthropic
import openai as openai_lib
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..auth.utils import decrypt_api_key
from ..models.orm import ConnectionORM
from ..models.schemas import ConnectionType

# ---------------------------------------------------------------------------
# Built-in tool definitions
# ---------------------------------------------------------------------------

CLAUDE_TOOL_DEFINITIONS: dict[str, dict] = {
    "web_search": {
        "type": "web_search_20250305",
        "name": "web_search",
    },
}

OPENAI_TOOL_DEFINITIONS: dict[str, dict] = {
    "web_search": {
        "type": "web_search",
    },
}

_DEFAULT_MODELS: dict[ConnectionType, str] = {
    ConnectionType.claude: "claude-sonnet-4-6",
    ConnectionType.openai: "gpt-4o",
    ConnectionType.azure_openai: "",
}


# ---------------------------------------------------------------------------
# Response serialization helper
# ---------------------------------------------------------------------------

def serialize_response(response: object) -> dict:
    """Serialize an SDK response object to a plain JSON-compatible dict."""
    errors: list[str] = []
    try:
        return response.model_dump(mode="json")  # type: ignore[attr-defined]
    except Exception as e:
        errors.append(f"model_dump: {e}")
    try:
        return json.loads(response.model_dump_json())  # type: ignore[attr-defined]
    except Exception as e:
        errors.append(f"model_dump_json: {e}")
    try:
        return json.loads(response.json())  # type: ignore[attr-defined]
    except Exception as e:
        errors.append(f"json(): {e}")
    try:
        return json.loads(json.dumps(response.__dict__, default=str))
    except Exception as e:
        errors.append(f"__dict__: {e}")
    try:
        return json.loads(json.dumps(vars(response), default=str))
    except Exception as e:
        errors.append(f"vars(): {e}")
    return {"_error": "could not serialize response", "_details": errors}


# ---------------------------------------------------------------------------
# Unified LLM client abstraction
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None, response_format: dict | None = None) -> str: ...


def _openai_chat_create(client, kwargs: dict, max_tokens: int | None):
    """Call chat.completions.create, falling back to max_completion_tokens if max_tokens is rejected."""
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    try:
        return client.chat.completions.create(**kwargs)
    except openai_lib.BadRequestError as e:
        if max_tokens is not None and "max_completion_tokens" in str(e):
            kwargs.pop("max_tokens", None)
            kwargs["max_completion_tokens"] = max_tokens
            return client.chat.completions.create(**kwargs)
        raise


class ClaudeClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def _extract_text(self, content) -> str:
        parts = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
        return "\n".join(parts).strip()

    def _build_kwargs(self, model: str, user_message: str, max_tokens: int | None, tools: list[str] | None) -> dict:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens if max_tokens is not None else 1024,
            "messages": [{"role": "user", "content": user_message}],
        }
        tool_defs = [CLAUDE_TOOL_DEFINITIONS[t] for t in (tools or []) if t in CLAUDE_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = {"type": "required"}
        return kwargs

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None, response_format: dict | None = None) -> str:
        response = self._client.messages.create(**self._build_kwargs(model, user_message, max_tokens, tools))
        return self._extract_text(response.content)

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str], response_format: dict | None = None) -> tuple[str, dict]:
        response = self._client.messages.create(**self._build_kwargs(model, user_message, max_tokens, tools))
        return self._extract_text(response.content), serialize_response(response)


class OpenAIChatClient:
    """OpenAI Chat Completions API."""
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = openai_lib.OpenAI(api_key=api_key, base_url=base_url)

    def _build_kwargs(self, model: str, user_message: str, response_format: dict | None) -> dict:
        kwargs: dict = {"model": model, "messages": [{"role": "user", "content": user_message}]}
        if response_format is not None:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "schema": response_format, "strict": False}}
        return kwargs

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None, response_format: dict | None = None) -> str:
        response = _openai_chat_create(self._client, self._build_kwargs(model, user_message, response_format), max_tokens)
        return (response.choices[0].message.content or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str], response_format: dict | None = None) -> tuple[str, dict]:
        response = _openai_chat_create(self._client, self._build_kwargs(model, user_message, response_format), max_tokens)
        return (response.choices[0].message.content or "").strip(), serialize_response(response)


class OpenAIResponsesClient:
    """OpenAI Responses API."""
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = openai_lib.OpenAI(api_key=api_key, base_url=base_url)

    def _build_kwargs(self, model: str, user_message: str, max_tokens: int | None, tools: list[str] | None, response_format: dict | None) -> dict:
        kwargs: dict = {"model": model, "input": user_message}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if response_format is not None:
            kwargs["text"] = {"format": {"type": "json_schema", "name": "output", "schema": response_format, "strict": False}}
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in (tools or []) if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        return kwargs

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None, response_format: dict | None = None) -> str:
        response = self._client.responses.create(**self._build_kwargs(model, user_message, max_tokens, tools, response_format))
        return (response.output_text or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str], response_format: dict | None = None) -> tuple[str, dict]:
        response = self._client.responses.create(**self._build_kwargs(model, user_message, max_tokens, tools, response_format))
        return (response.output_text or "").strip(), serialize_response(response)


class AzureOpenAIChatClient:
    """Azure OpenAI Chat Completions API."""
    def __init__(self, api_key: str, azure_endpoint: str, azure_deployment: str, api_version: str) -> None:
        self._client = openai_lib.AzureOpenAI(api_key=api_key, azure_endpoint=azure_endpoint, api_version=api_version)
        self._deployment = azure_deployment

    def _build_kwargs(self, user_message: str, response_format: dict | None) -> dict:
        kwargs: dict = {"model": self._deployment, "messages": [{"role": "user", "content": user_message}]}
        if response_format is not None:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "schema": response_format, "strict": False}}
        return kwargs

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None, response_format: dict | None = None) -> str:
        response = _openai_chat_create(self._client, self._build_kwargs(user_message, response_format), max_tokens)
        return (response.choices[0].message.content or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str], response_format: dict | None = None) -> tuple[str, dict]:
        response = _openai_chat_create(self._client, self._build_kwargs(user_message, response_format), max_tokens)
        return (response.choices[0].message.content or "").strip(), serialize_response(response)


class AzureOpenAIResponsesClient:
    """Azure OpenAI Responses API."""
    def __init__(self, api_key: str, azure_endpoint: str, azure_deployment: str, api_version: str) -> None:
        self._client = openai_lib.AzureOpenAI(api_key=api_key, azure_endpoint=azure_endpoint, api_version=api_version)
        self._deployment = azure_deployment

    def _build_kwargs(self, user_message: str, max_tokens: int | None, tools: list[str] | None, response_format: dict | None) -> dict:
        kwargs: dict = {"model": self._deployment, "input": user_message}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if response_format is not None:
            kwargs["text"] = {"format": {"type": "json_schema", "name": "output", "schema": response_format, "strict": False}}
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in (tools or []) if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        return kwargs

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None, response_format: dict | None = None) -> str:
        response = self._client.responses.create(**self._build_kwargs(user_message, max_tokens, tools, response_format))
        return (response.output_text or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str], response_format: dict | None = None) -> tuple[str, dict]:
        response = self._client.responses.create(**self._build_kwargs(user_message, max_tokens, tools, response_format))
        return (response.output_text or "").strip(), serialize_response(response)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

AnyLLMClient = ClaudeClient | OpenAIChatClient | OpenAIResponsesClient | AzureOpenAIChatClient | AzureOpenAIResponsesClient


def client_from_connection(conn: ConnectionORM, use_responses_api: bool | None = None) -> AnyLLMClient:
    plain_key = decrypt_api_key(conn.api_key)
    if conn.type == ConnectionType.claude:
        return ClaudeClient(api_key=plain_key)
    azure_kwargs = dict(
        api_key=plain_key,
        azure_endpoint=conn.azure_endpoint or "",
        azure_deployment=conn.azure_deployment or "",
        api_version=conn.azure_api_version,
    )
    responses = bool(use_responses_api)
    if conn.type == ConnectionType.openai:
        if responses:
            return OpenAIResponsesClient(api_key=plain_key, base_url=conn.base_url)
        return OpenAIChatClient(api_key=plain_key, base_url=conn.base_url)
    # azure_openai
    if responses:
        return AzureOpenAIResponsesClient(**azure_kwargs)
    return AzureOpenAIChatClient(**azure_kwargs)


def resolve_client(connection_id: str | None, db: Session, use_responses_api: bool | None = None) -> AnyLLMClient:
    if not connection_id:
        raise HTTPException(status_code=400, detail="A connection must be selected to run.")
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found")
    return client_from_connection(conn, use_responses_api=use_responses_api)


def resolve_model(connection_id: str | None, db: Session, model_override: str | None = None) -> str:
    if not connection_id:
        raise HTTPException(status_code=400, detail="A connection must be selected to run.")
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found")
    if conn.type == ConnectionType.azure_openai and conn.azure_deployment:
        return conn.azure_deployment
    return model_override or _DEFAULT_MODELS.get(conn.type, "claude-sonnet-4-6")
