from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..database import get_db
from ..models.orm import McpServerORM
from ..models.schemas import McpServerCreate, McpServerSchema, McpServerUpdate

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


@router.post("", response_model=McpServerSchema, status_code=201)
def create_mcp_server(
    body: McpServerCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> McpServerSchema:
    server = McpServerORM(org_id=current_user.org_id, name=body.name, url=body.url)
    db.add(server)
    db.commit()
    db.refresh(server)
    return McpServerSchema.model_validate(server)


@router.get("", response_model=list[McpServerSchema])
def list_mcp_servers(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[McpServerSchema]:
    servers = db.query(McpServerORM).filter(McpServerORM.org_id == current_user.org_id).all()
    return [McpServerSchema.model_validate(s) for s in servers]


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
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(server, field, value)
    db.commit()
    db.refresh(server)
    return McpServerSchema.model_validate(server)


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
