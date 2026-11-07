"""Stage 5: do all photos show the same individual animal?

With a walk-around video, every photo must match at least one video frame (the video is
one continuous take, so it ties the views together). Without frames, every photo must
match at least one other photo. Opposite sides of an animal rarely match each other
directly, which is why we use best-match rather than all-pairs.
"""

from __future__ import annotations

import numpy as np

from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import StageResult
from kisan.rules.policy import FULL_BODY_VIEWS

NAME = "identity"
IDENTITY_VIEWS = FULL_BODY_VIEWS | {"FACE"}


def run(ctx: AnalyzeContext) -> StageResult:
    th = ctx.th
    photos = [it for it in ctx.photos if ctx.effective_view(it) in IDENTITY_VIEWS and it.crop is not None]
    frames = [f for f in ctx.video_frames if f.crop is not None]
    if len(photos) + len(frames) < 2:
        return StageResult(NAME, False, 0.0, flags=["not enough photos to confirm it is one animal"])

    emb = ctx.backend.embed(photos + frames)
    p_emb, f_emb = emb[: len(photos)], emb[len(photos) :]

    if len(frames) >= 2:
        mode = "video_anchor"
        best = (p_emb @ f_emb.T).max(axis=1)
        frame_sims = f_emb @ f_emb.T
        np.fill_diagonal(frame_sims, np.nan)
        frame_consistency = float(np.nanmin(frame_sims))
    else:
        mode = "pairwise"
        sims = p_emb @ p_emb.T
        np.fill_diagonal(sims, -1.0)
        best = sims.max(axis=1)
        frame_consistency = None

    per_image = {it.image_id: round(float(b), 3) for it, b in zip(photos, best, strict=True)}
    outliers = [it for it, b in zip(photos, best, strict=True) if b < th.same_animal_sim]
    flags = [f"{ctx.effective_view(it)} photo may show a different animal" for it in outliers]
    if frame_consistency is not None and frame_consistency < th.same_animal_sim:
        flags.append("walk-around video may show more than one animal")

    keep = np.array([b >= th.same_animal_sim for b in best] + [True] * len(frames))
    centroid = emb[keep].mean(axis=0) if keep.any() else emb.mean(axis=0)
    ctx.centroid = centroid / max(np.linalg.norm(centroid), 1e-12)

    weakest = float(best.min())
    score = float(
        np.clip((weakest - th.identity_score_lo) / (th.identity_score_hi - th.identity_score_lo), 0, 1)
    )
    return StageResult(
        name=NAME,
        passed=not flags,
        score=score,
        flags=flags,
        evidence={
            "mode": mode,
            "best_match": per_image,
            "weakest": round(weakest, 3),
            "frame_consistency": None if frame_consistency is None else round(frame_consistency, 3),
            "outliers": [it.image_id for it in outliers],
        },
    )
