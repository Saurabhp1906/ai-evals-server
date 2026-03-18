from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import enforce_limit
from ..database import get_db
from ..models.orm import ScorerORM
from ..models.schemas import Scorer, ScorerCreate, ScorerUpdate

router = APIRouter(prefix="/scorers", tags=["scorers"])


@router.post("", response_model=Scorer, status_code=201)
def create_scorer(
    body: ScorerCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Scorer:
    enforce_limit(db, current_user.org_id, current_user.org_plan, "scorers", ScorerORM)
    scorer = ScorerORM(**body.model_dump(), org_id=current_user.org_id)
    db.add(scorer)
    db.commit()
    db.refresh(scorer)
    return Scorer.model_validate(scorer)


@router.get("", response_model=list[Scorer])
def list_scorers(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Scorer]:
    rows = db.query(ScorerORM).filter(ScorerORM.org_id == current_user.org_id).all()
    return [Scorer.model_validate(s) for s in rows]


@router.get("/{scorer_id}", response_model=Scorer)
def get_scorer(
    scorer_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Scorer:
    scorer = db.get(ScorerORM, scorer_id)
    if not scorer or scorer.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Scorer not found")
    return Scorer.model_validate(scorer)


@router.put("/{scorer_id}", response_model=Scorer)
def update_scorer(
    scorer_id: str,
    body: ScorerUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Scorer:
    scorer = db.get(ScorerORM, scorer_id)
    if not scorer or scorer.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Scorer not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(scorer, field, value)
    db.commit()
    db.refresh(scorer)
    return Scorer.model_validate(scorer)


@router.delete("/{scorer_id}", status_code=204)
def delete_scorer(
    scorer_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    scorer = db.get(ScorerORM, scorer_id)
    if not scorer or scorer.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Scorer not found")
    db.delete(scorer)
    db.commit()
