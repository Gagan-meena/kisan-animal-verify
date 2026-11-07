"""Stage 3: does the animal match the category the seller chose?"""

from __future__ import annotations

from collections import defaultdict

from kisan.ml.stages.context import AnalyzeContext
from kisan.ml.types import StageResult
from kisan.rules.policy import FULL_BODY_VIEWS

NAME = "species"


def run(ctx: AnalyzeContext) -> StageResult:
    body = [it for it in ctx.photos if it.view in FULL_BODY_VIEWS and it.detection is not None]
    if not body:
        return StageResult(NAME, False, 0.0, flags=["no full-body photo to check the species"])

    totals: dict[str, float] = defaultdict(float)
    for probs in ctx.backend.classify_species(body):
        for label, p in probs.items():
            totals[label] += p
    probs = {k: v / len(body) for k, v in totals.items()}
    pred = max(probs, key=probs.get)
    conf = probs[pred]
    declared_p = probs.get(ctx.species, 0.0)
    evidence = {
        "declared": ctx.species,
        "pred": pred,
        "conf": round(conf, 3),
        "top3": [[k, round(v, 3)] for k, v in sorted(probs.items(), key=lambda kv: -kv[1])[:3]],
    }

    if pred == ctx.species and conf >= ctx.th.species_conf:
        return StageResult(NAME, True, conf, evidence=evidence)
    if pred != ctx.species and conf >= ctx.th.species_conf:
        return StageResult(
            NAME,
            False,
            declared_p,
            flags=[f"photos look like a {pred}, listed as {ctx.species}"],
            evidence=evidence,
        )
    return StageResult(
        NAME,
        False,
        declared_p,
        flags=[f"species unclear (best guess {pred} at {conf:.0%})"],
        evidence=evidence,
    )
