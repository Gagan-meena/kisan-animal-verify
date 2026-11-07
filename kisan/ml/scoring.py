"""Turn stage evidence into one decision with reasons (rules 5 and 6)."""

from __future__ import annotations

from dataclasses import dataclass, field

from kisan.ml.types import StageResult

# Starting weights (percent). Stages that are skipped or not yet built are left out
# and the rest re-normalised. Recalibrate against reviewer outcomes.
WEIGHTS: dict[str, float] = {
    "identity": 30,
    "species": 20,
    "quality": 15,
    "views": 10,
    "breed": 10,
    "age": 10,
    "tag": 5,
}
VERIFY_AT = 85.0
REUPLOAD_BELOW = 60.0


@dataclass
class DecisionResult:
    status: str  # VERIFIED | NEEDS_REVIEW | REUPLOAD | BLOCKED
    score: float | None
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    reupload: list[dict] = field(default_factory=list)
    ai_status: str | None = None  # what the AI alone would have decided (pilot shadow mode)

    def __post_init__(self):
        if self.ai_status is None:
            self.ai_status = self.status

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def weighted_score(results: list[StageResult]) -> float | None:
    scored = [(WEIGHTS[r.name], r.score) for r in results if r.name in WEIGHTS and r.score is not None]
    total_w = sum(w for w, _ in scored)
    if not total_w:
        return None
    return round(100 * sum(w * s for w, s in scored) / total_w, 1)


def decide(results: list[StageResult], *, human_confirms_all: bool = False) -> DecisionResult:
    score = weighted_score(results)
    flags = [f for r in results for f in r.flags]
    reupload = [ri.__dict__ for r in results for ri in r.reupload]

    blocked = [reason for r in results if r.blocked for reason in r.block_reasons]
    if blocked:
        return DecisionResult("BLOCKED", score, flags, blocked, reupload)

    if reupload:
        reasons = [f"{r['view']}: {r['reason']}" for r in reupload]
        return DecisionResult("REUPLOAD", score, flags, reasons, reupload)

    if score is None or score < REUPLOAD_BELOW:
        return DecisionResult(
            "REUPLOAD", score, flags, ["photos are not clear enough to verify; please retake them"], reupload
        )

    if flags or score < VERIFY_AT:
        reasons = flags or [f"score {score} is below {VERIFY_AT}"]
        return DecisionResult("NEEDS_REVIEW", score, flags, reasons, reupload)

    if human_confirms_all:
        # Rule 6 pilot: the AI would approve, but a human confirms every decision.
        return DecisionResult(
            "NEEDS_REVIEW",
            score,
            flags,
            ["pilot: human confirmation of AI approval"],
            reupload,
            ai_status="VERIFIED",
        )
    return DecisionResult("VERIFIED", score, flags, [], reupload, ai_status="VERIFIED")
