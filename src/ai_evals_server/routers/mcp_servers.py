import asyncio
from fastapi import APIRouter, Depends, HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.utils import decrypt_api_key, encrypt_api_key
from ..database import get_db
from ..models.orm import McpServerORM
from ..models.schemas import McpServerCreate, McpServerSchema, McpServerUpdate, McpToolSchema

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


def _to_schema(server: McpServerORM) -> McpServerSchema:
    return McpServerSchema(
        id=server.id,
        name=server.name,
        url=server.url,
        has_token=bool(server.token),
        created_at=server.created_at,
    )


def _headers(server: McpServerORM) -> dict[str, str]:
    if server.token:
        return {"Authorization": f"Bearer {decrypt_api_key(server.token)}"}
    return {}


@router.post("", response_model=McpServerSchema, status_code=201)
def create_mcp_server(
    body: McpServerCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> McpServerSchema:
    encrypted_token = encrypt_api_key(body.token) if body.token else None
    server = McpServerORM(org_id=current_user.org_id, name=body.name, url=body.url, token=encrypted_token)
    db.add(server)
    db.commit()
    db.refresh(server)
    return _to_schema(server)


@router.get("", response_model=list[McpServerSchema])
def list_mcp_servers(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[McpServerSchema]:
    servers = db.query(McpServerORM).filter(McpServerORM.org_id == current_user.org_id).all()
    return [_to_schema(s) for s in servers]


@router.put("/{server_id}", response_model=McpServerSchema)
def update_mcp_server(
    server_id: str,
    body: McpServerUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> McpServerSchema:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if body.name is not None:
        server.name = body.name
    if body.url is not None:
        server.url = body.url
    if body.token is not None:
        server.token = encrypt_api_key(body.token) if body.token else None
    db.commit()
    db.refresh(server)
    return _to_schema(server)


@router.get("/{server_id}/tools", response_model=list[McpToolSchema])
def list_mcp_tools(
    server_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[McpToolSchema]:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")

    headers = _headers(server)

    async def _fetch_tools():
        async with streamablehttp_client(server.url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools

    try:
        tools = asyncio.run(_fetch_tools())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not connect to MCP server: {exc}")

    return [
        McpToolSchema(
            name=t.name,
            description=t.description or "",
            parameters=t.inputSchema,
        )
        for t in tools
    ]


@router.delete("/{server_id}", status_code=204)
def delete_mcp_server(
    server_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")
    db.delete(server)
    db.commit()
