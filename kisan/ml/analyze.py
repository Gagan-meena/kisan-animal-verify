"""GPU-side media analysis: stages 1-5 in one pass over the images.

These stages share decoded images and crops, so they run inside a single Temporal
activity instead of one activity each (which would re-download and re-decode every
image per stage). Cheaper DB/vector stages run as separate activities.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from kisan.ml.stages import detect, identity, quality, species, view
from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import StageResult

STAGES = (quality, detect, species, view, identity)


@dataclass
class AnalyzeOutput:
    results: list[StageResult]
    centroid: list[float] | None
    phashes: dict[str, str]
    stopped_at: str | None

    @property
    def hard_failed(self) -> bool:
        return self.stopped_at is not None


def analyze(ctx: AnalyzeContext) -> AnalyzeOutput:
    results: list[StageResult] = []
    stopped_at = None
    for stage in STAGES:
        r = stage.run(ctx)
        results.append(r)
        if r.stops_pipeline:
            stopped_at = r.name
            break
    centroid = None if ctx.centroid is None else np.asarray(ctx.centroid, dtype=np.float32).tolist()
    return AnalyzeOutput(
        results=results,
        centroid=centroid,
        phashes={it.image_id: it.phash for it in ctx.photos if it.phash},
        stopped_at=stopped_at,
    )
