from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# ============================================================================
# PLAN CONFIG — single source of truth
# Edit this dict to change any limit for any plan. None = unlimited.
# ============================================================================

PLAN_CONFIG: dict[str, dict] = {
    "free": {
        "resources": {
            "connections":        1,
            "prompts":            2,
            "prompt_versions":    3,   # per prompt
            "datasets":           1,
            "rows_per_dataset":   20,  # per dataset
            "scorers":            1,
            "playgrounds":        1,
            "agents":             1,
            "chats_per_agent":    2,   # per agent
            "messages_per_chat":  50,  # per chat
            "mcp_servers":        1,
            "team_members":       1,
        },
        "daily_quotas": {
            "playground_runs":     25,
            "agent_messages":      25,
            "scorer_evaluations":  25,
        },
        "features": {
            "run_history":          True,
            "run_comparison":       True,
            "reviews":              True,
            "responses_api_toggle": True,
            "oauth_mcp_auth":       True,
            "admin_controls":       True,
            "sso_saml":             False,
            "audit_log":            False,
        },
        "retention_days": 7,
    },
    "plus": {
        "resources": {
            "connections":        5,
            "prompts":            10,
            "prompt_versions":    5,
            "datasets":           5,
            "rows_per_dataset":   100,
            "scorers":            5,
            "playgrounds":        5,
            "agents":             5,
            "chats_per_agent":    5,
            "messages_per_chat":  100,
            "mcp_servers":        3,
            "team_members":       3,
        },
        "daily_quotas": {
            "playground_runs":     300,
            "agent_messages":      300,
            "scorer_evaluations":  300,
        },
        "features": {
            "run_history":          True,
            "run_comparison":       True,
            "reviews":              True,
            "responses_api_toggle": True,
            "oauth_mcp_auth":       True,
            "admin_controls":       False,
            "sso_saml":             False,
            "audit_log":            False,
        },
        "retention_days": 30,
    },
    "pro": {
        "resources": {
            "connections":        15,
            "prompts":            50,
            "prompt_versions":    10,
            "datasets":           20,
            "rows_per_dataset":   500,
            "scorers":            20,
            "playgrounds":        20,
            "agents":             20,
            "chats_per_agent":    5,
            "messages_per_chat":  100,
            "mcp_servers":        10,
            "team_members":       10,
        },
        "daily_quotas": {
            "playground_runs":     1000,
            "agent_messages":      1000,
            "scorer_evaluations":  1000,
        },
        "features": {
            "run_history":          True,
            "run_comparison":       True,
            "reviews":              True,
            "responses_api_toggle": True,
            "oauth_mcp_auth":       True,
            "admin_controls":       True,
            "sso_saml":             False,
            "audit_log":            False,
        },
        "retention_days": 90,
    },
    "enterprise": {
        "resources": {
            "connections":        None,
            "prompts":            None,
            "prompt_versions":    25,
            "datasets":           None,
            "rows_per_dataset":   5000,
            "scorers":            None,
            "playgrounds":        None,
            "agents":             None,
            "chats_per_agent":    10,
            "messages_per_chat":  200,
            "mcp_servers":        None,
            "team_members":       None,
        },
        "daily_quotas": {
            "playground_runs":     None,  # set per org via custom_limits
            "agent_messages":      None,
            "scorer_evaluations":  None,
        },
        "features": {
            "run_history":          True,
            "run_comparison":       True,
            "reviews":              True,
            "responses_api_toggle": True,
            "oauth_mcp_auth":       True,
            "admin_controls":       True,
            "sso_saml":             True,
            "audit_log":            True,
        },
        "retention_days": 365,
    },
}

_NEXT_PLAN = {"free": "Plus", "plus": "Pro", "pro": "Enterprise", "enterprise": "a custom"}


def _effective_config(plan: str, custom_limits: dict | None = None) -> dict:
    """Return plan config merged with any org-level overrides (enterprise custom limits)."""
    base = PLAN_CONFIG.get(plan) or PLAN_CONFIG["free"]
    if not custom_limits:
        return base
    merged = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for section, overrides in custom_limits.items():
        if section in merged and isinstance(overrides, dict):
            merged[section] = dict(merged[section])
            merged[section].update(overrides)
    return merged


def _get_limit(plan: str, section: str, key: str, custom_limits: dict | None = None) -> int | None:
    return _effective_config(plan, custom_limits).get(section, {}).get(key)


def _tomorrow_midnight() -> str:
    tomorrow = date.today() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc).isoformat()


# ============================================================================
# Resource limit checks
# ============================================================================

def check_resource_limit(
    db: Session,
    org_id: str,
    plan: str,
    resource: str,
    model,
    custom_limits: dict | None = None,
    filter_col: str | None = None,
    filter_val: str | None = None,
) -> None:
    """Raise 403 if the org has reached the plan limit for a resource.

    For per-parent limits (prompt_versions, rows_per_dataset, chats_per_agent,
    messages_per_chat) pass filter_col/filter_val to scope the count to a
    specific parent (e.g. filter_col="prompt_id", filter_val=prompt_id).
    """
    limit = _get_limit(plan, "resources", resource, custom_limits)
    if limit is None:
        return  # unlimited

    q = db.query(model)
    if filter_col and filter_val:
        q = q.filter(getattr(model, filter_col) == filter_val)
    else:
        q = q.filter(model.org_id == org_id)
    count = q.count()

    if count >= limit:
        upgrade_to = _NEXT_PLAN.get(plan, "a higher")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "limit_exceeded",
                "resource": resource,
                "current": count,
                "limit": limit,
                "plan": plan,
                "message": f"{plan.capitalize()} plan allows {limit} {resource}. Upgrade to {upgrade_to} for more.",
                "upgrade_url": "/settings/billing",
            },
        )


# ============================================================================
# Daily quota checks
# ============================================================================

def check_daily_quota(
    db: Session,
    org_id: str,
    plan: str,
    quota: str,
    increment: int = 1,
    custom_limits: dict | None = None,
) -> None:
    """Check and atomically increment a daily quota. Raises 403 if it would exceed the limit.

    For playground runs, pass increment=len(dataset.rows) to check the whole
    batch before starting.
    """
    limit = _get_limit(plan, "daily_quotas", quota, custom_limits)
    if limit is None:
        return  # unlimited

    today = date.today().isoformat()

    # Ensure the row for today exists (safe to race — ON CONFLICT DO NOTHING)
    db.execute(
        text(
            "INSERT INTO daily_usage (org_id, date, playground_runs, agent_messages, scorer_evaluations) "
            "VALUES (:org_id, :date, 0, 0, 0) ON CONFLICT (org_id, date) DO NOTHING"
        ),
        {"org_id": org_id, "date": today},
    )
    db.flush()

    # Lock the row, check, and increment atomically
    row = db.execute(
        text(f"SELECT {quota} FROM daily_usage WHERE org_id = :org_id AND date = :date FOR UPDATE"),
        {"org_id": org_id, "date": today},
    ).fetchone()

    current = row[0] if row else 0

    if current + increment > limit:
        upgrade_to = _NEXT_PLAN.get(plan, "a higher")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "quota_exceeded",
                "quota": quota,
                "used": current,
                "limit": limit,
                "needed": increment,
                "resets_at": _tomorrow_midnight(),
                "plan": plan,
                "message": (
                    f"Daily {quota.replace('_', ' ')} limit reached ({current}/{limit}). "
                    f"Resets at midnight UTC. Upgrade to {upgrade_to} for more."
                    if increment == 1 else
                    f"This run requires {increment} quota but you have {limit - current} remaining today "
                    f"({current}/{limit} used). Resets at midnight UTC. Upgrade to {upgrade_to} for more."
                ),
            },
        )

    db.execute(
        text(f"UPDATE daily_usage SET {quota} = {quota} + :inc WHERE org_id = :org_id AND date = :date"),
        {"org_id": org_id, "date": today, "inc": increment},
    )
    db.commit()


# ============================================================================
# Feature flag checks
# ============================================================================

def check_feature_flag(plan: str, feature: str, custom_limits: dict | None = None) -> bool:
    return bool(_get_limit(plan, "features", feature, custom_limits))


def require_feature(plan: str, feature: str, custom_limits: dict | None = None) -> None:
    """Raise 403 if the feature is not available on the given plan."""
    if not check_feature_flag(plan, feature, custom_limits):
        required_plan = next(
            (p for p, cfg in PLAN_CONFIG.items() if cfg.get("features", {}).get(feature)),
            "plus",
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "feature_unavailable",
                "feature": feature,
                "plan": plan,
                "required_plan": required_plan,
                "message": f"{feature.replace('_', ' ').capitalize()} requires {required_plan.capitalize()} or above.",
                "upgrade_url": "/settings/billing",
            },
        )


# ============================================================================
# Full usage snapshot (for GET /organizations/me/usage)
# ============================================================================

# Maps resource name → ORM model attribute name (org_id scoped, top-level only)
_ORG_LEVEL_RESOURCES = [
    "connections", "prompts", "datasets", "scorers",
    "playgrounds", "agents", "mcp_servers",
]


def get_full_usage(
    db: Session,
    org_id: str,
    plan: str,
    resource_models: dict,
    custom_limits: dict | None = None,
) -> dict:
    """Return a full usage snapshot for the usage dashboard."""
    config = _effective_config(plan, custom_limits)

    resources = {}
    for resource in _ORG_LEVEL_RESOURCES:
        limit = config["resources"].get(resource)
        model = resource_models.get(resource)
        count = db.query(model).filter(model.org_id == org_id).count() if model else 0
        resources[resource] = {"current": count, "limit": limit}

    # Also count team members
    from ..models.orm import MembershipORM
    member_count = db.query(MembershipORM).filter(MembershipORM.org_id == org_id).count()
    resources["team_members"] = {"current": member_count, "limit": config["resources"].get("team_members")}

    today = date.today().isoformat()
    usage_row = db.execute(
        text(
            "SELECT playground_runs, agent_messages, scorer_evaluations "
            "FROM daily_usage WHERE org_id = :org_id AND date = :date"
        ),
        {"org_id": org_id, "date": today},
    ).fetchone()

    resets_at = _tomorrow_midnight()
    daily_quotas = {
        "playground_runs": {
            "used": usage_row[0] if usage_row else 0,
            "limit": config["daily_quotas"]["playground_runs"],
            "resets_at": resets_at,
        },
        "agent_messages": {
            "used": usage_row[1] if usage_row else 0,
            "limit": config["daily_quotas"]["agent_messages"],
            "resets_at": resets_at,
        },
        "scorer_evaluations": {
            "used": usage_row[2] if usage_row else 0,
            "limit": config["daily_quotas"]["scorer_evaluations"],
            "resets_at": resets_at,
        },
    }

    return {
        "plan": plan,
        "resources": resources,
        "daily_quotas": daily_quotas,
        "features": config["features"],
    }


# ============================================================================
# Legacy shims — keep existing callers working without changes
# ============================================================================

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    p: cfg["resources"] for p, cfg in PLAN_CONFIG.items()
}

PLAN_LABELS = {p: p.capitalize() for p in PLAN_CONFIG}


def enforce_limit(db: Session, org_id: str, plan: str, resource: str, model) -> None:
    """Legacy shim. New code should use check_resource_limit directly."""
    check_resource_limit(db, org_id, plan, resource, model)


def get_usage(db: Session, org_id: str, plan: str, models: dict) -> dict:
    """Legacy shim for the basic usage endpoint."""
    result = {}
    for resource, limit in PLAN_LIMITS.get(plan, {}).items():
        model = models.get(resource)
        count = db.query(model).filter(model.org_id == org_id).count() if model else 0
        result[resource] = {"count": count, "limit": limit}
    return result
