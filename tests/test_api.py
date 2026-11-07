# type: ignore
import uuid

from sqlalchemy import select

from kisan.db.models import Decision, Outbox, Verification,ListingStatus,Listing
from kisan.rules.policy import required_views

APP = {"X-App-Version": "1.2.0"}
META = {
    "source": "in_app_camera",
    "captured_at": "2026-10-09T08:00:00+05:30",
    "app_version": "1.2.0",
    "device_id": "dev-1",
    "sig": "abc",
}
LISTING = {
    "title": "Gir cow, 2nd lactation",
    "price_inr": 65000,
    "animal": {"species": "cow", "breed": "Gir", "sex": "female", "age_months": 48, "tag_id": "123456789012"},
}


async def new_seller(client, state="RJ", kyc="VERIFIED"):
    r = await client.post("/dev/sellers", json={"state": state, "kyc_status": kyc})
    return {**APP, "X-Seller-Id": r.json()["seller_id"]}

async def new_listing(client, h, body=LISTING):
    r = await client.post("/v1/listings", headers=h, json=body)
    assert r.status_code == 201
    return r.json()


async def upload(client, storage, h, animal_id, view):
    ctype = "video/mp4" if view == "VIDEO" else "image/webp"
    r = await client.post(
        f"/v1/animals/{animal_id}/media",
        headers=h,
        json={"view": view, "content_type": ctype, "capture_meta": META},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    storage.objects[body["upload_url"].removeprefix("memory://")] = b"bytes"
    r = await client.post(f"/v1/animals/{animal_id}/media/{body['image_id']}/complete", headers=h)
    assert r.status_code == 204, r.text
    return body["image_id"]


async def test_outdated_app_is_refused(client):
    h = await new_seller(client)
    r = await client.post("/v1/listings", headers={**h, "X-App-Version": "0.9.0"}, json=LISTING)
    assert r.status_code == 426


async def test_pilot_gate_blocks_other_states(client):
    h = await new_seller(client, state="MH")
    r = await client.post("/v1/listings", headers=h, json=LISTING)
    assert r.status_code == 403
    assert "not available in your state" in r.json()["detail"]


async def test_gallery_upload_refused(client):
    h = await new_seller(client)
    animal_id = (await client.post("/v1/listings", headers=h, json=LISTING)).json()["animal_id"]
    r = await client.post(
        f"/v1/animals/{animal_id}/media",
        headers=h,
        json={"view": "FRONT", "content_type": "image/jpeg", "capture_meta": {**META, "source": "gallery"}},
    )
    assert r.status_code == 422


async def test_wrong_content_type_for_video(client):
    h = await new_seller(client)
    animal_id = (await client.post("/v1/listings", headers=h, json=LISTING)).json()["animal_id"]
    r = await client.post(
        f"/v1/animals/{animal_id}/media",
        headers=h,
        json={"view": "VIDEO", "content_type": "image/jpeg", "capture_meta": META},
    )
    assert r.status_code == 422


async def test_complete_before_upload_is_conflict(client):
    h = await new_seller(client)
    animal_id = (await client.post("/v1/listings", headers=h, json=LISTING)).json()["animal_id"]
    r = await client.post(
        f"/v1/animals/{animal_id}/media",
        headers=h,
        json={"view": "FRONT", "content_type": "image/webp", "capture_meta": META},
    )
    r = await client.post(f"/v1/animals/{animal_id}/media/{r.json()['image_id']}/complete", headers=h)
    assert r.status_code == 409


async def test_other_seller_cannot_touch_animal(client):
    h1, h2 = await new_seller(client), await new_seller(client)
    animal_id = (await client.post("/v1/listings", headers=h1, json=LISTING)).json()["animal_id"]
    r = await client.post(f"/v1/animals/{animal_id}/submit", headers=h2)
    assert r.status_code == 404


async def test_full_submission_flow(client, storage, db):
    h = await new_seller(client)
    r = await client.post("/v1/listings", headers=h, json=LISTING)
    assert r.status_code == 201
    animal_id = r.json()["animal_id"]
    assert set(r.json()["required_views"]) == {str(v) for v in required_views("cow")}

    await upload(client, storage, h, animal_id, "FRONT")
    r = await client.post(f"/v1/animals/{animal_id}/submit", headers=h)
    assert r.status_code == 409
    assert "LEFT" in r.json()["detail"]["missing"]

    for v in sorted(required_views("cow") - {"FRONT"}):
        await upload(client, storage, h, animal_id, str(v))
    r = await client.post(f"/v1/animals/{animal_id}/submit", headers=h)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "VERIFYING", "attempt": 1}

    # second submit while verifying is refused
    assert (await client.post(f"/v1/animals/{animal_id}/submit", headers=h)).status_code == 409

    async with db() as s:
        topics = [o.topic for o in (await s.scalars(select(Outbox))).all()]
    assert topics.count("media.uploaded") == len(required_views("cow"))
    assert topics.count("verify.requested") == 1

    r = await client.get(f"/v1/animals/{animal_id}/verification", headers=h)
    assert r.json()["status"] == "PENDING"


async def test_review_flow_signals_workflow(client, db, gateway):
    h = await new_seller(client)
    seller_id = h["X-Seller-Id"]
    animal_id = (await client.post("/v1/listings", headers=h, json=LISTING)).json()["animal_id"]
    async with db() as s:
        s.add(
            Verification(
                seller_id=uuid.UUID(seller_id),
                animal_id=uuid.UUID(animal_id),
                workflow_id="verify-x-1",
                status=Decision.NEEDS_REVIEW,
                score=78.0,
                flags=["RIGHT photo may show a different animal"],
            )
        )
        await s.commit()

    rv = {"X-Reviewer-Id": "mod-7"}
    queue = (await client.get("/v1/review/queue", headers=rv)).json()
    assert [q["animal_id"] for q in queue] == [animal_id]

    # seller never sees internal fraud flags
    seller_view = (await client.get(f"/v1/animals/{animal_id}/verification", headers=h)).json()
    assert seller_view["status"] == "NEEDS_REVIEW" and "different animal" not in str(seller_view)

    r = await client.post(
        f"/v1/review/{seller_id}/{animal_id}",
        headers=rv,
        json={"decision": "VERIFIED", "labels": {"same_animal": True}},
    )
    assert r.status_code == 202
    assert gateway.signals == [("verify-x-1", {"decision": "VERIFIED", "reviewer_id": "mod-7", "reason": ""})]

async def test_list_listings_newest_first(client):
    h = await new_seller(client)
    first = await new_listing(client, h)
    second = await new_listing(client, h)

    r = await client.get("/v1/listings", headers=h)

    assert r.status_code == 200
    ids = [x["listing_id"] for x in r.json()]
    assert ids == [second["listing_id"], first["listing_id"]]

async def test_list_listings_only_own(client):
    h1 = await new_seller(client)
    h2 = await new_seller(client)
    await new_listing(client, h1)
    await new_listing(client, h1)

    r = await client.get("/v1/listings", headers=h2)
    r1 = await client.get("/v1/listings", headers=h1)
    
    assert len(r1.json()) == 2

    assert r.status_code == 200
    ids = [x["listing_id"] for x in r.json()]
    assert ids == []

async def test_list_listings_empty(client):
    h = await new_seller(client=client)
    
    r = await client.get("/v1/listings", headers=h)

    assert r.status_code == 200
    ids = [x["listing_id"] for x in r.json()]
    assert ids == []

async def test_submit_blocked_listing_409(client,db):
    h =  await new_seller(client)
    listing = await new_listing(client,h)
    key  = (uuid.UUID(h["X-Seller-Id"]),uuid.UUID(listing["listing_id"]))

    async with db() as s:
        row  = await s.get(Listing,key)
        row.status = ListingStatus.BLOCKED

        await s.commit()

    r = await client.post(f"/v1/animals/{listing['animal_id']}/submit", headers=h)

    assert r.status_code == 409
    assert "not allowed" in r.json()["detail"]

    async with db() as s:
        assert (await s.get(Listing, key)).status == ListingStatus.BLOCKED




