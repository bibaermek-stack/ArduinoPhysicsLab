"""Account, public IDs, relationship requests — social identity layer."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from server.app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountRecord(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    public_id: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    teacher_sync_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    student_sync_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    photo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RelationshipRequestRecord(Base):
    __tablename__ = "relationship_requests"
    __table_args__ = (
        UniqueConstraint(
            "kind", "from_account_id", "to_account_id", "status",
            name="uq_pending_request",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # teacher_student | friend
    from_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    to_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RelationshipLinkRecord(Base):
    __tablename__ = "relationship_links"
    __table_args__ = (
        UniqueConstraint("kind", "account_a_id", "account_b_id", name="uq_relationship_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    account_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    account_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
