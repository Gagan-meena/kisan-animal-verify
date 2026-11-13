"""Temporal worker: runs VerifyAnimal workflows and their activities.

Scale replicas on the Temporal task-queue backlog; GPU work itself goes to Triton.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from kisan.config import get_settings
from kisan.db.session import get_sessionmaker
from kisan.ml.backends import get_backend
from kisan.services.verification.activities import Deps, VerifyActivities
from kisan.services.verification.workflow import VerifyAnimal
from kisan.storage import get_storage
from kisan.vector import get_index


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    backend = get_backend()
    index = get_index()
    client = await Client.connect(s.temporal_host)
    acts = VerifyActivities(Deps(get_sessionmaker(), get_storage(),backend, index , s))
    index.ensure_collection(backend.dim, shards=s.qdrant_shards, replicas=s.qdrant_replicas)
    worker = Worker(
        client,
        task_queue=s.temporal_task_queue,
        workflows=[VerifyAnimal],
        activities=acts.all(),
        max_concurrent_activities=16,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
