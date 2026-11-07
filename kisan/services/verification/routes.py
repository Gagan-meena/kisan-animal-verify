"""Verification status for sellers, and the review console API for moderators."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kisan import events
from kisan.db.models import Animal, Decision, Review, Seller, Verification
from kisan.db.session import get_session
from kisan.services.deps import current_reviewer, current_seller
from kisan.services.schemas import (
    ReuploadOut,
    ReviewIn,
    ReviewQueueItem,
    SellerVerificationOut,
)
from kisan.services.verification.gateway import WorkflowGateway, get_gateway

seller_router = APIRouter(prefix="/v1", tags=["verification"])
review_router = APIRouter(prefix="/v1/review", tags=["review"])

SELLER_MESSAGES = {
    Decision.PENDING: "We are checking your photos. This usually takes under 2 minutes.",
    Decision.NEEDS_REVIEW: "Our team is checking your listing. You will get a message when it is done.",
    Decision.VERIFIED: "Your animal is verified and the listing is live.",
    Decision.REUPLOAD: "Some photos need to be taken again.",
    Decision.BLOCKED: "This listing cannot be published.",
}


async def _latest(session: AsyncSession, seller_id: uuid.UUID, animal_id: uuid.UUID) -> Verification | None:
    return await session.scalar(
        select(Verification)
        .where(Verification.seller_id == seller_id, Verification.animal_id == animal_id)
        .order_by(Verification.created_at.desc())
        .limit(1)
    )


@seller_router.get("/animals/{animal_id}/verification", response_model=SellerVerificationOut)
async def seller_status(
    animal_id: uuid.UUID,
    seller: Seller = Depends(current_seller),
    session: AsyncSession = Depends(get_session),
):
    if await session.get(Animal, (seller.id, animal_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found.")
    v = await _latest(session, seller.id, animal_id)
    if v is None:
        return SellerVerificationOut(status=Decision.PENDING, message=SELLER_MESSAGES[Decision.PENDING])
    message = SELLER_MESSAGES[Decision(v.status)]
    reupload = []
    if v.status == Decision.REUPLOAD:
        reupload = [ReuploadOut(**r) for r in v.evidence.get("decision", {}).get("reupload", [])]
    if v.status in (Decision.BLOCKED, Decision.REUPLOAD) and not reupload and v.reasons:
        message = f"{message} {v.reasons[0]}"
    return SellerVerificationOut(status=v.status, message=message, reupload=reupload)


@review_router.get("/queue", response_model=list[ReviewQueueItem])
async def review_queue(
    limit: int = Query(50, le=200),
    _: str = Depends(current_reviewer),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.scalars(
            select(Verification)
            .where(Verification.status == Decision.NEEDS_REVIEW)
            .order_by(Verification.created_at)
            .limit(limit)
        )
    ).all()
    return [
        ReviewQueueItem(
            seller_id=v.seller_id,
            animal_id=v.animal_id,
            verification_id=v.id,
            score=v.score,
            flags=v.flags,
            waiting_since=v.created_at.isoformat(),
        )
        for v in rows
    ]


@review_router.get("/{seller_id}/{animal_id}")
async def review_detail(
    seller_id: uuid.UUID,
    animal_id: uuid.UUID,
    _: str = Depends(current_reviewer),
    session: AsyncSession = Depends(get_session),
):
    v = await _latest(session, seller_id, animal_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No verification found.")
    return {
        "verification_id": str(v.id),
        "status": v.status,
        "score": v.score,
        "flags": v.flags,
        "reasons": v.reasons,
        "evidence": v.evidence,
        "model_versions": v.model_versions,
    }


@review_router.post("/{seller_id}/{animal_id}", status_code=status.HTTP_202_ACCEPTED)
async def submit_review(
    seller_id: uuid.UUID,
    animal_id: uuid.UUID,
    body: ReviewIn,
    reviewer: str = Depends(current_reviewer),
    session: AsyncSession = Depends(get_session),
    gateway: WorkflowGateway = Depends(get_gateway),
):
    v = await _latest(session, seller_id, animal_id)
    if v is None or v.status != Decision.NEEDS_REVIEW:
        raise HTTPException(status.HTTP_409_CONFLICT, "This animal is not waiting for review.")

    session.add(
        Review(
            seller_id=seller_id,
            animal_id=animal_id,
            reviewer_id=reviewer,
            decision=body.decision,
            reason=body.reason,
            labels=body.labels,
        )
    )
    events.add_event(
        session,
        seller_id=seller_id,
        topic=events.REVIEW_CLOSED,
        key=str(animal_id),
        payload={
            "seller_id": str(seller_id),
            "animal_id": str(animal_id),
            "verification_id": str(v.id),
            "reviewer_id": reviewer,
            "decision": body.decision,
            "ai_status": v.evidence.get("decision", {}).get("ai_status"),
            "labels": body.labels,
        },
    )
    await session.commit()
    await gateway.signal_review(
        v.workflow_id, {"decision": body.decision, "reviewer_id": reviewer, "reason": body.reason}
    )
    return {"status": "accepted"}
