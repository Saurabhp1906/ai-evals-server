import asyncio
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import check_resource_limit
from ..auth.utils import decrypt_api_key, encrypt_api_key
from ..database import get_db
from ..models.orm import McpServerORM
from ..models.schemas import (
    McpServerCreate,
    McpServerSchema,
    McpServerUpdate,
    McpToolSchema,
    OAuthCallbackRequest,
    OAuthStartRequest,
    OAuthStartResponse,
)

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])

# In-memory state store: state -> {server_id, code_verifier, token_endpoint, expires_at}
_oauth_states: dict[str, dict] = {}


def _to_schema(server: McpServerORM) -> McpServerSchema:
    return McpServerSchema(
        id=server.id,
        name=server.name,
        url=server.url,
        has_token=bool(server.token),
        has_oauth=bool(server.oauth_client_id),
        oauth_connected=bool(server.oauth_access_token),
        oauth_client_id=server.oauth_client_id,
        created_at=server.created_at,
    )


def _refresh_oauth_token(server: McpServerORM, db: Session) -> None:
    """Exchange refresh token for a new access token and update the DB."""
    if not server.oauth_refresh_token:
        return
    metadata = _discover_oauth_metadata(server.url)
    token_endpoint = metadata.get("token_endpoint")
    if not token_endpoint:
        raise ValueError("No token endpoint found during refresh")
    client_id = server.oauth_client_id or ""
    client_secret = decrypt_api_key(server.oauth_client_secret) if server.oauth_client_secret else None
    data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": decrypt_api_key(server.oauth_refresh_token),
        "client_id": client_id,
    }
    refresh_headers: dict[str, str] = {}
    if client_secret:
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        refresh_headers["Authorization"] = f"Basic {creds}"
    resp = httpx.post(token_endpoint, data=data, headers=refresh_headers, timeout=30)
    resp.raise_for_status()
    tokens = resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise ValueError("No access_token in refresh response")
    server.oauth_access_token = encrypt_api_key(access_token)
    if tokens.get("refresh_token"):
        server.oauth_refresh_token = encrypt_api_key(tokens["refresh_token"])
    if tokens.get("expires_in"):
        server.oauth_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
    db.commit()


def _get_auth_headers(server: McpServerORM, db: Session) -> dict[str, str]:
    """Return auth headers, refreshing OAuth token if expired or close to expiry."""
    if server.oauth_access_token:
        if (server.oauth_refresh_token and server.oauth_token_expiry and
                datetime.now(timezone.utc) >= server.oauth_token_expiry - timedelta(seconds=60)):
            try:
                _refresh_oauth_token(server, db)
            except Exception:
                pass  # fall through and use the existing token
        return {"Authorization": f"Bearer {decrypt_api_key(server.oauth_access_token)}"}
    if server.token:
        return {"Authorization": f"Bearer {decrypt_api_key(server.token)}"}
    return {}


def _verify_connection(url: str, headers: dict[str, str]) -> None:
    """Attempt to connect and list tools; raises 400 if unreachable."""
    async def _check():
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.list_tools()

    try:
        asyncio.run(_check())
    except Exception as exc:
        cause = exc
        if hasattr(exc, 'exceptions') and exc.exceptions:
            cause = exc.exceptions[0]
        raise HTTPException(status_code=400, detail=f"Could not connect to MCP server: {cause}")


def _discover_oauth_metadata(url: str) -> dict:
    """Fetch OAuth 2.0 metadata from MCP server's well-known endpoint."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for base in [origin, url.rstrip('/')]:
        try:
            resp = httpx.get(f"{base}/.well-known/oauth-authorization-server", follow_redirects=True, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            continue
    raise HTTPException(status_code=502, detail="No OAuth metadata found at this MCP server URL")


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return verifier, challenge


@router.post("", response_model=McpServerSchema, status_code=201)
def create_mcp_server(
    body: McpServerCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> McpServerSchema:
    check_resource_limit(
        db, current_user.org_id, current_user.org_plan, "mcp_servers",
        McpServerORM, current_user.org_custom_limits,
    )

    # Verify connection unless skipped (OAuth flow skips verification)
    if not body.skip_verify:
        headers = {"Authorization": f"Bearer {body.token}"} if body.token else {}
        _verify_connection(body.url, headers)

    encrypted_token = encrypt_api_key(body.token) if body.token else None
    encrypted_client_secret = encrypt_api_key(body.oauth_client_secret) if body.oauth_client_secret else None
    server = McpServerORM(
        org_id=current_user.org_id,
        name=body.name,
        url=body.url,
        token=encrypted_token,
        oauth_client_id=body.oauth_client_id,
        oauth_client_secret=encrypted_client_secret,
    )
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

    if not body.skip_verify and (body.url is not None or body.token is not None):
        new_url = body.url if body.url is not None else server.url
        if body.token is not None:
            new_headers = {"Authorization": f"Bearer {body.token}"} if body.token else {}
        else:
            new_headers = _get_auth_headers(server, db)
        _verify_connection(new_url, new_headers)

    if body.name is not None:
        server.name = body.name
    if body.url is not None:
        server.url = body.url
    if body.token is not None:
        server.token = encrypt_api_key(body.token) if body.token else None
    if body.oauth_client_id is not None:
        server.oauth_client_id = body.oauth_client_id or None
    if body.oauth_client_secret is not None:
        server.oauth_client_secret = encrypt_api_key(body.oauth_client_secret) if body.oauth_client_secret else None
    db.commit()
    db.refresh(server)
    return _to_schema(server)


@router.post("/{server_id}/oauth/start", response_model=OAuthStartResponse)
def start_oauth(
    server_id: str,
    body: OAuthStartRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> OAuthStartResponse:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")

    metadata = _discover_oauth_metadata(server.url)
    auth_endpoint = metadata.get("authorization_endpoint")
    token_endpoint = metadata.get("token_endpoint")
    if not auth_endpoint or not token_endpoint:
        raise HTTPException(status_code=502, detail="OAuth metadata missing authorization or token endpoint")

    # Use stored client_id or attempt dynamic client registration (RFC 7591)
    # Re-register if we have a client_id but no secret — previous registration was public client
    client_id = server.oauth_client_id
    needs_registration = not client_id or (client_id and not server.oauth_client_secret)
    if needs_registration:
        registration_endpoint = metadata.get("registration_endpoint")
        if not registration_endpoint:
            raise HTTPException(
                status_code=400,
                detail="Server does not support dynamic client registration. Please provide a Client ID manually.",
            )
        try:
            # Build registration payload from what the server advertises
            supported_grants = metadata.get("grant_types_supported", ["authorization_code"])
            supported_responses = metadata.get("response_types_supported", ["code"])
            supported_auth_methods = metadata.get("token_endpoint_auth_methods_supported", [])

            reg_payload: dict = {
                "client_name": "Evalpeak",
                "redirect_uris": [body.redirect_uri],
                "grant_types": [g for g in ["authorization_code", "refresh_token"] if g in supported_grants],
                "response_types": [r for r in ["code"] if r in supported_responses],
            }
            # Only set token_endpoint_auth_method if server advertises a preference
            if supported_auth_methods:
                # Prefer confidential client methods (get a secret) over public client (none)
                for method in ["client_secret_post", "client_secret_basic", "none"]:
                    if method in supported_auth_methods:
                        reg_payload["token_endpoint_auth_method"] = method
                        break

            reg_resp = httpx.post(
                registration_endpoint,
                json=reg_payload,
                timeout=10,
            )
            if not reg_resp.is_success:
                raise HTTPException(
                    status_code=502,
                    detail=f"Dynamic client registration failed ({reg_resp.status_code}): {reg_resp.text}",
                )
            reg_data = reg_resp.json()
            client_id = reg_data.get("client_id")
            if not client_id:
                raise HTTPException(status_code=502, detail="Dynamic registration did not return a client_id")
            client_secret = reg_data.get("client_secret")
            server.oauth_client_id = client_id
            if client_secret:
                server.oauth_client_secret = encrypt_api_key(client_secret)
            db.commit()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Dynamic client registration failed: {exc}")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    # Clean up expired states
    expired = [k for k, v in list(_oauth_states.items()) if v["expires_at"] < now]
    for k in expired:
        del _oauth_states[k]

    _oauth_states[state] = {
        "server_id": server_id,
        "code_verifier": verifier,
        "token_endpoint": token_endpoint,
        "expires_at": now + timedelta(minutes=10),
    }

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": body.redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if body.scope:
        params["scope"] = body.scope

    auth_url = auth_endpoint + "?" + urlencode(params)
    return OAuthStartResponse(authorization_url=auth_url, state=state)


@router.post("/{server_id}/oauth/callback")
def complete_oauth(
    server_id: str,
    body: OAuthCallbackRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")

    state_data = _oauth_states.get(body.state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    if state_data["server_id"] != server_id:
        raise HTTPException(status_code=400, detail="State server mismatch")
    if datetime.now(timezone.utc) > state_data["expires_at"]:
        _oauth_states.pop(body.state, None)
        raise HTTPException(status_code=400, detail="OAuth state expired, please try again")

    token_endpoint = state_data["token_endpoint"]
    client_id = server.oauth_client_id
    client_secret = decrypt_api_key(server.oauth_client_secret) if server.oauth_client_secret else None
    try:
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": body.code,
            "redirect_uri": body.redirect_uri,
            "code_verifier": state_data["code_verifier"],
        }
        if client_secret:
            # Send via both POST body (client_secret_post) and Basic auth header (client_secret_basic)
            # to maximise compatibility — different servers check different places
            data["client_id"] = client_id
            data["client_secret"] = client_secret
            auth = (client_id, client_secret)
        else:
            data["client_id"] = client_id
            auth = None

        resp = httpx.post(token_endpoint, data=data, auth=auth, timeout=30)
        resp.raise_for_status()
        tokens = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc.response.text}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc}")
    finally:
        _oauth_states.pop(body.state, None)

    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="No access_token in OAuth response")

    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    server.oauth_access_token = encrypt_api_key(access_token)
    server.oauth_refresh_token = encrypt_api_key(refresh_token) if refresh_token else None
    if expires_in:
        server.oauth_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    db.commit()

    return {"ok": True}


@router.delete("/{server_id}/oauth", status_code=204)
def revoke_oauth(
    server_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")
    server.oauth_access_token = None
    server.oauth_refresh_token = None
    server.oauth_token_expiry = None
    db.commit()


@router.get("/{server_id}/tools", response_model=list[McpToolSchema])
def list_mcp_tools(
    server_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[McpToolSchema]:
    server = db.get(McpServerORM, server_id)
    if not server or server.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="MCP server not found")

    headers = _get_auth_headers(server, db)

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
