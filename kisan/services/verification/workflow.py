"""VerifyAnimal: one durable workflow per submission (rule 2).

Survives worker crashes and deploys, retries failed steps, and waits for a human
reviewer for as long as needed without holding any compute.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, TypedDict

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from kisan.services.verification.activities import VerifyActivities
    from kisan.services.verification.contracts import (
        AnalyzeResult,
        FraudInput,
        IndexInput,
        RecordInput,
        ReviewSignal,
        ScoreInput,
        VerifyRequest,
    )

class ActivityOptions(TypedDict, total=False):
    start_to_close_timeout: timedelta
    schedule_to_close_timeout: timedelta
    heartbeat_timeout: timedelta
    retry_policy: RetryPolicy
    task_queue: str


DB: ActivityOptions = {
    "start_to_close_timeout":timedelta(seconds=30),
    "retry_policy":RetryPolicy(maximum_attempts=10, maximum_interval=timedelta(seconds=30)),
}
GPU:ActivityOptions = {
    "start_to_close_timeout":timedelta(minutes=5),
    "heartbeat_timeout":timedelta(seconds=90),
    "retry_policy":RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5)),
}


@workflow.defn
class VerifyAnimal:
    def __init__(self) -> None:
        self._review: ReviewSignal | None = None
        self._status: str = "PENDING"

    @workflow.signal
    def reviewed(self, decision: ReviewSignal) -> None:
        if self._review is None:  # first decision wins
            self._review = decision

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.run
    async def run(self, req: VerifyRequest, review_sla_hours: float = 4.0) -> str:
        vid: str = await workflow.execute_activity_method(
            VerifyActivities.start_verification,
            req,
            **DB
        )

        analysis: AnalyzeResult | None = None
        results:list[dict[str,Any]] = []
        decision: dict[str, Any] = {}
        try:
            analysis = await workflow.execute_activity_method(
                VerifyActivities.analyze_media, 
                req, 
                **GPU
            )
    
            results = list(analysis.results)
            if analysis.stopped_at is None:
                results += await workflow.execute_activity_method(
                    VerifyActivities.fraud_and_rules, 
                    FraudInput(req, analysis.centroid, analysis.phashes), 
                    **DB
                )
    
            decision = await workflow.execute_activity_method(
                VerifyActivities.score, 
                ScoreInput(results), 
                **DB
            )
        except ActivityError:
            decision = {
                "status":"NEEDS_REVIEW",
                "score":None,
                "flags":["automatic check failed"],
                "reasons":None
            }
            pass


        self._status = decision["status"]
        await workflow.execute_activity_method(
            VerifyActivities.record_decision, 
            RecordInput(req, vid, "ai", decision, results), 
            **DB
        )

        if decision["status"] == "NEEDS_REVIEW":
            self._status = "NEEDS_REVIEW"
            try:
                await workflow.wait_condition(
                    lambda: self._review is not None, timeout=timedelta(hours=review_sla_hours)
                )
            except TimeoutError:
                await workflow.execute_activity_method(
                    VerifyActivities.record_decision, 
                    RecordInput(req, vid, "escalated", decision), 
                    **DB
                )
                await workflow.wait_condition(lambda: self._review is not None)

            review = self._review
            if review is None:
                raise RuntimeError("Review signal missing after wait_condition")
            decision = {
                "status": review.decision,
                "score": decision.get("score"),
                "reasons": [review.reason] if review.reason else [],
            }
            await workflow.execute_activity_method(
                VerifyActivities.record_decision,
                RecordInput(req, vid, "review", decision, reviewer=review),
                **DB,
            )
            self._status = review.decision

        if decision["status"] == "VERIFIED" and analysis and analysis.centroid:
            await workflow.execute_activity_method(
                VerifyActivities.index_identity, 
                IndexInput(req, analysis.centroid), 
                **DB
            )
        return decision["status"]
