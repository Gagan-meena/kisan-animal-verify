"""Kafka consumer: ``verify.requested`` -> start a VerifyAnimal workflow (rule 2).

The workflow ID comes from (animal_id, attempt), so redelivered events never start a
second run. Unparseable events go to the DLQ instead of blocking the partition.
"""

from __future__ import annotations

import asyncio
import json
import logging

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from kisan import events
from kisan.config import get_settings
from kisan.services.verification.contracts import VerifyRequest, workflow_id_for

log = logging.getLogger("kisan.trigger")


def parse(value: bytes) -> VerifyRequest:
    d = json.loads(value)
    return VerifyRequest(
        seller_id=d["seller_id"],
        animal_id=d["animal_id"],
        listing_id=d["listing_id"],
        attempt=int(d.get("attempt", 1)),
    )


async def start(client: Client, req: VerifyRequest) -> bool:
    from kisan.services.verification.workflow import VerifyAnimal

    s = get_settings()
    try:
        await client.start_workflow(
            VerifyAnimal.run,
            args=[req, s.review_sla_hours],
            id=workflow_id_for(req.animal_id, req.attempt),
            task_queue=s.temporal_task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        return True
    except WorkflowAlreadyStartedError:
        log.info("workflow already started for %s attempt %s", req.animal_id, req.attempt)
        return False


async def main() -> None:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    client = await Client.connect(s.temporal_host)
    consumer = AIOKafkaConsumer(
        events.VERIFY_REQUESTED,
        bootstrap_servers=s.kafka_bootstrap,
        group_id="verify-trigger",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    dlq = AIOKafkaProducer(bootstrap_servers=s.kafka_bootstrap, acks="all")
    await consumer.start()
    await dlq.start()
    try:
        async for msg in consumer:
            try:
                req = parse(msg.value)
            except (ValueError, KeyError) as e:
                log.error("bad event at offset %s: %s", msg.offset, e)
                await dlq.send_and_wait(events.dlq(events.VERIFY_REQUESTED), msg.value, key=msg.key)
            else:
                await start(client, req)  # Temporal errors propagate: crash and resume from last commit
            await consumer.commit()
    finally:
        await consumer.stop()
        await dlq.stop()


if __name__ == "__main__":
    asyncio.run(main())
