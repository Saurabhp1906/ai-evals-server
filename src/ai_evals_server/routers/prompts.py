from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import enforce_limit
from ..database import get_db
from ..models.orm import PromptORM
from ..models.schemas import Prompt, PromptCreate, PromptUpdate

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("", response_model=Prompt, status_code=201)
def create_prompt(
    body: PromptCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Prompt:
    enforce_limit(db, current_user.org_id, current_user.org_plan, "prompts", PromptORM)
    prompt = PromptORM(**body.model_dump(), org_id=current_user.org_id)
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return Prompt.model_validate(prompt)


@router.get("", response_model=list[Prompt])
def list_prompts(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Prompt]:
    rows = db.query(PromptORM).filter(PromptORM.org_id == current_user.org_id).all()
    return [Prompt.model_validate(p) for p in rows]


@router.get("/{prompt_id}", response_model=Prompt)
def get_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Prompt:
    prompt = db.get(PromptORM, prompt_id)
    if not prompt or prompt.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return Prompt.model_validate(prompt)


@router.put("/{prompt_id}", response_model=Prompt)
def update_prompt(
    prompt_id: str,
    body: PromptUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Prompt:
    prompt = db.get(PromptORM, prompt_id)
    if not prompt or prompt.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prompt, field, value)
    db.commit()
    db.refresh(prompt)
    return Prompt.model_validate(prompt)


@router.delete("/{prompt_id}", status_code=204)
def delete_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    prompt = db.get(PromptORM, prompt_id)
    if not prompt or prompt.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    db.delete(prompt)
    db.commit()
