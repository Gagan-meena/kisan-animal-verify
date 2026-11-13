from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from kisan.db.models import Species, View


class AnimalIn(BaseModel):
    species: Species
    breed: str | None = Field(default=None, max_length=48)
    sex: Literal["male", "female"]
    age_months: int | None = Field(default=None, ge=0, le=480)
    tag_id: str | None = Field(default=None, pattern=r"^\d{12}$", description="12-digit national ear tag")


class ListingIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    price_inr: int = Field(gt=0, le=10_000_000)
    animal: AnimalIn


class ListingOut(BaseModel):
    listing_id: uuid.UUID
    animal_id: uuid.UUID
    status: str
    required_views: list[str]


class CaptureMeta(BaseModel):
    """Written by the app's camera screen (rule 1)."""

    source: Literal["in_app_camera", "gallery"]
    captured_at: str
    app_version: str
    device_id: str
    on_device_check: dict[str,Any] = Field(default_factory=dict[str,Any])
    sig: str | None = None


class MediaIn(BaseModel):
    view: View
    content_type: str
    capture_meta: CaptureMeta


class MediaOut(BaseModel):
    image_id: uuid.UUID
    upload_url: str
    upload_headers: dict[str, str]
    expires_in: int


class SubmitOut(BaseModel):
    status: str
    attempt: int


class ReuploadOut(BaseModel):
    image_id: str
    view: str
    reason: str
    code: str = "other"


class SellerVerificationOut(BaseModel):
    """What the seller sees. Internal fraud flags are never shown."""

    status: str
    message: str
    reupload: list[ReuploadOut] = []


class ReviewIn(BaseModel):
    decision: Literal["VERIFIED", "REUPLOAD", "BLOCKED"]
    reason: str = ""
    # Labels feed Re-ID fine-tuning and threshold calibration
    labels: dict[str,Any] = Field(
        default_factory=dict[str,Any],
        examples=[{"same_animal": True, "species": "cow"}]
    )


class ReviewQueueItem(BaseModel):
    seller_id: uuid.UUID
    animal_id: uuid.UUID
    verification_id: uuid.UUID
    score: float | None
    flags: list[str]
    waiting_since: str
