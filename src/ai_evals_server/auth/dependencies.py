from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.orm import MembershipORM, OrganizationORM
from .utils import decode_supabase_token

_bearer = HTTPBearer()


@dataclass
class CurrentUser:
    id: str
    email: str
    org_id: str
    org_plan: str   # free | plus | pro
    org_role: str   # admin | member


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = credentials.credentials
    try:
        payload = decode_supabase_token(token)
        user_id: str = payload.get("sub", "")
        email: str = payload.get("email", "")
        if not user_id:
            raise JWTError("Missing sub claim")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    # Look up the user's membership
    membership = (
        db.query(MembershipORM)
        .filter(MembershipORM.user_id == user_id)
        .first()
    )

    if not membership:
        # First login — auto-create a personal workspace on the Free plan
        name = email.split("@")[0] if email else "My Workspace"
        org = OrganizationORM(name=f"{name}'s workspace", plan="free")
        db.add(org)
        db.flush()
        membership = MembershipORM(org_id=org.id, user_id=user_id, role="admin")
        db.add(membership)
        db.commit()
        db.refresh(membership)

    org = db.get(OrganizationORM, membership.org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Organization not found")

    return CurrentUser(
        id=user_id,
        email=email,
        org_id=org.id,
        org_plan=org.plan,
        org_role=membership.role,
    )


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that additionally requires the user to be an org admin."""
    if current_user.org_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
