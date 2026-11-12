# type: ignore
"""Full Temporal workflow test with time skipping. Needs the Temporal test server binary,
which the SDK downloads on first run; skipped when it cannot be fetched (offline CI)."""

import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError  # noqa: F401
from temporalio.worker import Worker

from kisan.services.verification.contracts import AnalyzeResult, RecordInput, ReviewSignal, VerifyRequest
from kisan.services.verification.workflow import VerifyAnimal


@pytest.fixture
async def env():
    from temporalio.testing import WorkflowEnvironment

    try:
        e = await WorkflowEnvironment.start_time_skipping()
    except RuntimeError as err:
        pytest.skip(f"Temporal test server unavailable: {err}")
    yield e
    await e.shutdown()


def fake_activities(decision_status: str, recorded: list):
    @activity.defn(name="start_verification")
    async def start_verification(req):
        return "v1"

    @activity.defn(name="analyze_media")
    async def analyze_media(req):
        return AnalyzeResult(results=[], centroid=[0.1, 0.2], phashes={}, stopped_at=None)

    @activity.defn(name="fraud_and_rules")
    async def fraud_and_rules(inp):
        return []

    @activity.defn(name="score")
    async def score(inp):
        return {"status": decision_status, "score": 90.0, "reasons": []}

    @activity.defn(name="record_decision")
    async def record_decision(inp:RecordInput):
        recorded.append((inp.phase, inp.decision["status"]))

    @activity.defn(name="index_identity")
    async def index_identity(inp):
        recorded.append(("indexed", None))

    return [start_verification, analyze_media, fraud_and_rules, score, record_decision, index_identity]


async def test_review_signal_completes_workflow(env):
    recorded = []
    async with Worker(
        env.client,
        task_queue="t",
        workflows=[VerifyAnimal],
        activities=fake_activities("NEEDS_REVIEW", recorded),
    ):
        req = VerifyRequest(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
        h = await env.client.start_workflow(VerifyAnimal.run, args=[req, 4.0], id="wf-1", task_queue="t")
        await env.sleep(60)
        assert await h.query(VerifyAnimal.status) == "NEEDS_REVIEW"
        await h.signal(VerifyAnimal.reviewed, ReviewSignal("VERIFIED", "mod-1"))
        assert await h.result() == "VERIFIED"
    assert recorded == [("ai", "NEEDS_REVIEW"), ("review", "VERIFIED"), ("indexed", None)]


async def test_review_sla_escalates_then_waits(env):
    recorded = []
    async with Worker(
        env.client,
        task_queue="t2",
        workflows=[VerifyAnimal],
        activities=fake_activities("NEEDS_REVIEW", recorded),
    ):
        req = VerifyRequest(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
        h = await env.client.start_workflow(VerifyAnimal.run, args=[req, 4.0], id="wf-2", task_queue="t2")
        await env.sleep(5 * 3600)
        assert ("escalated", "NEEDS_REVIEW") in recorded
        await h.signal(
            VerifyAnimal.reviewed, ReviewSignal("REUPLOAD", "mod-2", "LEFT photo is a different cow")
        )
        assert await h.result() == "REUPLOAD"


async def test_workflow_passes_sandbox_validation():
    """Runs offline: catches non-deterministic imports in the workflow module."""
    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
    from temporalio.workflow import _Definition

    SandboxedWorkflowRunner().prepare_workflow(_Definition.must_from_class(VerifyAnimal))