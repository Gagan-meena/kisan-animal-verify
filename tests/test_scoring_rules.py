import numpy as np

from kisan.ml import scoring, yolo
from kisan.ml.stages import fraud
from kisan.ml.stages.fraud import DuplicateHit, PhotoFacts
from kisan.ml.types import ReuploadCode, ReuploadItem, StageResult
from kisan.rules.engine import StateRuleRow, evaluate


def ok(name:str, score:float | None=None):
    return StageResult(name, True, score)


def test_weights_renormalise_over_built_stages():
    # breed/age/tag not built yet: only identity(30), species(20), quality(15), views(10) count
    rs = [ok("identity", 1.0), ok("species", 1.0), ok("quality", 0.5), ok("views", 1.0)]
    assert scoring.weighted_score(rs) == round(100 * (30 + 20 + 7.5 + 10) / 75, 1)


def test_decision_ladder():
    good = [ok("identity", 0.95), ok("species", 0.97), ok("quality", 1.0), ok("views", 1.0)]
    assert scoring.decide(good).status == "VERIFIED"
    assert scoring.decide(good, human_confirms_all=True).status == "NEEDS_REVIEW"

    flagged = [*good, StageResult("fraud", False, None, flags=["seller KYC is not complete"])]
    d = scoring.decide(flagged)
    assert d.status == "NEEDS_REVIEW" and d.reasons == ["seller KYC is not complete"]

    retake = [*good,
         StageResult(
            "quality",
            False, 0.8,
            reupload=[ReuploadItem("i", "LEFT", "blurry",ReuploadCode.BLURRY)]
        )
    ]
    d = scoring.decide(retake)
    assert d.status == "REUPLOAD" and d.reasons == ["LEFT: blurry"]

    blocked = [*good, StageResult("rules", False, None, blocked=True, block_reasons=["not permitted"])]
    assert scoring.decide(blocked).status == "BLOCKED"

    weak = [ok("identity", 0.2), ok("species", 0.5), ok("quality", 0.6), ok("views", 0.5)]
    assert scoring.decide(weak).status == "REUPLOAD"


def test_rules_engine():
    rule = StateRuleRow("RJ", "cow", "sell", True, ["ear_tag"], legally_reviewed=True)
    assert evaluate(rule, state="RJ", species="cow", docs_present={"ear_tag"}).flags == []
    assert evaluate(rule, state="RJ", species="cow", docs_present=set()).flags == [
        "missing required documents: ear_tag"
    ]
    banned = StateRuleRow("XX", "cow", "sell", False, note="Sale not permitted", legally_reviewed=True)
    out = evaluate(banned, state="XX", species="cow", docs_present=set())
    assert out.blocked and out.reasons == ["Sale not permitted"]
    assert evaluate(None, state="RJ", species="yak", docs_present=set()).flags


def test_fraud_same_photo_twice_and_gallery():
    h = "f0f0f0f0f0f0f0f0"
    photos = [
        PhotoFacts("a", "LEFT", h, {"source": "in_app_camera", "sig": "x"}),
        PhotoFacts("b", "RIGHT", h, {"source": "in_app_camera", "sig": "x"}),
        PhotoFacts("c", "FACE", "0f0f0f0f0f0f0f0f", {"source": "gallery"}),
    ]
    r = fraud.run(photos, seller_id="s1", seller_kyc="VERIFIED", duplicate_hits=[])
    reasons = {(x.image_id, x.reason) for x in r.reupload}
    assert ("b", "same photo as the LEFT photo; take a new RIGHT photo") in reasons
    assert ("c", "take this photo with the in-app camera") in reasons


def test_fraud_capture_span_and_duplicates():
    photos = [
        PhotoFacts(
            "a", "LEFT", None, {"source": "in_app_camera", "sig": "x", "captured_at": "2026-10-01T08:00:00"}
        ),
        PhotoFacts(
            "b", "RIGHT", None, {"source": "in_app_camera", "sig": "x", "captured_at": "2026-10-04T08:00:00"}
        ),
    ]
    hits = [DuplicateHit("a2", "l2", "s1", 0.97), DuplicateHit("a3", "l3", "s9", 0.50)]
    r = fraud.run(photos, seller_id="s1", seller_kyc="VERIFIED", duplicate_hits=hits)
    assert "photos were taken 72 hours apart" in r.flags
    assert any("this seller" in f for f in r.flags)
    assert not any("l3" in f for f in r.flags)


def test_yolo_decode_maps_back_to_original_pixels():
    classes = ["cow", "buffalo"]
    img_h, img_w = 960, 1280
    chw, ratio, pad = yolo.letterbox(np.zeros((img_h, img_w, 3), np.uint8), 640)
    assert chw.shape == (3, 640, 640)
    # one strong "buffalo" box at original (320,240)-(960,720), plus a weaker duplicate
    x1, y1, x2, y2 = 320, 240, 960, 720
    cx, cy = (x1 + x2) / 2 * ratio + pad[0], (y1 + y2) / 2 * ratio + pad[1]
    w, h = (x2 - x1) * ratio, (y2 - y1) * ratio
    raw = np.zeros((6, 8400), np.float32)
    raw[:, 0] = [cx, cy, w, h, 0.05, 0.91]
    raw[:, 1] = [cx + 2, cy + 1, w, h, 0.02, 0.80]
    dets = yolo.decode(raw, classes, ratio, pad, (img_h, img_w))
    assert len(dets) == 1
    d = dets[0]
    assert d.label == "buffalo" and abs(d.conf - 0.91) < 1e-6
    assert np.allclose(d.box, (x1, y1, x2, y2), atol=1.0)


def test_fraud_mixed_timezone_capture_times():
    photos = [
        PhotoFacts(
            "a", "LEFT", None, {"source": "in_app_camera", "sig": "x", "captured_at": "2026-10-09T08:00:00"}
        ),
        PhotoFacts(
            "b",
            "RIGHT",
            None,
            {"source": "in_app_camera", "sig": "x", "captured_at": "2026-10-09T13:40:00+05:30"},
        ),
    ]
    r = fraud.run(photos, seller_id="s1", seller_kyc="VERIFIED", duplicate_hits=[])
    assert r.passed, r.flags
