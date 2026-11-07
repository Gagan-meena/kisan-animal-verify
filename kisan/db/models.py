"""ORM models.

Every tenant table carries ``seller_id`` and uses it as the first primary-key column,
because Citus distributes these tables by ``seller_id`` (rule 4). Keeping a seller's
listings, animals, images and verifications on one shard keeps writes single-shard.
The authoritative DDL (partitions, distribution) lives in ``db/migrations``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class Species(enum.StrEnum):
    COW = "cow"
    BUFFALO = "buffalo"
    GOAT = "goat"
    SHEEP = "sheep"
    CAMEL = "camel"
    HORSE = "horse"


class View(enum.StrEnum):
    FRONT = "FRONT"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    REAR = "REAR"
    FACE = "FACE"
    MUZZLE = "MUZZLE"
    TAG = "TAG"
    VIDEO = "VIDEO"  # 5-second walk-around clip (rule 5)


class ListingStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    VERIFYING = "VERIFYING"
    LIVE = "LIVE"
    NEEDS_REUPLOAD = "NEEDS_REUPLOAD"
    BLOCKED = "BLOCKED"
    SOLD = "SOLD"

class ListingSummary(BaseModel):
    listing_id: uuid.UUID
    animal_id: uuid.UUID
    title: str
    species: Species
    price_inr: int
    status: str
    created_at: datetime


class Decision(enum.StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REUPLOAD = "REUPLOAD"
    BLOCKED = "BLOCKED"


class Seller(Base):
    __tablename__ = "sellers"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(2))
    kyc_status: Mapped[str] = mapped_column(String(16), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Listing(Base):
    __tablename__ = "listings"
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(String(120))
    price_inr: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=ListingStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Animal(Base):
    __tablename__ = "animals"
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    species: Mapped[Species] = mapped_column(String(16))
    breed: Mapped[str | None] = mapped_column(String(48))
    sex: Mapped[str] = mapped_column(String(8))
    age_months: Mapped[int | None] = mapped_column(Integer)
    tag_id: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnimalImage(Base):
    __tablename__ = "animal_images"
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    animal_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    view: Mapped[str] = mapped_column(String(8))
    storage_key: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(32))
    # Signed by the app at capture time (rule 1 / rule 5)
    capture_meta: Mapped[dict] = mapped_column(default=dict)
    uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Verification(Base):
    __tablename__ = "verifications"
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    animal_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    workflow_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default=Decision.PENDING)
    score: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(default=dict)
    flags: Mapped[list] = mapped_column(default=list)
    reasons: Mapped[list] = mapped_column(default=list)
    model_versions: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Review(Base):
    __tablename__ = "reviews"
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    animal_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    reviewer_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    """Transactional outbox (rule 2). Rows are written in the same transaction as the
    business change and published to Kafka by ``kisan.events.relay``."""

    __tablename__ = "outbox"
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class StateRule(Base):
    """Reference table (replicated to every Citus node). One row per state × species × action.
    Content must be legally reviewed before a state is enabled (rule 5, rule 6)."""

    __tablename__ = "state_rules"
    state: Mapped[str] = mapped_column(String(2), primary_key=True)
    species: Mapped[str] = mapped_column(String(16), primary_key=True)
    action: Mapped[str] = mapped_column(String(16), primary_key=True)  # sell | transport
    allowed: Mapped[bool] = mapped_column(Boolean)
    docs_required: Mapped[list] = mapped_column(default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    legally_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
