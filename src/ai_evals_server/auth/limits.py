from fastapi import HTTPException
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Plan limits — None means unlimited
# ---------------------------------------------------------------------------

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free": {"prompts": 1, "scorers": 1, "playgrounds": 1, "datasets": 2},
    "plus": {"prompts": 5,  "scorers": 5,  "playgrounds": 5,  "datasets": 20},
    "pro":  {"prompts": 20, "scorers": 20, "playgrounds": 20, "datasets": 50},
}

PLAN_LABELS = {
    "free": "Free",
    "plus": "Plus",
    "pro": "Pro",
}


def enforce_limit(db: Session, org_id: str, plan: str, resource: str, model) -> None:
    """Raise 403 if the org has reached its plan limit for the given resource."""
    limit = PLAN_LIMITS.get(plan, {}).get(resource)
    if limit is None:
        return
    count = db.query(model).filter(model.org_id == org_id).count()
    if count >= limit:
        label = PLAN_LABELS.get(plan, plan)
        upgrade_to = {"free": "Plus", "plus": "Pro"}.get(plan, "a higher")
        raise HTTPException(
            status_code=403,
            detail=(
                f"{label} plan limit reached: you can have at most {limit} {resource}. "
                f"Upgrade to {upgrade_to} to create more."
            ),
        )


def get_usage(db: Session, org_id: str, plan: str, models: dict) -> dict:
    """Return current usage counts and limits for all tracked resources."""
    result = {}
    tracked = PLAN_LIMITS.get(plan, {})
    for resource, limit in tracked.items():
        model = models.get(resource)
        count = db.query(model).filter(model.org_id == org_id).count() if model else 0
        result[resource] = {"count": count, "limit": limit}
    return result
