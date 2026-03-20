from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..email import send_invite_email
from ..models.orm import InviteORM, MembershipORM, OrganizationORM

router = APIRouter(prefix="/invites", tags=["invites"])

_INVITE_TTL_DAYS = 7


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "member"


class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    token: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class AcceptRequest(BaseModel):
    token: str


@router.post("", response_model=InviteResponse, status_code=201)
def create_invite(
    body: InviteCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> InviteResponse:
    if current_user.org_plan == "free":
        raise HTTPException(status_code=403, detail="Inviting teammates requires a Plus or Pro plan.")
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")

    # Invalidate any prior pending invite for the same email in this org
    existing = (
        db.query(InviteORM)
        .filter(
            InviteORM.org_id == current_user.org_id,
            InviteORM.email == body.email,
            InviteORM.accepted_at.is_(None),
        )
        .first()
    )
    if existing:
        db.delete(existing)

    invite = InviteORM(
        org_id=current_user.org_id,
        email=body.email,
        role=body.role,
        invited_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    org = db.get(OrganizationORM, current_user.org_id)
    send_invite_email(invite.email, org.name if org else "your team", invite.token)

    return _to_response(invite)


@router.get("", response_model=list[InviteResponse])
def list_invites(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> list[InviteResponse]:
    invites = (
        db.query(InviteORM)
        .filter(InviteORM.org_id == current_user.org_id, InviteORM.accepted_at.is_(None))
        .all()
    )
    return [_to_response(i) for i in invites]


@router.delete("/{invite_id}", status_code=204)
def revoke_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> None:
    invite = db.get(InviteORM, invite_id)
    if not invite or invite.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Invite not found")
    db.delete(invite)
    db.commit()


@router.get("/preview/{token}")
def preview_invite(token: str, db: Session = Depends(get_db)) -> dict:
    """Public endpoint — returns org name so the accept page can show context before login."""
    invite = db.query(InviteORM).filter(InviteORM.token == token).first()
    if not invite or invite.accepted_at:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite has expired")
    org = db.get(OrganizationORM, invite.org_id)
    return {"org_name": org.name if org else "Unknown", "email": invite.email, "role": invite.role}


@router.post("/accept")
def accept_invite(
    body: AcceptRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    invite = db.query(InviteORM).filter(InviteORM.token == body.token).first()
    if not invite or invite.accepted_at:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite has expired")

    # Check not already a member of this org
    already = (
        db.query(MembershipORM)
        .filter(MembershipORM.org_id == invite.org_id, MembershipORM.user_id == current_user.id)
        .first()
    )
    if already:
        raise HTTPException(status_code=409, detail="You are already a member of this organization")

    # Remove user from their current org (personal workspace) if it has only them
    old_membership = (
        db.query(MembershipORM).filter(MembershipORM.user_id == current_user.id).first()
    )
    if old_membership:
        other_members = (
            db.query(MembershipORM)
            .filter(
                MembershipORM.org_id == old_membership.org_id,
                MembershipORM.user_id != current_user.id,
            )
            .count()
        )
        db.delete(old_membership)
        if other_members == 0:
            # Only member — delete the personal org too
            old_org = db.get(OrganizationORM, old_membership.org_id)
            if old_org:
                db.delete(old_org)
        db.flush()  # ensure DELETE is sent before INSERT below

    # Join the invited org
    new_membership = MembershipORM(
        org_id=invite.org_id,
        user_id=current_user.id,
        role=invite.role,
    )
    db.add(new_membership)

    # Mark invite as accepted
    invite.accepted_at = datetime.now(timezone.utc)
    db.commit()

    org = db.get(OrganizationORM, invite.org_id)
    return {"org_id": invite.org_id, "org_name": org.name if org else "", "role": invite.role}


def _to_response(invite: InviteORM) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        created_at=invite.created_at,
    )
