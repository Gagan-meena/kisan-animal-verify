"""Temporal activities. Each is retryable and idempotent."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from kisan import events
from kisan.config import Settings
from kisan.db.models import (
    Animal,
    AnimalImage,
    Decision,
    Listing,
    ListingStatus,
    Seller,
    StateRule,
    Verification,
    View,
    utcnow,
)
from kisan.ml import media, scoring
from kisan.ml.analyze import analyze
from kisan.ml.backends import InferenceBackend
from kisan.ml.stages import fraud, rules
from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import MediaItem, StageResult
from kisan.rules.engine import StateRuleRow
from kisan.services.verification.contracts import (
    AnalyzeResult,
    FraudInput,
    IndexInput,
    RecordInput,
    ScoreInput,
    VerifyRequest,
)
from kisan.storage import Storage
from kisan.vector import IdentityIndex

LISTING_STATUS = {
    Decision.VERIFIED: ListingStatus.LIVE,
    Decision.NEEDS_REVIEW: ListingStatus.VERIFYING,
    Decision.REUPLOAD: ListingStatus.NEEDS_REUPLOAD,
    Decision.BLOCKED: ListingStatus.BLOCKED,
}


@dataclass
class Deps:
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: Storage
    backend: InferenceBackend
    index: IdentityIndex
    settings: Settings


async def latest_media(
    session: AsyncSession, seller_id: uuid.UUID, animal_id: uuid.UUID
) -> dict[str, AnimalImage]:
    """Latest uploaded file per view (retakes replace earlier shots)."""
    rows = (
        await session.scalars(
            select(AnimalImage)
            .where(
                AnimalImage.seller_id == seller_id,
                AnimalImage.animal_id == animal_id,
                AnimalImage.uploaded.is_(True),
            )
            .order_by(AnimalImage.created_at)
        )
    ).all()
    return {r.view: r for r in rows}


class VerifyActivities:
    def __init__(self, deps: Deps):
        self.d = deps

    @activity.defn
    async def start_verification(self, req: VerifyRequest) -> str:
        wf_id = activity.info().workflow_id
        sid, aid = uuid.UUID(req.seller_id), uuid.UUID(req.animal_id)
        async with self.d.sessionmaker() as s:
            existing = await s.scalar(
                select(Verification).where(
                    Verification.seller_id == sid,
                    Verification.animal_id == aid,
                    Verification.workflow_id == wf_id,
                )
            )
            if existing:
                return str(existing.id)
            v = Verification(seller_id=sid, animal_id=aid, workflow_id=wf_id, status=Decision.PENDING)
            s.add(v)
            await s.commit()
            return str(v.id)

    @activity.defn
    async def analyze_media(self, req: VerifyRequest) -> AnalyzeResult:
        sid, aid = uuid.UUID(req.seller_id), uuid.UUID(req.animal_id)
        async with self.d.sessionmaker() as s:
            animal = await s.get(Animal, (sid, aid))
            if animal is None:
                raise ApplicationError("animal not found", non_retryable=True)
            files = await latest_media(s, sid, aid)

        photos: list[MediaItem] = []
        frames: list[MediaItem] = []
        for view, img in files.items():
            activity.heartbeat(f"download {view}")
            data = await asyncio.to_thread(self.d.storage.get, img.storage_key)
            try:
                if view == View.VIDEO:
                    raw = await asyncio.to_thread(media.sample_video_frames, data, 6)
                    frames += [MediaItem(f"{img.id}#f{i}", "VIDEO", f) for i, f in enumerate(raw)]
                else:
                    photos.append(
                        MediaItem(str(img.id), view, await asyncio.to_thread(media.decode_image, data))
                    )
            except ValueError:
                # Corrupt file: ask for a retake instead of failing the workflow.
                photos.append(MediaItem(str(img.id), view, _blank()))

        ctx = AnalyzeContext(
            animal_id=req.animal_id,
            species=animal.species,
            photos=photos,
            video_frames=frames,
            backend=self.d.backend,
        )
        activity.heartbeat("inference")
        out = await asyncio.to_thread(analyze, ctx)
        return AnalyzeResult(
            results=[r.to_dict() for r in out.results],
            centroid=out.centroid,
            phashes=out.phashes,
            stopped_at=out.stopped_at,
        )

    @activity.defn
    async def fraud_and_rules(self, inp: FraudInput) -> list[dict[str,Any]]:
        req = inp.req
        sid, aid = uuid.UUID(req.seller_id), uuid.UUID(req.animal_id)
        async with self.d.sessionmaker() as s:
            seller = await s.get(Seller, sid)
            if seller is None:
                raise ValueError(f"Seller not found: {sid}")
            animal = await s.get(Animal, (sid, aid))
            if animal is None:
                raise ValueError(f"Animal not found: {aid}")
            listing = await s.get(Listing, (sid, animal.listing_id))
            if listing is None:
                raise ValueError(f"Listing not found: {animal.listing_id}")
            files = await latest_media(s, sid, aid)
            rule = await s.get(StateRule, (listing.state, animal.species, "sell"))

        hits = []
        if inp.centroid:
            hits = await asyncio.to_thread(
                self.d.index.search, inp.centroid, species=animal.species, exclude_animal_id=req.animal_id
            )
        facts = [
            fraud.PhotoFacts(str(f.id), f.view, inp.phashes.get(str(f.id)), f.capture_meta)
            for f in files.values()
        ]
        fr = fraud.run(facts, seller_id=req.seller_id, seller_kyc=seller.kyc_status, duplicate_hits=hits)

        docs:set[str] = set()
        if animal.tag_id and View.TAG in files:
            docs.add("ear_tag")
        rule_row = (
            None
            if rule is None
            else StateRuleRow(
                rule.state,
                rule.species,
                rule.action,
                rule.allowed,
                list(rule.docs_required),
                rule.note,
                rule.legally_reviewed,
            )
        )
        rr = rules.run(rule_row, state=listing.state, species=animal.species, docs_present=docs)
        return [fr.to_dict(), rr.to_dict()]

    @activity.defn
    async def score(self, inp: ScoreInput) -> dict[str,Any]:
        results = [StageResult.from_dict(r) for r in inp.results]
        return scoring.decide(
            results,
            human_confirms_all=self.d.settings.pilot_human_confirms_all
        ).to_dict()

    @activity.defn
    async def record_decision(self, inp: RecordInput) -> None:
        req = inp.req
        sid, aid = uuid.UUID(req.seller_id), uuid.UUID(req.animal_id)
        async with self.d.sessionmaker() as s:
            v = await s.get(Verification, (sid, uuid.UUID(inp.verification_id)))
            evidence = dict(v.evidence or {})
            recorded = list(evidence.get("recorded", []))
            if inp.phase in recorded:
                return  # retry after a successful commit
            recorded.append(inp.phase)
            evidence["recorded"] = recorded

            if inp.phase == "escalated":
                v.flags = [*v.flags, "review SLA breached"]
                v.evidence = evidence
                await s.commit()
                return

            if inp.phase == "ai":
                evidence["stages"] = inp.results
                evidence["decision"] = inp.decision
                v.score = inp.decision.get("score")
                v.flags = inp.decision.get("flags", [])
                v.model_versions = self.d.backend.versions()
            else:
                if inp.reviewer is None:
                    raise ValueError(f"Reviewer missing for phase={inp.phase}")
                evidence["review"] = {
                    "reviewer_id": inp.reviewer.reviewer_id,
                    "decision": inp.reviewer.decision,
                    "reason": inp.reviewer.reason,
                }
            status = inp.decision["status"]
            v.status = status
            v.reasons = inp.decision.get("reasons", [])
            v.evidence = evidence
            if status != Decision.NEEDS_REVIEW:
                v.decided_at = utcnow()

            animal = await s.get(Animal, (sid, aid))
            if animal is None:
                raise ValueError(f"Animal not found: {aid}")
            listing = await s.get(Listing, (sid, animal.listing_id))
            if listing is None:
                raise ValueError(f"Listing not found: {animal.listing_id}")
            listing.status = LISTING_STATUS[Decision(status)]
            events.add_event(
                s,
                seller_id=sid,
                topic=events.VERIFY_DECIDED,
                key=req.animal_id,
                payload={
                    "seller_id": req.seller_id,
                    "animal_id": req.animal_id,
                    "listing_id": req.listing_id,
                    "verification_id": inp.verification_id,
                    "status": status,
                    "phase": inp.phase,
                    "score": inp.decision.get("score"),
                },
            )
            await s.commit()

    @activity.defn
    async def index_identity(self, inp: IndexInput) -> None:
        req = inp.req
        sid, aid = uuid.UUID(req.seller_id), uuid.UUID(req.animal_id)
        async with self.d.sessionmaker() as s:
            animal = await s.get(Animal, (sid, aid))
            if animal is None:
                raise ValueError(f"Animal not found: {aid}")
            listing = await s.get(Listing, (sid, animal.listing_id))
            if listing is None:
                raise ValueError(f"Listing not found: {animal.listing_id}")
        await asyncio.to_thread(
            self.d.index.upsert,
            req.animal_id,
            inp.centroid,
            {
                "species": animal.species,
                "status": "active",
                "state": listing.state,
                "seller_id": req.seller_id,
                "listing_id": req.listing_id,
            },
        )

    def all(self) -> list[Any]:
        return [
            self.start_verification,
            self.analyze_media,
            self.fraud_and_rules,
            self.score,
            self.record_decision,
            self.index_identity,
        ]


def _blank():
    import numpy as np

    return np.zeros((10, 10, 3), dtype=np.uint8)
