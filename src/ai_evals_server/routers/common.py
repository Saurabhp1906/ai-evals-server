from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser


def get_org_resource(db: Session, orm_class, resource_id: str, current_user: CurrentUser, detail: str | None = None):
    """Fetch a resource by id and verify it belongs to the current user's org."""
    resource = db.get(orm_class, resource_id)
    name = orm_class.__name__.replace("ORM", "")
    if not resource or resource.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail=detail or f"{name} not found")
    return resource


def update_resource(db: Session, resource, body) -> None:
    """Apply non-unset fields from a Pydantic body onto an ORM instance and commit."""
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(resource, field, value)
    db.commit()
    db.refresh(resource)
