from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import check_resource_limit
from ..database import get_db
from ..models.orm import PromptORM, PromptVersionORM
from ..models.schemas import Prompt, PromptCreate, PromptUpdate, PromptVersion, PromptVersionCreate, PromptVersionUpdate
from .common import get_org_resource, update_resource

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _to_prompt_response(prompt: PromptORM) -> Prompt:
    latest_version_string = None
    if prompt.versions:
        latest = max(prompt.versions, key=lambda v: v.version_number)
        latest_version_string = latest.prompt_string
    return Prompt(
        id=prompt.id,
        name=prompt.name,
        tools=prompt.tools,
        use_responses_api=prompt.use_responses_api,
        connection_id=prompt.connection_id,
        max_output_tokens=prompt.max_output_tokens,
        model=prompt.model,
        mcp_server_id=prompt.mcp_server_id,
        mcp_tool_filter=prompt.mcp_tool_filter,
        response_format=prompt.response_format,
        created_at=prompt.created_at,
        created_by_email=prompt.created_by_email,
        latest_version_string=latest_version_string,
    )


@router.post("", response_model=Prompt, status_code=201)
def create_prompt(
    body: PromptCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Prompt:
    check_resource_limit(
        db, current_user.org_id, current_user.org_plan, "prompts",
        PromptORM, current_user.org_custom_limits,
    )
    prompt_data = body.model_dump(exclude={'prompt_string'})
    prompt = PromptORM(**prompt_data, org_id=current_user.org_id, created_by_email=current_user.email)
    db.add(prompt)
    db.flush()
    v1 = PromptVersionORM(prompt_id=prompt.id, version_number=1, prompt_string=body.prompt_string)
    db.add(v1)
    db.commit()
    db.refresh(prompt)
    return _to_prompt_response(prompt)


@router.get("", response_model=list[Prompt])
def list_prompts(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Prompt]:
    rows = db.query(PromptORM).filter(PromptORM.org_id == current_user.org_id).all()
    return [_to_prompt_response(p) for p in rows]


@router.get("/{prompt_id}", response_model=Prompt)
def get_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Prompt:
    return _to_prompt_response(get_org_resource(db, PromptORM, prompt_id, current_user, "Prompt not found"))


@router.put("/{prompt_id}", response_model=Prompt)
def update_prompt(
    prompt_id: str,
    body: PromptUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Prompt:
    prompt = get_org_resource(db, PromptORM, prompt_id, current_user, "Prompt not found")
    update_resource(db, prompt, body)
    return _to_prompt_response(prompt)


@router.delete("/{prompt_id}", status_code=204)
def delete_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    prompt = get_org_resource(db, PromptORM, prompt_id, current_user, "Prompt not found")
    db.delete(prompt)
    db.commit()


# ---------------------------------------------------------------------------
# Prompt Versions
# ---------------------------------------------------------------------------

def _get_prompt_and_version(prompt_id: str, version_id: str, db: Session, current_user: CurrentUser):
    prompt = get_org_resource(db, PromptORM, prompt_id, current_user, "Prompt not found")
    version = db.get(PromptVersionORM, version_id)
    if not version or version.prompt_id != prompt_id:
        raise HTTPException(status_code=404, detail="Version not found")
    return prompt, version


@router.get("/{prompt_id}/versions", response_model=list[PromptVersion])
def list_versions(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[PromptVersion]:
    get_org_resource(db, PromptORM, prompt_id, current_user, "Prompt not found")
    rows = (
        db.query(PromptVersionORM)
        .filter(PromptVersionORM.prompt_id == prompt_id)
        .order_by(PromptVersionORM.version_number)
        .all()
    )
    return [PromptVersion.model_validate(v) for v in rows]


@router.post("/{prompt_id}/versions", response_model=PromptVersion, status_code=201)
def create_version(
    prompt_id: str,
    body: PromptVersionCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PromptVersion:
    get_org_resource(db, PromptORM, prompt_id, current_user, "Prompt not found")
    check_resource_limit(
        db, current_user.org_id, current_user.org_plan, "prompt_versions",
        PromptVersionORM, current_user.org_custom_limits,
        filter_col="prompt_id", filter_val=prompt_id,
    )
    version = PromptVersionORM(prompt_id=prompt_id, **body.model_dump())
    db.add(version)
    db.commit()
    db.refresh(version)
    return PromptVersion.model_validate(version)


@router.get("/{prompt_id}/versions/{version_id}", response_model=PromptVersion)
def get_version(
    prompt_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PromptVersion:
    _, version = _get_prompt_and_version(prompt_id, version_id, db, current_user)
    return PromptVersion.model_validate(version)


@router.put("/{prompt_id}/versions/{version_id}", response_model=PromptVersion)
def update_version(
    prompt_id: str,
    version_id: str,
    body: PromptVersionUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PromptVersion:
    _, version = _get_prompt_and_version(prompt_id, version_id, db, current_user)
    version.prompt_string = body.prompt_string
    db.commit()
    db.refresh(version)
    return PromptVersion.model_validate(version)


@router.delete("/{prompt_id}/versions/{version_id}", status_code=204)
def delete_version(
    prompt_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    _, version = _get_prompt_and_version(prompt_id, version_id, db, current_user)
    db.delete(version)
    db.commit()
