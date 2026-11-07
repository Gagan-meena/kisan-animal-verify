"""Thin wrapper over the Temporal client so the API layer can be tested without Temporal."""

from __future__ import annotations

from typing import Protocol

from kisan.config import get_settings


class WorkflowGateway(Protocol):
    async def signal_review(self, workflow_id: str, decision: dict) -> None: ...


class TemporalGateway:
    def __init__(self):
        self._client = None

    async def _get(self):
        if self._client is None:
            from temporalio.client import Client

            self._client = await Client.connect(get_settings().temporal_host)
        return self._client

    async def signal_review(self, workflow_id: str, decision: dict) -> None:
        from kisan.services.verification.workflow import ReviewSignal, VerifyAnimal

        client = await self._get()
        await client.get_workflow_handle(workflow_id).signal(VerifyAnimal.reviewed, ReviewSignal(**decision))


_gateway = TemporalGateway()


def get_gateway() -> WorkflowGateway:
    return _gateway
