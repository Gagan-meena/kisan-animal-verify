"""Stage 1: image quality (server-side repeat of the on-device check)."""

from __future__ import annotations

import cv2
import imagehash
import numpy as np
from PIL import Image

from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.thresholds import Thresholds
from kisan.ml.types import ReuploadItem, StageResult

NAME = "quality"


def measure(bgr: np.ndarray) -> dict[str, float]:
    h, w = bgr.shape[:2]
    # Measure blur at a fixed scale so the threshold does not depend on resolution.
    scale = 1024 / max(h, w)
    small = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return {
        "short_side": float(min(h, w)),
        "blur_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
        "clipped": float(((gray < 5) | (gray > 250)).mean()),
    }


def problems(m: dict[str, float], th: Thresholds) -> list[str]:
    p = []
    if m["short_side"] < th.min_short_side:
        p.append(f"photo too small ({int(m['short_side'])}px, need {th.min_short_side}px)")
    if m["blur_var"] < th.min_blur_var:
        p.append("photo is blurry; hold the phone steady")
    if m["brightness"] < th.min_brightness:
        p.append("photo is too dark; move to daylight")
    elif m["brightness"] > th.max_brightness:
        p.append("photo is too bright; avoid direct sun behind the animal")
    if m["contrast"] < th.min_contrast:
        p.append("photo has very low contrast")
    if m["clipped"] > th.max_clipped_fraction:
        p.append("large parts of the photo are pure black or white")
    return p


def phash(bgr: np.ndarray) -> str:
    return str(imagehash.phash(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))))


def run(ctx: AnalyzeContext) -> StageResult:
    metrics: dict[str, dict] = {}
    reupload: list[ReuploadItem] = []
    for it in ctx.photos:
        m = measure(it.bgr)
        it.phash = phash(it.bgr)
        metrics[it.image_id] = {k: round(v, 2) for k, v in m.items()}
        p = problems(m, ctx.th)
        if p:
            reupload.append(ReuploadItem(it.image_id, it.view, "; ".join(p)))
    total = max(1, len(ctx.photos))
    return StageResult(
        name=NAME,
        passed=not reupload,
        score=(total - len(reupload)) / total,
        hard_gate=True,
        reupload=reupload,
        evidence={"images": metrics},
    )
