from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..database import get_db
from ..models.orm import ReviewORM, ReviewRowORM
from ..models.schemas import ReviewCreate, ReviewRowUpdate, ReviewSchema

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewSchema, status_code=201)
def create_review(
    body: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReviewSchema:
    review = ReviewORM(
        org_id=current_user.org_id,
        name=body.name,
        playground_id=body.playground_id,
        playground_name=body.playground_name,
        run_label=body.run_label,
    )
    db.add(review)
    db.flush()

    for row in body.rows:
        db.add(ReviewRowORM(
            review_id=review.id,
            input=row.input,
            output=row.output,
            score=row.score,
            row_comment=row.row_comment,
            prompt_string=row.prompt_string,
        ))

    db.commit()
    db.refresh(review)
    return ReviewSchema.model_validate(review)


@router.get("", response_model=list[ReviewSchema])
def list_reviews(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ReviewSchema]:
    reviews = db.query(ReviewORM).filter(ReviewORM.org_id == current_user.org_id).order_by(ReviewORM.created_at.desc()).all()
    return [ReviewSchema.model_validate(r) for r in reviews]


@router.get("/{review_id}", response_model=ReviewSchema)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReviewSchema:
    review = db.get(ReviewORM, review_id)
    if not review or review.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewSchema.model_validate(review)


@router.patch("/{review_id}/rows/{row_id}", response_model=ReviewSchema)
def update_review_row(
    review_id: str,
    row_id: str,
    body: ReviewRowUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReviewSchema:
    review = db.get(ReviewORM, review_id)
    if not review or review.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Review not found")

    row = db.get(ReviewRowORM, row_id)
    if not row or row.review_id != review_id:
        raise HTTPException(status_code=404, detail="Row not found")

    if body.annotation is not None:
        row.annotation = body.annotation
    if body.rating is not None:
        row.rating = body.rating
    if body.expected_behavior is not None:
        row.expected_behavior = body.expected_behavior

    db.commit()
    db.refresh(review)
    return ReviewSchema.model_validate(review)


@router.delete("/{review_id}", status_code=204)
def delete_review(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    review = db.get(ReviewORM, review_id)
    if not review or review.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(review)
    db.commit()
