"""Stage 2: detect the animal, reject empty / crowded frames, crop for later stages."""

from __future__ import annotations

from typing import Any

from kisan.ml import yolo
from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import Detection, MediaItem, ReuploadCode, ReuploadItem, StageResult
from kisan.rules.policy import FULL_BODY_VIEWS

NAME = "detect"


def _animals(dets: list[Detection], ctx: AnalyzeContext) -> list[Detection]:
    keep = [d for d in dets if d.label in ctx.backend.animal_labels and d.conf >= ctx.th.det_conf]
    return sorted(keep, key=lambda d: d.area, reverse=True)


def _assign(item: MediaItem, animals: list[Detection]) -> None:
    if animals:
        item.detection = animals[0]
        item.crop = yolo.crop(item.bgr, animals[0])
    else:
        item.crop = item.bgr


def run(ctx: AnalyzeContext) -> StageResult:
    reupload: list[ReuploadItem] = []
    evidence: dict[str, dict[str,Any]] = {}

    if ctx.photos:
        for it, dets in zip(ctx.photos, ctx.backend.detect(ctx.photos), strict=True):
            animals = _animals(dets, ctx)
            frame = float(it.bgr.shape[0] * it.bgr.shape[1])
            coverage = animals[0].area / frame if animals else 0.0
            big_others = [d for d in animals[1:] if d.area / frame >= ctx.th.second_animal_area]
            evidence[it.image_id] = {
                "animals": len(animals),
                "coverage": round(coverage, 3),
                "conf": round(animals[0].conf, 3) if animals else None,
                "label": animals[0].label if animals else None,
            }
            if it.view in FULL_BODY_VIEWS:
                if not animals:
                    reupload.append(
                        ReuploadItem(it.image_id,
                            it.view,
                            "no animal found in this photo",
                            ReuploadCode.NO_ANIMAL
                        )
                    )
                elif coverage < ctx.th.min_body_coverage:
                    reupload.append(
                        ReuploadItem(it.image_id,
                            it.view,
                            "animal is too far; move closer",
                            ReuploadCode.TOO_FAR
                        )
                    )
                elif big_others:
                    reupload.append(
                        ReuploadItem(
                            it.image_id,
                            it.view,
                            "more than one animal in the photo; photograph one",
                            ReuploadCode.MANY_ANIMALS
                        )
                    )
            _assign(it, animals)

    usable_frames:list[MediaItem] = []
    if ctx.video_frames:
        for fr, dets in zip(ctx.video_frames, ctx.backend.detect(ctx.video_frames), strict=True):
            animals = _animals(dets, ctx)
            if animals:
                _assign(fr, animals)
                usable_frames.append(fr)
    ctx.video_frames = usable_frames

    return StageResult(
        name=NAME,
        passed=bool(ctx.photos) and not reupload,
        score=None,  # gate only; not weighted
        hard_gate=True,
        reupload=reupload,
        evidence={"images": evidence, "video_frames_with_animal": len(usable_frames)},
    )
