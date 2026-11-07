import json
import uuid

from sqlalchemy import select

from kisan import events
from kisan.db.models import Outbox
from kisan.events.relay import relay_once


class FakeProducer:
    def __init__(self, fail_after=None):
        self.sent = []
        self.fail_after = fail_after

    async def send_and_wait(self, topic, value, key):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise ConnectionError("broker down")
        self.sent.append((topic, key.decode(), json.loads(value)))


async def test_relay_publishes_once(db):
    sid = uuid.uuid4()
    async with db() as s:
        for i in range(3):
            events.add_event(s, seller_id=sid, topic=events.VERIFY_REQUESTED, key=f"a{i}", payload={"i": i})
        await s.commit()

    p = FakeProducer()
    async with db() as s:
        assert await relay_once(s, p) == 3
    async with db() as s:
        assert await relay_once(s, p) == 0
    assert [k for _, k, _ in p.sent] == ["a0", "a1", "a2"]


async def test_relay_keeps_unsent_rows_when_broker_fails(db):
    sid = uuid.uuid4()
    async with db() as s:
        for i in range(2):
            events.add_event(s, seller_id=sid, topic=events.MEDIA_UPLOADED, key=f"m{i}", payload={})
        await s.commit()
    async with db() as s:
        try:
            await relay_once(s, FakeProducer(fail_after=1))
        except ConnectionError:
            await s.rollback()
    async with db() as s:
        pending = (await s.scalars(select(Outbox).where(Outbox.published_at.is_(None)))).all()
    # nothing marked published; the sent one is re-sent later (at-least-once)
    assert len(pending) == 2
