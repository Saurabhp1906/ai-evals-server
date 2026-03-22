from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import check_resource_limit, require_feature
from ..database import get_db
from ..models.orm import PlaygroundORM, PlaygroundRunORM, PlaygroundRunRowORM
from ..models.schemas import (
    PlaygroundCreate,
    PlaygroundRunSchema,
    PlaygroundSchema,
    PlaygroundUpdate,
    SaveRunRequest,
)

router = APIRouter(prefix="/playgrounds", tags=["playgrounds"])


@router.post("", response_model=PlaygroundSchema, status_code=201)
def create_playground(
    body: PlaygroundCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlaygroundSchema:
    check_resource_limit(
        db, current_user.org_id, current_user.org_plan, "playgrounds",
        PlaygroundORM, current_user.org_custom_limits,
    )
    pg = PlaygroundORM(**body.model_dump(), org_id=current_user.org_id, created_by_email=current_user.email)
    db.add(pg)
    db.commit()
    db.refresh(pg)
    return PlaygroundSchema.model_validate(pg)


@router.get("", response_model=list[PlaygroundSchema])
def list_playgrounds(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[PlaygroundSchema]:
    rows = db.query(PlaygroundORM).filter(PlaygroundORM.org_id == current_user.org_id).all()
    return [PlaygroundSchema.model_validate(pg) for pg in rows]


@router.get("/{playground_id}", response_model=PlaygroundSchema)
def get_playground(
    playground_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlaygroundSchema:
    pg = db.get(PlaygroundORM, playground_id)
    if not pg or pg.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Playground not found")
    return PlaygroundSchema.model_validate(pg)


@router.put("/{playground_id}", response_model=PlaygroundSchema)
def update_playground(
    playground_id: str,
    body: PlaygroundUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlaygroundSchema:
    pg = db.get(PlaygroundORM, playground_id)
    if not pg or pg.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Playground not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(pg, field, value)
    db.commit()
    db.refresh(pg)
    return PlaygroundSchema.model_validate(pg)


@router.delete("/{playground_id}", status_code=204)
def delete_playground(
    playground_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    pg = db.get(PlaygroundORM, playground_id)
    if not pg or pg.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Playground not found")
    db.delete(pg)
    db.commit()


@router.post("/{playground_id}/runs", response_model=PlaygroundRunSchema, status_code=201)
def save_run(
    playground_id: str,
    body: SaveRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlaygroundRunSchema:
    require_feature(current_user.org_plan, "run_history", current_user.org_custom_limits)
    pg = db.get(PlaygroundORM, playground_id)
    if not pg or pg.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Playground not found")

    run = PlaygroundRunORM(
        playground_id=playground_id,
        prompt_version_id=body.prompt_version_id,
        prompt_version_number=body.prompt_version_number,
        prompt_id=body.prompt_id,
        dataset_id=body.dataset_id,
        scorer_id=body.scorer_id,
    )
    db.add(run)
    db.flush()

    for row in body.rows:
        db.add(PlaygroundRunRowORM(
            run_id=run.id,
            row_id=row.row_id,
            input=row.input,
            comment=row.comment,
            output=row.output,
            score=row.score,
            error=row.error,
            elapsed_ms=row.elapsed_ms,
            tool_calls=row.tool_calls or None,
        ))

    db.commit()
    db.refresh(run)
    return PlaygroundRunSchema.model_validate(run)


@router.delete("/{playground_id}/runs/{run_id}", status_code=204)
def delete_run(
    playground_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    pg = db.get(PlaygroundORM, playground_id)
    if not pg or pg.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Playground not found")
    run = db.get(PlaygroundRunORM, run_id)
    if not run or run.playground_id != playground_id:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(run)
    db.commit()
