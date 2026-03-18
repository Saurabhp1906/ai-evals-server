import anthropic
import openai as openai_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.utils import decrypt_api_key, encrypt_api_key
from ..database import get_db
from ..models.orm import ConnectionORM
from ..models.schemas import ConnectionCreate, ConnectionResponse, ConnectionType, ConnectionUpdate

router = APIRouter(prefix="/connections", tags=["connections"])


def _verify_connection(body: ConnectionCreate) -> None:
    """Make a minimal API call to confirm credentials work. Raises HTTPException on failure."""
    try:
        if body.type == ConnectionType.claude:
            client = anthropic.Anthropic(api_key=body.api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
        elif body.type == ConnectionType.openai:
            client = openai_lib.OpenAI(api_key=body.api_key, base_url=body.base_url)
            client.responses.create(model="gpt-4o-mini", input="hi", max_output_tokens=1)
        elif body.type == ConnectionType.azure_openai:
            client = openai_lib.AzureOpenAI(
                api_key=body.api_key,
                azure_endpoint=body.azure_endpoint or "",
                api_version=body.azure_api_version,
            )
            client.responses.create(model=body.azure_deployment or "", input="hi", max_output_tokens=2000)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Connection verification failed: {exc}")


def _to_response(conn: ConnectionORM) -> ConnectionResponse:
    return ConnectionResponse(
        id=conn.id,
        name=conn.name,
        type=conn.type,
        api_key_hint=f"...{decrypt_api_key(conn.api_key)[-4:]}",
        azure_endpoint=conn.azure_endpoint,
        azure_deployment=conn.azure_deployment,
        azure_api_version=conn.azure_api_version,
        base_url=conn.base_url,
        created_at=conn.created_at,
    )


@router.post("", response_model=ConnectionResponse, status_code=201)
def create_connection(
    body: ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConnectionResponse:
    if body.type.value == "azure_openai":
        if not body.azure_endpoint:
            raise HTTPException(status_code=422, detail="azure_endpoint is required for azure_openai connections")
        if not body.azure_deployment:
            raise HTTPException(status_code=422, detail="azure_deployment is required for azure_openai connections")

    existing = (
        db.query(ConnectionORM)
        .filter(ConnectionORM.org_id == current_user.org_id, ConnectionORM.type == body.type)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A {body.type.value} connection already exists. Only 1 connection per provider type is allowed.",
        )

    _verify_connection(body)

    data = body.model_dump()
    data["api_key"] = encrypt_api_key(data["api_key"])
    conn = ConnectionORM(**data, org_id=current_user.org_id)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return _to_response(conn)


@router.get("", response_model=list[ConnectionResponse])
def list_connections(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ConnectionResponse]:
    rows = db.query(ConnectionORM).filter(ConnectionORM.org_id == current_user.org_id).all()
    return [_to_response(c) for c in rows]


@router.get("/{connection_id}", response_model=ConnectionResponse)
def get_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConnectionResponse:
    conn = db.get(ConnectionORM, connection_id)
    if not conn or conn.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return _to_response(conn)


@router.put("/{connection_id}", response_model=ConnectionResponse)
def update_connection(
    connection_id: str,
    body: ConnectionUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConnectionResponse:
    conn = db.get(ConnectionORM, connection_id)
    if not conn or conn.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    data = {k: v for k, v in body.model_dump(exclude_none=True).items() if v != ""}

    # Verify only if something other than name is changing
    actually_changed = {
        k: v for k, v in data.items()
        if k != "name" and v != getattr(conn, k, None)
    }
    if actually_changed:
        verify_body = ConnectionCreate(
            name=conn.name,
            type=conn.type,
            api_key=data.get("api_key") or decrypt_api_key(conn.api_key),
            azure_endpoint=data.get("azure_endpoint") or conn.azure_endpoint,
            azure_deployment=data.get("azure_deployment") or conn.azure_deployment,
            azure_api_version=data.get("azure_api_version") or conn.azure_api_version,
            base_url=data.get("base_url") or conn.base_url,
        )
        _verify_connection(verify_body)

    if "api_key" in data:
        data["api_key"] = encrypt_api_key(data["api_key"])
    for field, value in data.items():
        setattr(conn, field, value)
    db.commit()
    db.refresh(conn)
    return _to_response(conn)


@router.delete("/{connection_id}", status_code=204)
def delete_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    conn = db.get(ConnectionORM, connection_id)
    if not conn or conn.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(conn)
    db.commit()
