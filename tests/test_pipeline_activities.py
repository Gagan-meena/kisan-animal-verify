"""End-to-end over the real activities (sqlite + in-memory storage + fake models),
in the same order the VerifyAnimal workflow calls them."""

import os
import tempfile
import uuid

import cv2
import pytest
from temporalio.testing import ActivityEnvironment

from kisan.config import get_settings
from kisan.db.models import Animal, AnimalImage, Listing, ListingStatus, Seller, StateRule, Verification
from kisan.ml.backends import FakeBackend
from kisan.rules.policy import required_views
from kisan.services.verification.activities import Deps, VerifyActivities
from kisan.services.verification.contracts import (
    FraudInput,
    IndexInput,
    RecordInput,
    ReviewSignal,
    ScoreInput,
    VerifyRequest,
)
from kisan.storage import MemoryStorage
from kisan.vector import MemoryIndex
from tests.helpers import sharp_image

META = {"source": "in_app_camera", "captured_at": "2026-10-09T08:00:00+05:30", "sig": "s"}


def mp4_bytes(n=12) -> bytes:
    path = os.path.join(tempfile.mkdtemp(), "v.mp4")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 6, (1280, 960))
    for i in range(n):
        w.write(sharp_image(200 + i))
    w.release()
    with open(path, "rb") as f:
        return f.read()


async def seed(db, storage, *, state="RJ", kyc="VERIFIED", reviewed_rule=True, species="cow"):
    sid, lid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with db() as s:
        s.add(Seller(id=sid, state=state, kyc_status=kyc))
        s.add(
            Listing(
                seller_id=sid, id=lid, state=state, title="t", price_inr=1, status=ListingStatus.VERIFYING
            )
        )
        s.add(
            Animal(
                seller_id=sid, id=aid, listing_id=lid, species=species, sex="female", tag_id="123456789012"
            )
        )
        if await s.get(StateRule, (state, species, "sell")) is None:
            s.add(
                StateRule(
                    state=state,
                    species=species,
                    action="sell",
                    allowed=True,
                    docs_required=["ear_tag"],
                    legally_reviewed=reviewed_rule,
                )
            )
        for i, v in enumerate(sorted(required_views(species))):
            key = f"{aid}/{v}"
            if v == "VIDEO":
                storage.objects[key] = mp4_bytes()
                ctype = "video/mp4"
            else:
                storage.objects[key] = cv2.imencode(".jpg", sharp_image(i), [cv2.IMWRITE_JPEG_QUALITY, 90])[
                    1
                ].tobytes()
                ctype = "image/jpeg"
            s.add(
                AnimalImage(
                    seller_id=sid,
                    animal_id=aid,
                    view=str(v),
                    storage_key=key,
                    content_type=ctype,
                    capture_meta=META,
                    uploaded=True,
                )
            )
        await s.commit()
    return VerifyRequest(str(sid), str(aid), str(lid), 1)


async def run_like_workflow(acts: VerifyActivities, req: VerifyRequest):
    env = ActivityEnvironment()
    env.info = env.info.__class__(**{**env.info.__dict__, "workflow_id": "verify-test-1"})
    vid = await env.run(acts.start_verification, req)
    analysis = await env.run(acts.analyze_media, req)
    results = list(analysis.results)
    if analysis.stopped_at is None:
        results += await env.run(acts.fraud_and_rules, FraudInput(req, analysis.centroid, analysis.phashes))
    decision = await env.run(acts.score, ScoreInput(results))
    await env.run(acts.record_decision, RecordInput(req, vid, "ai", decision, results))
    return env, vid, analysis, decision


@pytest.fixture
def make_acts(db):
    def _make(backend=None, index=None, storage=None, human_confirms_all=False):
        s = get_settings().model_copy(update={"pilot_human_confirms_all": human_confirms_all})
        return VerifyActivities(
            Deps(db, storage or MemoryStorage(), backend or FakeBackend(), index or MemoryIndex(), s)
        )

    return _make


async def test_clean_listing_is_verified_and_indexed(db, make_acts):
    storage, index = MemoryStorage(), MemoryIndex()
    acts = make_acts(storage=storage, index=index)
    req = await seed(db, storage)
    env, vid, analysis, decision = await run_like_workflow(acts, req)

    assert decision["status"] == "VERIFIED", decision
    assert decision["score"] >= 85
    stages = {r["name"] for r in analysis.results}
    assert {"quality", "detect", "species", "views", "identity"} <= stages
    identity = next(r for r in analysis.results if r["name"] == "identity")
    assert identity["evidence"]["mode"] == "video_anchor"

    await env.run(acts.index_identity, IndexInput(req, analysis.centroid))
    assert req.animal_id in index.points

    async with db() as s:
        listing = await s.get(Listing, (uuid.UUID(req.seller_id), uuid.UUID(req.listing_id)))
        v = await s.get(Verification, (uuid.UUID(req.seller_id), uuid.UUID(vid)))
    assert listing.status == ListingStatus.LIVE
    assert v.status == "VERIFIED" and v.model_versions == {"backend": "fake"}


async def test_pilot_mode_sends_approvals_to_human(db, make_acts):
    storage = MemoryStorage()
    acts = make_acts(storage=storage, human_confirms_all=True)
    req = await seed(db, storage)
    env, vid, _, decision = await run_like_workflow(acts, req)
    assert decision["status"] == "NEEDS_REVIEW" and decision["ai_status"] == "VERIFIED"

    review = ReviewSignal("VERIFIED", "mod-1")
    await env.run(
        acts.record_decision, RecordInput(req, vid, "review", {"status": "VERIFIED"}, reviewer=review)
    )
    # retried activity is a no-op
    await env.run(
        acts.record_decision, RecordInput(req, vid, "review", {"status": "VERIFIED"}, reviewer=review)
    )
    async with db() as s:
        v = await s.get(Verification, (uuid.UUID(req.seller_id), uuid.UUID(vid)))
    assert v.status == "VERIFIED" and v.evidence["recorded"] == ["ai", "review"]


async def test_same_animal_relisted_by_another_seller_is_flagged(db, make_acts):
    storage, index = MemoryStorage(), MemoryIndex()
    acts = make_acts(storage=storage, index=index)

    first = await seed(db, storage)
    env, _, analysis, decision = await run_like_workflow(acts, first)
    await env.run(acts.index_identity, IndexInput(first, analysis.centroid))

    second = await seed(db, storage)  # FakeBackend puts everything in identity group "A"
    _, _, _, decision = await run_like_workflow(acts, second)
    assert decision["status"] == "NEEDS_REVIEW"
    assert any("another seller" in f for f in decision["flags"])


async def test_unreviewed_state_rule_and_no_kyc_go_to_review(db, make_acts):
    storage = MemoryStorage()
    acts = make_acts(storage=storage)
    req = await seed(db, storage, state="RJ", kyc="PENDING", reviewed_rule=False, species="buffalo")
    _, _, _, decision = await run_like_workflow(acts, req)
    assert decision["status"] == "NEEDS_REVIEW"
    assert "seller KYC is not complete" in decision["flags"]
    assert any("pending legal review" in f for f in decision["flags"])


async def test_blurry_photo_asks_for_retake(db, make_acts):
    storage = MemoryStorage()
    acts = make_acts(storage=storage)
    req = await seed(db, storage)
    key = f"{req.animal_id}/LEFT"
    blurred = cv2.GaussianBlur(sharp_image(1), (61, 61), 25)
    storage.objects[key] = cv2.imencode(".jpg", blurred)[1].tobytes()

    _, vid, analysis, decision = await run_like_workflow(acts, req)
    assert analysis.stopped_at == "quality"
    assert decision["status"] == "REUPLOAD"
    assert decision["reupload"][0]["view"] == "LEFT"
    assert "blurry" in decision["reupload"][0]["reason"]
