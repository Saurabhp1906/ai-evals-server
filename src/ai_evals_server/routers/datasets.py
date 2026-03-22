from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import _get_limit, _NEXT_PLAN, check_resource_limit
from ..database import get_db
from ..models.orm import DatasetORM, DatasetRowORM
from ..models.schemas import Dataset, DatasetCreate, DatasetRowCreate, DatasetRowUpdate, DatasetUpdate

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=Dataset, status_code=201)
def create_dataset(
    body: DatasetCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dataset:
    check_resource_limit(
        db, current_user.org_id, current_user.org_plan, "datasets",
        DatasetORM, current_user.org_custom_limits,
    )
    dataset = DatasetORM(**body.model_dump(), org_id=current_user.org_id, created_by_email=current_user.email)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return Dataset.model_validate(dataset)


@router.get("", response_model=list[Dataset])
def list_datasets(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Dataset]:
    rows = db.query(DatasetORM).filter(DatasetORM.org_id == current_user.org_id).all()
    return [Dataset.model_validate(d) for d in rows]


@router.get("/{dataset_id}", response_model=Dataset)
def get_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dataset:
    dataset = db.get(DatasetORM, dataset_id)
    if not dataset or dataset.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return Dataset.model_validate(dataset)


@router.put("/{dataset_id}", response_model=Dataset)
def update_dataset(
    dataset_id: str,
    body: DatasetUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dataset:
    dataset = db.get(DatasetORM, dataset_id)
    if not dataset or dataset.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(dataset, field, value)
    db.commit()
    db.refresh(dataset)
    return Dataset.model_validate(dataset)


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    dataset = db.get(DatasetORM, dataset_id)
    if not dataset or dataset.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    db.delete(dataset)
    db.commit()


# --- Rows ---

@router.post("/{dataset_id}/rows", response_model=Dataset)
def add_rows(
    dataset_id: str,
    rows: list[DatasetRowCreate],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dataset:
    dataset = db.get(DatasetORM, dataset_id)
    if not dataset or dataset.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")

    limit = _get_limit(current_user.org_plan, "resources", "rows_per_dataset", current_user.org_custom_limits)
    if limit is not None:
        current_count = db.query(DatasetRowORM).filter(DatasetRowORM.dataset_id == dataset_id).count()
        if current_count + len(rows) > limit:
            upgrade_to = _NEXT_PLAN.get(current_user.org_plan, "a higher")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "limit_exceeded",
                    "resource": "rows_per_dataset",
                    "current": current_count,
                    "limit": limit,
                    "plan": current_user.org_plan,
                    "message": (
                        f"{current_user.org_plan.capitalize()} plan allows {limit} rows per dataset. "
                        f"Adding {len(rows)} rows would exceed this limit (currently {current_count}/{limit}). "
                        f"Upgrade to {upgrade_to} for more."
                    ),
                    "upgrade_url": "/settings/billing",
                },
            )

    for row_data in rows:
        db.add(DatasetRowORM(dataset_id=dataset_id, **row_data.model_dump()))
    db.commit()
    db.refresh(dataset)
    return Dataset.model_validate(dataset)


@router.put("/{dataset_id}/rows/{row_id}", response_model=Dataset)
def update_row(
    dataset_id: str,
    row_id: str,
    body: DatasetRowUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dataset:
    dataset = db.get(DatasetORM, dataset_id)
    if not dataset or dataset.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    row = db.get(DatasetRowORM, row_id)
    if not row or row.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Row not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(dataset)
    return Dataset.model_validate(dataset)


@router.delete("/{dataset_id}/rows/{row_id}", response_model=Dataset)
def delete_row(
    dataset_id: str,
    row_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dataset:
    dataset = db.get(DatasetORM, dataset_id)
    if not dataset or dataset.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    row = db.get(DatasetRowORM, row_id)
    if not row or row.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Row not found")
    db.delete(row)
    db.commit()
    db.refresh(dataset)
    return Dataset.model_validate(dataset)
