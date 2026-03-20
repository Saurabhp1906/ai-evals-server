from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import enforce_limit
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
    enforce_limit(db, current_user.org_id, current_user.org_plan, "datasets", DatasetORM)
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
