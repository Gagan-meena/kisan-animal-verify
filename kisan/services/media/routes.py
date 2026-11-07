"""Listing + media service: create listings, hand out upload URLs, submit for verification."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select,and_
from sqlalchemy.ext.asyncio import AsyncSession

from kisan import events
from kisan.config import Settings, get_settings
from kisan.db.models import Animal, AnimalImage, Listing, ListingStatus, ListingSummary, Seller, Verification, View
from kisan.db.session import get_session
from kisan.rules.policy import (
    MAX_IMAGES_PER_ANIMAL,
    PHOTO_CONTENT_TYPES,
    VIDEO_CONTENT_TYPES,
    required_views,
)
from kisan.services.deps import current_seller, pilot_gate, require_app_version
from kisan.services.schemas import ListingIn, ListingOut, MediaIn, MediaOut, SubmitOut
from kisan.storage import Storage, get_storage, media_key

router = APIRouter(prefix="/v1", tags=["listings"], dependencies=[Depends(require_app_version)])
EXT = {"image/webp": "webp", "image/jpeg": "jpg", "video/mp4": "mp4"}


async def _animal(session: AsyncSession, seller: Seller, animal_id: uuid.UUID) -> Animal:
    animal = await session.get(Animal, (seller.id, animal_id))
    if animal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found.")
    return animal


async def _listing(session: AsyncSession, animal: Animal) -> Listing:
    return await session.get(Listing, (animal.seller_id, animal.listing_id))


@router.post("/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
async def create_listing(
    body: ListingIn, seller: Seller = Depends(pilot_gate), session: AsyncSession = Depends(get_session)
):
    listing = Listing(
        seller_id=seller.id, id=uuid.uuid4(), state=seller.state, title=body.title, price_inr=body.price_inr
    )
    animal = Animal(seller_id=seller.id, id=uuid.uuid4(), listing_id=listing.id, **body.animal.model_dump())
    session.add_all([listing, animal])
    await session.commit()
    return ListingOut(
        listing_id=listing.id,
        animal_id=animal.id,
        status=listing.status,
        required_views=sorted(str(v) for v in required_views(animal.species)),
    )

@router.get("/listings",response_model=list[ListingSummary])
async def list_my_listing(
    seller: Seller = Depends(current_seller),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Listing, Animal)
        .join(Animal, and_(Animal.seller_id == Listing.seller_id,
                           Animal.listing_id == Listing.id))
        .where(Listing.seller_id == seller.id)
        .order_by(Listing.created_at.desc())
    )
   
    rows = (await session.execute(stmt)).all()
    return [ListingSummary(listing_id=listing.id,
                        animal_id=animal.id,
                        title=listing.title,
                        species=animal.species,
                        price_inr=listing.price_inr,
                        status=listing.status,
                        created_at=listing.created_at
                    ) for listing, animal in rows]
    

@router.post("/animals/{animal_id}/media", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def request_upload(
    animal_id: uuid.UUID,
    body: MediaIn,
    seller: Seller = Depends(pilot_gate),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    animal = await _animal(session, seller, animal_id)
    listing = await _listing(session, animal)
    if listing.status == ListingStatus.VERIFYING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This listing is being verified; wait for the result.")

    allowed = VIDEO_CONTENT_TYPES if body.view == View.VIDEO else PHOTO_CONTENT_TYPES
    if body.content_type not in allowed:
        raise HTTPException(422, f"{body.view} must be one of: {', '.join(sorted(allowed))}")
    if body.capture_meta.source != "in_app_camera":
        raise HTTPException(422, "Please take the photo with the in-app camera.")

    count = await session.scalar(
        select(func.count())
        .select_from(AnimalImage)
        .where(AnimalImage.seller_id == seller.id, AnimalImage.animal_id == animal.id)
    )
    if count >= MAX_IMAGES_PER_ANIMAL * 3:  # allow retakes, but bound abuse
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many uploads for this animal.")

    image = AnimalImage(
        seller_id=seller.id,
        id=uuid.uuid4(),
        animal_id=animal.id,
        view=body.view,
        content_type=body.content_type,
        capture_meta=body.capture_meta.model_dump(),
        storage_key="",
    )
    image.storage_key = media_key(str(seller.id), str(animal.id), str(image.id), EXT[body.content_type])
    session.add(image)
    await session.commit()
    return MediaOut(
        image_id=image.id,
        upload_url=storage.presign_put(image.storage_key, body.content_type),
        upload_headers={"Content-Type": body.content_type},
        expires_in=settings.presign_ttl_seconds,
    )


@router.post("/animals/{animal_id}/media/{image_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_upload(
    animal_id: uuid.UUID,
    image_id: uuid.UUID,
    seller: Seller = Depends(pilot_gate),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    image = await session.get(AnimalImage, (seller.id, image_id))
    if image is None or image.animal_id != animal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found.")
    if image.uploaded:
        return
    if not storage.exists(image.storage_key):
        raise HTTPException(status.HTTP_409_CONFLICT, "File has not finished uploading.")
    image.uploaded = True
    events.add_event(
        session,
        seller_id=seller.id,
        topic=events.MEDIA_UPLOADED,
        key=str(animal_id),
        payload={
            "seller_id": str(seller.id),
            "animal_id": str(animal_id),
            "image_id": str(image.id),
            "view": image.view,
            "storage_key": image.storage_key,
        },
    )
    await session.commit()


@router.post("/animals/{animal_id}/submit", response_model=SubmitOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_for_verification(
    animal_id: uuid.UUID, seller: Seller = Depends(pilot_gate), session: AsyncSession = Depends(get_session)
):
    animal = await _animal(session, seller, animal_id)
    listing = await _listing(session, animal)
    if listing.status in (ListingStatus.VERIFYING, ListingStatus.LIVE, ListingStatus.SOLD):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Listing is already {listing.status.lower()}.")

    if listing.status ==  ListingStatus.BLOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This listing is not allowed and cannot be submitted again."  )

    uploaded_views = set(
        (
            await session.scalars(
                select(AnimalImage.view).where(
                    AnimalImage.seller_id == seller.id,
                    AnimalImage.animal_id == animal.id,
                    AnimalImage.uploaded.is_(True),
                )
            )
        ).all()
    )
    missing = sorted(str(v) for v in required_views(animal.species) - uploaded_views)
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": "Some photos are missing.", "missing": missing}
        )

    attempt = 1 + (
        await session.scalar(
            select(func.count())
            .select_from(Verification)
            .where(Verification.seller_id == seller.id, Verification.animal_id == animal.id)
        )
    )
    listing.status = ListingStatus.VERIFYING
    events.add_event(
        session,
        seller_id=seller.id,
        topic=events.VERIFY_REQUESTED,
        key=str(animal.id),
        payload={
            "seller_id": str(seller.id),
            "animal_id": str(animal.id),
            "listing_id": str(listing.id),
            "attempt": attempt,
        },
    )
    await session.commit()
    return SubmitOut(status=listing.status, attempt=attempt)
