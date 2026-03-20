import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .schemas import ConnectionType


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Organizations + multi-tenancy
# ---------------------------------------------------------------------------

class OrganizationORM(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str] = mapped_column(String, nullable=False, default="free")  # free | plus | pro
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    members: Mapped[list["MembershipORM"]] = relationship(
        "MembershipORM", back_populates="organization", cascade="all, delete-orphan"
    )
    invites: Mapped[list["InviteORM"]] = relationship(
        "InviteORM", back_populates="organization", cascade="all, delete-orphan"
    )


class MembershipORM(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)  # Supabase auth UUID
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")  # admin | member
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organization: Mapped["OrganizationORM"] = relationship("OrganizationORM", back_populates="members")


class InviteORM(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True, default=_uuid)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    invited_by: Mapped[str] = mapped_column(String, nullable=False)  # user_id of inviter
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organization: Mapped["OrganizationORM"] = relationship("OrganizationORM", back_populates="invites")


# ---------------------------------------------------------------------------
# Resources — scoped to org_id
# ---------------------------------------------------------------------------

class ConnectionORM(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(
        Enum(ConnectionType, name="connection_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    azure_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    azure_deployment: Mapped[str | None] = mapped_column(Text, nullable=True)
    azure_api_version: Mapped[str] = mapped_column(String, default="2024-02-01")
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PromptORM(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    use_responses_api: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connection_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    created_by_email: Mapped[str | None] = mapped_column(String, nullable=True)

    connection: Mapped["ConnectionORM | None"] = relationship("ConnectionORM")
    versions: Mapped[list["PromptVersionORM"]] = relationship(
        "PromptVersionORM",
        back_populates="prompt",
        cascade="all, delete-orphan",
        order_by="PromptVersionORM.version_number",
    )


class DatasetORM(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by_email: Mapped[str | None] = mapped_column(String, nullable=True)

    rows: Mapped[list["DatasetRowORM"]] = relationship(
        "DatasetRowORM",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetRowORM.created_at",
    )


class DatasetRowORM(Base):
    __tablename__ = "dataset_rows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    dataset: Mapped["DatasetORM"] = relationship("DatasetORM", back_populates="rows")


class ScorerORM(Base):
    __tablename__ = "scorers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_string: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, default="claude-sonnet-4-6")
    connection_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    pass_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by_email: Mapped[str | None] = mapped_column(String, nullable=True)

    connection: Mapped["ConnectionORM | None"] = relationship("ConnectionORM")


class PlaygroundORM(Base):
    __tablename__ = "playgrounds"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    scorer_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("scorers.id", ondelete="SET NULL"), nullable=True
    )
    prompt_connection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    scorer_connection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by_email: Mapped[str | None] = mapped_column(String, nullable=True)

    runs: Mapped[list["PlaygroundRunORM"]] = relationship(
        "PlaygroundRunORM",
        back_populates="playground",
        cascade="all, delete-orphan",
        order_by="PlaygroundRunORM.created_at.desc()",
    )


class PlaygroundRunORM(Base):
    __tablename__ = "playground_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    playground_id: Mapped[str] = mapped_column(
        String, ForeignKey("playgrounds.id", ondelete="CASCADE"), nullable=False
    )
    prompt_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dataset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    scorer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    playground: Mapped["PlaygroundORM"] = relationship("PlaygroundORM", back_populates="runs")
    rows: Mapped[list["PlaygroundRunRowORM"]] = relationship(
        "PlaygroundRunRowORM",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class PlaygroundRunRowORM(Base):
    __tablename__ = "playground_run_rows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("playground_runs.id", ondelete="CASCADE"), nullable=False
    )
    row_id: Mapped[str] = mapped_column(String, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run: Mapped["PlaygroundRunORM"] = relationship("PlaygroundRunORM", back_populates="rows")


class PromptVersionORM(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    prompt_id: Mapped[str] = mapped_column(
        String, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_string: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    prompt: Mapped["PromptORM"] = relationship("PromptORM", back_populates="versions")
