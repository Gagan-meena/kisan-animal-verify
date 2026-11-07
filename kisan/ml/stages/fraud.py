"""Stage 6b: fraud signals (rule 5). Pure function over facts gathered by activities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import imagehash

from kisan.ml.thresholds import DEFAULT, Thresholds
from kisan.ml.types import ReuploadItem, StageResult

NAME = "fraud"


@dataclass
class PhotoFacts:
    image_id: str
    view: str
    phash: str | None
    capture_meta: dict = field(default_factory=dict)


@dataclass
class DuplicateHit:
    animal_id: str
    listing_id: str | None
    seller_id: str | None
    sim: float


def run(
    photos: list[PhotoFacts],
    *,
    seller_id: str,
    seller_kyc: str,
    duplicate_hits: list[DuplicateHit],
    th: Thresholds = DEFAULT,
) -> StageResult:
    flags: list[str] = []
    reupload: list[ReuploadItem] = []

    # 1. Same photo uploaded as two different views
    hashed = [p for p in photos if p.phash]
    seen: set[str] = set()
    for i, a in enumerate(hashed):
        for b in hashed[i + 1 :]:
            if b.image_id in seen:
                continue
            if imagehash.hex_to_hash(a.phash) - imagehash.hex_to_hash(b.phash) <= th.phash_same_photo:
                seen.add(b.image_id)
                reupload.append(
                    ReuploadItem(
                        b.image_id, b.view, f"same photo as the {a.view} photo; take a new {b.view} photo"
                    )
                )

    # 2. Capture provenance: in-app camera only (rule 1)
    for p in photos:
        src = p.capture_meta.get("source")
        if src != "in_app_camera":
            reupload.append(ReuploadItem(p.image_id, p.view, "take this photo with the in-app camera"))
        elif not p.capture_meta.get("sig"):
            flags.append(f"{p.view} photo has no capture signature")

    times = []
    for p in photos:
        ts = p.capture_meta.get("captured_at")
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                # Mixed naive/aware values would raise on comparison: treat naive as UTC.
                times.append(t if t.tzinfo else t.replace(tzinfo=UTC))
            except ValueError:
                flags.append(f"{p.view} photo has an invalid capture time")
    if len(times) >= 2:
        span_h = (max(times) - min(times)).total_seconds() / 3600
        if span_h > th.max_capture_span_hours:
            flags.append(f"photos were taken {span_h:.0f} hours apart")

    # 3. Seller identity
    if seller_kyc != "VERIFIED":
        flags.append("seller KYC is not complete")

    # 4. Same animal in another listing
    for h in duplicate_hits:
        if h.sim >= th.duplicate_sim:
            who = "this seller" if h.seller_id == seller_id else "another seller"
            flags.append(f"same animal may already be listed by {who} (listing {h.listing_id}, {h.sim:.2f})")

    return StageResult(
        name=NAME,
        passed=not flags and not reupload,
        score=None,
        hard_gate=bool(reupload),
        flags=flags,
        reupload=reupload,
        evidence={
            "duplicate_hits": [h.__dict__ for h in duplicate_hits[:5]],
            "seller_kyc": seller_kyc,
        },
    )
