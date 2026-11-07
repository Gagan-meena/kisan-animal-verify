"""Stage 4: is each photo the view the app asked for, and are all required views covered?"""

from __future__ import annotations

from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import ReuploadItem, StageResult
from kisan.rules.policy import required_views

NAME = "views"
_SWAP = {"LEFT": "RIGHT", "RIGHT": "LEFT"}


def run(ctx: AnalyzeContext) -> StageResult:
    reupload: list[ReuploadItem] = []
    evidence: dict[str, dict] = {}
    photos = [it for it in ctx.photos if it.crop is not None]

    for it, probs in zip(photos, ctx.backend.classify_view(photos) if photos else [], strict=True):
        pred = max(probs, key=probs.get)
        conf = probs[pred]
        evidence[it.image_id] = {"declared": it.view, "pred": pred, "conf": round(conf, 3)}
        if pred == it.view or conf < ctx.th.view_conf:
            continue
        if _SWAP.get(it.view) == pred:
            # Seller mixed up left and right: harmless, correct it silently.
            ctx.corrected_views[it.image_id] = pred
            evidence[it.image_id]["corrected"] = True
        else:
            reupload.append(
                ReuploadItem(it.image_id, it.view, f"this looks like a {pred} photo, not {it.view}")
            )

    rejected = {r.image_id for r in reupload}
    covered = {ctx.effective_view(it) for it in photos if it.image_id not in rejected}
    if ctx.video_frames:
        covered.add("VIDEO")
    needed = {str(v) for v in required_views(ctx.species)}
    missing = sorted(needed - covered)
    for v in missing:
        if not any(r.view == v for r in reupload):
            reupload.append(ReuploadItem("", v, f"{v} photo is missing"))

    return StageResult(
        name=NAME,
        passed=not reupload,
        score=len(needed & covered) / max(1, len(needed)),
        hard_gate=True,
        reupload=reupload,
        evidence={"images": evidence, "missing": missing},
    )
