"""Workflow/activity payloads. Kept free of heavy imports so the Temporal workflow
sandbox can load them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerifyRequest:
    seller_id: str
    animal_id: str
    listing_id: str
    attempt: int = 1


@dataclass
class ReviewSignal:
    decision: str  # VERIFIED | REUPLOAD | BLOCKED
    reviewer_id: str
    reason: str = ""


@dataclass
class AnalyzeResult:
    results: list[dict[str,Any]]
    centroid: list[float] | None
    phashes: dict[str, str]
    stopped_at: str | None


@dataclass
class FraudInput:
    req: VerifyRequest
    centroid: list[float] | None
    phashes: dict[str, str]


@dataclass
class ScoreInput:
    results: list[dict[str,Any]]


@dataclass
class RecordInput:
    req: VerifyRequest
    verification_id: str
    phase: str  # "ai" | "review" | "escalated" Literal["ai", "review", "escalated"]
    decision: dict[str,Any]
    results: list[dict[str,Any]] = field(default_factory=list[dict[str, Any]])
    reviewer: ReviewSignal | None = None


@dataclass
class IndexInput:
    req: VerifyRequest
    centroid: list[float]


def workflow_id_for(animal_id: str, attempt: int) -> str:
    return f"verify-{animal_id}-{attempt}"
