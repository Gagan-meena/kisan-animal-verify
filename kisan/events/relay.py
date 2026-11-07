"""Outbox relay: ships committed outbox rows to Kafka (rule 2).

One active relay at a time, elected with a Postgres advisory lock; extra replicas wait
as hot standbys. Delivery is at-least-once, so consumers are idempotent (the Temporal
workflow ID is derived from the event, and duplicate starts are ignored).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kisan.db.models import Outbox, utcnow

log = logging.getLogger("kisan.relay")
LOCK_ID = 0x4B49_5341  # "KISA"


class Producer(Protocol):
    async def send_and_wait(self, topic: str, value: bytes, key: bytes) -> object: ...


async def relay_once(session: AsyncSession, producer: Producer, batch: int = 500) -> int:
    rows = (
        await session.scalars(
            select(Outbox).where(Outbox.published_at.is_(None)).order_by(Outbox.created_at).limit(batch)
        )
    ).all()
    if not rows:
        return 0
    sent = []
    for row in rows:
        await producer.send_and_wait(
            row.topic, json.dumps(row.payload, default=str).encode(), key=row.key.encode()
        )
        sent.append(row.id)
    await session.execute(update(Outbox).where(Outbox.id.in_(sent)).values(published_at=utcnow()))
    await session.commit()
    return len(sent)


async def run(sessionmaker: async_sessionmaker, producer: Producer, idle_sleep: float = 0.2) -> None:
    async with sessionmaker() as lock_session:
        while not (
            await lock_session.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID})
        ).scalar():
            log.info("another relay is active; standing by")
            await asyncio.sleep(5)
        log.info("relay is leader")
        while True:
            async with sessionmaker() as s:
                n = await relay_once(s, producer)
            if n == 0:
                await asyncio.sleep(idle_sleep)


async def main() -> None:
    from aiokafka import AIOKafkaProducer

    from kisan.config import get_settings
    from kisan.db.session import get_sessionmaker

    logging.basicConfig(level=logging.INFO)
    producer = AIOKafkaProducer(
        bootstrap_servers=get_settings().kafka_bootstrap, acks="all", enable_idempotence=True, linger_ms=5
    )
    await producer.start()
    try:
        await run(get_sessionmaker(), producer)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
