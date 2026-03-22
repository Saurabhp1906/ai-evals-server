import asyncio
import json
import anthropic
import openai as openai_lib
from fastapi import APIRouter, Depends, HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.utils import decrypt_api_key
from ..database import get_db
from ..models.orm import AgentChatORM, AgentChatSummaryORM, AgentMessageORM, AgentORM, ConnectionORM, McpServerORM
from ..models.schemas import (
    AgentChatSchema, AgentCreate, AgentSchema, AgentSendMessageRequest, AgentUpdate,
    ConnectionType,
)

router = APIRouter(prefix="/agents", tags=["agents"])

_DEFAULT_MODELS = {
    ConnectionType.claude: "claude-sonnet-4-6",
    ConnectionType.openai: "gpt-4o",
    ConnectionType.azure_openai: "",
}


def _get_agent(agent_id: str, db: Session, current_user: CurrentUser) -> AgentORM:
    agent = db.get(AgentORM, agent_id)
    if not agent or agent.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _build_llm_messages(messages: list[AgentMessageORM]) -> list[dict]:
    """Convert ORM messages to LLM message dicts. Summary becomes bracketed context pair."""
    result: list[dict] = []
    for m in messages:
        if m.role == "summary":
            result.append({"role": "user", "content": f"[Summary of earlier conversation: {m.content}]"})
            result.append({"role": "assistant", "content": "Understood, I have context from our earlier conversation."})
        else:
            result.append({"role": m.role, "content": m.content})
    return result


def _mcp_headers(mcp: McpServerORM) -> dict[str, str]:
    if mcp.oauth_access_token:
        return {"Authorization": f"Bearer {decrypt_api_key(mcp.oauth_access_token)}"}
    if mcp.token:
        return {"Authorization": f"Bearer {decrypt_api_key(mcp.token)}"}
    return {}


async def _run_chat_with_mcp_async(
    agent: AgentORM,
    messages: list[AgentMessageORM],
    conn: ConnectionORM,
    mcp: McpServerORM,
) -> str:
    plain_key = decrypt_api_key(conn.api_key)
    model = agent.model or _DEFAULT_MODELS.get(conn.type, "claude-sonnet-4-6")
    max_tokens = agent.max_output_tokens or 1024
    tool_filter: list[str] | None = agent.mcp_tool_filter
    llm_messages = _build_llm_messages(messages)

    async with streamablehttp_client(mcp.url, headers=_mcp_headers(mcp)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            available = [t for t in tools_result.tools if tool_filter is None or t.name in tool_filter]

            if conn.type == ConnectionType.claude:
                client = anthropic.Anthropic(api_key=plain_key)
                claude_tools = [
                    {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
                    for t in available
                ]
                while True:
                    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": llm_messages, "tools": claude_tools}
                    if agent.system_prompt:
                        kwargs["system"] = agent.system_prompt
                    response = client.messages.create(**kwargs)
                    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                    if not tool_use_blocks:
                        return "\n".join(b.text for b in response.content if hasattr(b, "text")).strip()
                    llm_messages.append({"role": "assistant", "content": response.content})
                    tool_results = []
                    for block in tool_use_blocks:
                        result = await session.call_tool(block.name, block.input)
                        result_text = "\n".join(b.text for b in result.content if hasattr(b, "text"))
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_text})
                    llm_messages.append({"role": "user", "content": tool_results})

            # OpenAI / Azure
            if conn.type == ConnectionType.azure_openai:
                oa_client: openai_lib.OpenAI | openai_lib.AzureOpenAI = openai_lib.AzureOpenAI(
                    api_key=plain_key, azure_endpoint=conn.azure_endpoint or "", api_version=conn.azure_api_version,
                )
                deployment = conn.azure_deployment or model
            else:
                oa_client = openai_lib.OpenAI(api_key=plain_key, base_url=conn.base_url)
                deployment = model

            if agent.system_prompt:
                llm_messages = [{"role": "system", "content": agent.system_prompt}] + llm_messages

            openai_tools = [
                {"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.inputSchema}}
                for t in available
            ]

            while True:
                kwargs2: dict = {"model": deployment, "messages": llm_messages}
                if openai_tools:
                    kwargs2["tools"] = openai_tools
                if max_tokens:
                    kwargs2["max_tokens"] = max_tokens
                try:
                    resp = oa_client.chat.completions.create(**kwargs2)
                except openai_lib.BadRequestError as e:
                    if "max_completion_tokens" in str(e):
                        kwargs2.pop("max_tokens", None)
                        kwargs2["max_completion_tokens"] = max_tokens
                        resp = oa_client.chat.completions.create(**kwargs2)
                    else:
                        raise
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    return (msg.content or "").strip()
                llm_messages.append(msg)
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    result = await session.call_tool(tc.function.name, args)
                    result_text = "\n".join(b.text for b in result.content if hasattr(b, "text"))
                    llm_messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})


def _run_chat(
    agent: AgentORM,
    messages: list[AgentMessageORM],
    db: Session,
) -> str:
    """Run LLM with full chat history. Dispatches to MCP tool loop if configured."""
    if not agent.connection_id:
        raise HTTPException(status_code=400, detail="Agent has no connection configured")

    conn = db.get(ConnectionORM, agent.connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    # MCP tool calling path
    if agent.mcp_server_id:
        mcp = db.get(McpServerORM, agent.mcp_server_id)
        if mcp:
            return asyncio.run(_run_chat_with_mcp_async(agent, messages, conn, mcp))

    # Plain LLM path (no MCP)
    plain_key = decrypt_api_key(conn.api_key)
    model = agent.model or _DEFAULT_MODELS.get(conn.type, "claude-sonnet-4-6")
    max_tokens = agent.max_output_tokens or 1024
    llm_messages = _build_llm_messages(messages)
    system = agent.system_prompt or ""

    if conn.type == ConnectionType.claude:
        client = anthropic.Anthropic(api_key=plain_key)
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": llm_messages}
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return "\n".join(b.text for b in response.content if hasattr(b, "text")).strip()

    if system:
        llm_messages = [{"role": "system", "content": system}] + llm_messages

    if conn.type == ConnectionType.azure_openai:
        oa_client: openai_lib.OpenAI | openai_lib.AzureOpenAI = openai_lib.AzureOpenAI(
            api_key=plain_key, azure_endpoint=conn.azure_endpoint or "", api_version=conn.azure_api_version,
        )
        deployment = conn.azure_deployment or model
    else:
        oa_client = openai_lib.OpenAI(api_key=plain_key, base_url=conn.base_url)
        deployment = model

    try:
        response = oa_client.chat.completions.create(model=deployment, messages=llm_messages, max_tokens=max_tokens)
    except openai_lib.BadRequestError as e:
        if "max_completion_tokens" in str(e):
            response = oa_client.chat.completions.create(model=deployment, messages=llm_messages, max_completion_tokens=max_tokens)
        else:
            raise
    return (response.choices[0].message.content or "").strip()


def _summarize(agent: AgentORM, messages: list[AgentMessageORM], db: Session) -> str:
    """Call LLM to summarize the given messages."""
    conversation = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
    summary_request = AgentMessageORM(
        chat_id=messages[0].chat_id,
        role="user",
        content=f"Please summarize the following conversation in a few concise sentences, preserving key context:\n\n{conversation}",
    )
    return _run_chat(agent, [summary_request], db)


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=AgentSchema, status_code=201)
def create_agent(body: AgentCreate, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> AgentSchema:
    agent = AgentORM(
        org_id=current_user.org_id,
        name=body.name,
        system_prompt=body.system_prompt,
        connection_id=body.connection_id,
        model=body.model,
        max_output_tokens=body.max_output_tokens,
        mcp_server_id=body.mcp_server_id,
        mcp_tool_filter=body.mcp_tool_filter,
        tools=body.tools,
        summarize_after=body.summarize_after,
        created_by_email=current_user.email,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return AgentSchema.model_validate(agent)


@router.get("", response_model=list[AgentSchema])
def list_agents(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> list[AgentSchema]:
    agents = db.query(AgentORM).filter(AgentORM.org_id == current_user.org_id).order_by(AgentORM.created_at.desc()).all()
    return [AgentSchema.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentSchema)
def get_agent(agent_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> AgentSchema:
    return AgentSchema.model_validate(_get_agent(agent_id, db, current_user))


@router.patch("/{agent_id}", response_model=AgentSchema)
def update_agent(agent_id: str, body: AgentUpdate, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> AgentSchema:
    agent = _get_agent(agent_id, db, current_user)
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(agent, field, val)
    db.commit()
    db.refresh(agent)
    return AgentSchema.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> None:
    agent = _get_agent(agent_id, db, current_user)
    db.delete(agent)
    db.commit()


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

@router.post("/{agent_id}/chats", response_model=AgentChatSchema, status_code=201)
def create_chat(agent_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> AgentChatSchema:
    _get_agent(agent_id, db, current_user)
    chat_count = db.query(AgentChatORM).filter(AgentChatORM.agent_id == agent_id).count()
    if chat_count >= 5:
        raise HTTPException(status_code=400, detail="Maximum of 5 chats per agent reached. Delete an existing chat to create a new one.")
    chat = AgentChatORM(agent_id=agent_id)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return AgentChatSchema.model_validate(chat)


@router.get("/{agent_id}/chats", response_model=list[AgentChatSchema])
def list_chats(agent_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> list[AgentChatSchema]:
    _get_agent(agent_id, db, current_user)
    chats = db.query(AgentChatORM).filter(AgentChatORM.agent_id == agent_id).order_by(AgentChatORM.created_at.desc()).all()
    return [AgentChatSchema.model_validate(c) for c in chats]


@router.get("/{agent_id}/chats/{chat_id}", response_model=AgentChatSchema)
def get_chat(agent_id: str, chat_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> AgentChatSchema:
    _get_agent(agent_id, db, current_user)
    chat = db.get(AgentChatORM, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return AgentChatSchema.model_validate(chat)


@router.delete("/{agent_id}/chats/{chat_id}", status_code=204)
def delete_chat(agent_id: str, chat_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> None:
    _get_agent(agent_id, db, current_user)
    chat = db.get(AgentChatORM, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    db.delete(chat)
    db.commit()


@router.post("/{agent_id}/chats/{chat_id}/messages", response_model=AgentChatSchema)
def send_message(
    agent_id: str,
    chat_id: str,
    body: AgentSendMessageRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentChatSchema:
    agent = _get_agent(agent_id, db, current_user)
    chat = db.get(AgentChatORM, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Load all real messages (user + assistant only)
    all_messages = (
        db.query(AgentMessageORM)
        .filter(AgentMessageORM.chat_id == chat_id)
        .order_by(AgentMessageORM.created_at)
        .all()
    )

    if len(all_messages) >= 100:
        raise HTTPException(status_code=400, detail="Chat has reached the maximum of 100 messages. Start a new chat to continue.")

    # Get the latest summary (if any)
    latest_summary = (
        db.query(AgentChatSummaryORM)
        .filter(AgentChatSummaryORM.chat_id == chat_id)
        .order_by(AgentChatSummaryORM.created_at.desc())
        .first()
    )

    # Determine messages not yet covered by the latest summary
    if latest_summary and latest_summary.to_message_id:
        to_msg = db.get(AgentMessageORM, latest_summary.to_message_id)
        recent = [m for m in all_messages if to_msg and m.created_at > to_msg.created_at] if to_msg else all_messages
    else:
        recent = all_messages

    # Auto-summarize if unsummarized messages hit the threshold
    if len(recent) >= agent.summarize_after:
        summary_text = _summarize(agent, recent, db)
        new_summary = AgentChatSummaryORM(
            chat_id=chat_id,
            content=summary_text,
            from_message_id=recent[0].id,
            to_message_id=recent[-1].id,
        )
        db.add(new_summary)
        db.flush()
        latest_summary = new_summary
        recent = []

    # Add user message
    user_msg = AgentMessageORM(chat_id=chat_id, role="user", content=body.content)
    db.add(user_msg)
    db.flush()

    # Build LLM context: latest summary (as bracketed message) + unsummarized messages + new user message
    context: list[AgentMessageORM] = []
    if latest_summary:
        context.append(AgentMessageORM(
            chat_id=chat_id, role="summary", content=latest_summary.content
        ))
    context.extend(recent)
    context.append(user_msg)

    # Run LLM
    assistant_text = _run_chat(agent, context, db)

    # Save assistant response
    db.add(AgentMessageORM(chat_id=chat_id, role="assistant", content=assistant_text))
    db.commit()
    db.refresh(chat)
    return AgentChatSchema.model_validate(chat)
