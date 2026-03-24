"""
Shared MCP tool-loop helpers used by playground.py and agents.py.
"""
import asyncio
import json

import openai as openai_lib
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy.orm import Session

from ..auth.utils import decrypt_api_key
from ..models.orm import ConnectionORM, McpServerORM
from ..models.schemas import ConnectionType
from .llm_clients import OPENAI_TOOL_DEFINITIONS, _DEFAULT_MODELS


def get_mcp_auth_headers(mcp: McpServerORM, db: Session) -> dict[str, str]:
    """Return auth headers for an MCP server, refreshing OAuth token if near expiry."""
    from .mcp_servers import _get_auth_headers
    return _get_auth_headers(mcp, db)


async def _mcp_complete_responses_async(
    openai_client: openai_lib.OpenAI | openai_lib.AzureOpenAI,
    deployment: str,
    user_message: str | list,
    max_tokens: int | None,
    mcp_url: str,
    mcp_headers: dict[str, str] | None = None,
    tool_filter: list[str] | None = None,
    prompt_tools: list[str] | None = None,
) -> tuple[str, list[dict], dict]:
    """MCP tool loop via Responses API (stateful, uses previous_response_id)."""
    from .llm_clients import serialize_response
    tool_calls_trace: list[dict] = []

    async with streamablehttp_client(mcp_url, headers=mcp_headers or {}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()

            openai_tools = [
                OPENAI_TOOL_DEFINITIONS[t] for t in (prompt_tools or []) if t in OPENAI_TOOL_DEFINITIONS
            ] + [
                {"type": "function", "name": t.name, "description": t.description or "", "parameters": t.inputSchema}
                for t in tools_result.tools
                if tool_filter is None or t.name in tool_filter
            ]

            kwargs: dict = {"model": deployment, "input": user_message, "tools": openai_tools}
            if max_tokens:
                kwargs["max_output_tokens"] = max_tokens

            response = openai_client.responses.create(**kwargs)
            while True:
                function_calls = [item for item in response.output if item.type == "function_call"]
                if not function_calls:
                    break
                tool_results = []
                for fc in function_calls:
                    args = json.loads(fc.arguments)
                    result = await session.call_tool(fc.name, args)
                    result_text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
                    tool_calls_trace.append({"tool": fc.name, "args": args, "result": result_text})
                    tool_results.append({"type": "function_call_output", "call_id": fc.call_id, "output": result_text})
                response = openai_client.responses.create(
                    model=deployment, previous_response_id=response.id, input=tool_results, tools=openai_tools,
                )

            return (response.output_text or "").strip(), tool_calls_trace, serialize_response(response)


async def _mcp_complete_chat_async(
    openai_client: openai_lib.OpenAI | openai_lib.AzureOpenAI,
    deployment: str,
    user_message: str,
    max_tokens: int | None,
    mcp_url: str,
    mcp_headers: dict[str, str] | None = None,
    tool_filter: list[str] | None = None,
) -> tuple[str, list[dict], dict]:
    """MCP tool loop via Chat Completions API."""
    from .llm_clients import serialize_response
    tool_calls_trace: list[dict] = []

    async with streamablehttp_client(mcp_url, headers=mcp_headers or {}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()

            chat_tools = [
                {"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.inputSchema}}
                for t in tools_result.tools
                if tool_filter is None or t.name in tool_filter
            ]

            messages: list[dict] = [{"role": "user", "content": user_message}]
            while True:
                kwargs: dict = {"model": deployment, "messages": messages}
                if chat_tools:
                    kwargs["tools"] = chat_tools
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                try:
                    response = openai_client.chat.completions.create(**kwargs)
                except openai_lib.BadRequestError as e:
                    if "max_completion_tokens" in str(e):
                        kwargs.pop("max_tokens", None)
                        kwargs["max_completion_tokens"] = max_tokens
                        response = openai_client.chat.completions.create(**kwargs)
                    else:
                        raise

                msg = response.choices[0].message
                if not msg.tool_calls:
                    return (msg.content or "").strip(), tool_calls_trace, serialize_response(response)

                messages.append(msg)
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    result = await session.call_tool(tc.function.name, args)
                    result_text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
                    tool_calls_trace.append({"tool": tc.function.name, "args": args, "result": result_text})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})


def run_with_mcp(
    conn: ConnectionORM,
    user_message: str | list,
    max_tokens: int | None,
    mcp_url: str,
    mcp_headers: dict[str, str] | None = None,
    tool_filter: list[str] | None = None,
    use_responses_api: bool = False,
    model: str | None = None,
    prompt_tools: list[str] | None = None,
) -> tuple[str, list[dict], dict]:
    """Bridge sync → async MCP tool call loop (Responses API or Chat Completions)."""
    plain_key = decrypt_api_key(conn.api_key)
    if conn.type == ConnectionType.azure_openai:
        openai_client: openai_lib.OpenAI | openai_lib.AzureOpenAI = openai_lib.AzureOpenAI(
            api_key=plain_key,
            azure_endpoint=conn.azure_endpoint or "",
            api_version=conn.azure_api_version,
        )
        deployment = conn.azure_deployment or ""
    elif conn.type == ConnectionType.openai:
        openai_client = openai_lib.OpenAI(api_key=plain_key, base_url=conn.base_url)
        deployment = model or _DEFAULT_MODELS[ConnectionType.openai]
    else:
        raise HTTPException(status_code=400, detail="MCP is only supported with OpenAI and Azure OpenAI connections")

    if use_responses_api:
        return asyncio.run(_mcp_complete_responses_async(openai_client, deployment, user_message, max_tokens, mcp_url, mcp_headers, tool_filter, prompt_tools))
    return asyncio.run(_mcp_complete_chat_async(openai_client, deployment, user_message, max_tokens, mcp_url, mcp_headers, tool_filter))


def resolve_mcp(mcp_server_id: str | None, db: Session) -> tuple[str, dict[str, str]] | tuple[None, None]:
    """Return (url, headers) for an MCP server, or (None, None) if not set."""
    if not mcp_server_id:
        return None, None
    mcp = db.get(McpServerORM, mcp_server_id)
    if not mcp:
        raise HTTPException(status_code=404, detail=f"MCP server '{mcp_server_id}' not found")
    headers = get_mcp_auth_headers(mcp, db)
    return mcp.url, headers
