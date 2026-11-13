"""Kafka topics and the transactional outbox (rule 2)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from kisan.db.models import Outbox

MEDIA_UPLOADED = "media.uploaded"
VERIFY_REQUESTED = "verify.requested"
VERIFY_DECIDED = "verify.decided"
REVIEW_CLOSED = "review.closed"


def dlq(topic: str) -> str:
    return f"{topic}.dlq"


def add_event(
        session: AsyncSession,
        *,
        seller_id: uuid.UUID,
        topic: str,
        key: str,
        payload: dict[str,Any]
    ) -> None:
    """Stage an event in the caller's transaction. Commit publishes nothing directly;
    the relay ships committed rows to Kafka, so DB and events never disagree."""
    session.add(Outbox(seller_id=seller_id, topic=topic, key=key, payload=payload))
