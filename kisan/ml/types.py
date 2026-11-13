from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np


class ReuploadCode(StrEnum):
    NO_ANIMAL = "no_animal"
    TOO_FAR = "too_far"
    MANY_ANIMALS = "many_animals"
    WRONG_VIEW = "wrong_view"
    MISSING = "missing"
    SAME_PHOTO = "same_photo"
    USE_CAMERA = "use_camera"
    BLURRY = "blurry"
    TOO_DARK= "too_dark"
    GLARE = "glare"
    TOO_BRIGHT="too_bright"
    TOO_SMALL= "too_small"
    LOW_CONTRAST="low_contrast"
    CLIPPED="clipped"
    OTHER = "other"

@dataclass
class Detection:
    """Box in absolute pixel coords (x1, y1, x2, y2) of the source image."""

    box: tuple[float, float, float, float]
    conf: float
    label: str

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


@dataclass
class MediaItem:
    """One uploaded photo, or one frame sampled from the walk-around video."""

    image_id: str
    view: str  # declared view (VIDEO for frames)
    bgr: np.ndarray
    phash: str | None = None
    crop: np.ndarray | None = None
    detection: Detection | None = None
    embedding: np.ndarray | None = None


@dataclass
class ReuploadItem:
    image_id: str
    view: str
    reason: str
    code: str


@dataclass
class StageResult:
    name: str
    passed: bool
    # 0..1, or None when the stage was skipped (excluded from the weighted score)
    score: float | None
    hard_gate: bool = False
    flags: list[str] = field(default_factory=list[str])
    reupload: list[ReuploadItem] = field(default_factory=list[ReuploadItem])
    evidence: dict[str, Any] = field(default_factory=dict[str,Any])
    blocked: bool = False
    block_reasons: list[str] = field(default_factory=list[str])

    @property
    def stops_pipeline(self) -> bool:
        return self.hard_gate and not self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "hard_gate": self.hard_gate,
            "flags": self.flags,
            "reupload": [r.__dict__ for r in self.reupload],
            "evidence": self.evidence,
            "blocked": self.blocked,
            "block_reasons": self.block_reasons,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StageResult:
        return cls(
            name=d["name"],
            passed=d["passed"],
            score=d["score"],
            hard_gate=d.get("hard_gate", False),
            flags=list(d.get("flags", [])),
            reupload=[ReuploadItem(**r) for r in d.get("reupload", [])],
            evidence=dict(d.get("evidence", {})),
            blocked=d.get("blocked", False),
            block_reasons=list(d.get("block_reasons", [])),
        )
