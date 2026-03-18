from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user, require_admin
from ..auth.limits import PLAN_LIMITS, get_usage
from ..database import get_db
from ..models.orm import (
    ConnectionORM, MembershipORM, OrganizationORM,
    PlaygroundORM, PromptORM, ScorerORM,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])

_USAGE_MODELS = {
    "prompts": PromptORM,
    "scorers": ScorerORM,
    "playgrounds": PlaygroundORM,
}


class OrgResponse(BaseModel):
    id: str
    name: str
    plan: str
    created_at: datetime


class OrgUpdate(BaseModel):
    name: str


class MemberResponse(BaseModel):
    user_id: str
    role: str
    created_at: datetime


class UsageResponse(BaseModel):
    prompts: dict
    scorers: dict
    playgrounds: dict


@router.get("/me", response_model=OrgResponse)
def get_my_org(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> OrgResponse:
    org = db.get(OrganizationORM, current_user.org_id)
    return OrgResponse(id=org.id, name=org.name, plan=org.plan, created_at=org.created_at)


@router.put("/me", response_model=OrgResponse)
def update_my_org(
    body: OrgUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> OrgResponse:
    org = db.get(OrganizationORM, current_user.org_id)
    org.name = body.name
    db.commit()
    db.refresh(org)
    return OrgResponse(id=org.id, name=org.name, plan=org.plan, created_at=org.created_at)


@router.get("/me/members", response_model=list[MemberResponse])
def list_members(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[MemberResponse]:
    members = db.query(MembershipORM).filter(MembershipORM.org_id == current_user.org_id).all()
    return [MemberResponse(user_id=m.user_id, role=m.role, created_at=m.created_at) for m in members]


@router.delete("/me/members/{user_id}", status_code=204)
def remove_member(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")
    membership = (
        db.query(MembershipORM)
        .filter(MembershipORM.org_id == current_user.org_id, MembershipORM.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(membership)
    db.commit()


@router.get("/me/usage", response_model=UsageResponse)
def get_usage_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UsageResponse:
    usage = get_usage(db, current_user.org_id, current_user.org_plan, _USAGE_MODELS)
    return UsageResponse(**usage)
