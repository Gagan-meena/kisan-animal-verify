"""Request dependencies: identity, pilot gate (rule 6), app version gate (rule 1).

The API gateway validates the user's JWT and forwards trusted claims as headers
(``X-Seller-Id``, ``X-Reviewer-Id``). Services must only be reachable through the gateway.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kisan.config import Settings, get_settings
from kisan.db.models import Seller
from kisan.db.session import get_session


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.split("."))
    except ValueError:
        return (0,)


async def require_app_version(
    x_app_version: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    # Old apps run an older on-device model; their pre-checks are not trusted.
    if x_app_version is None or _version_tuple(x_app_version) < _version_tuple(settings.min_app_version):
        raise HTTPException(status.HTTP_426_UPGRADE_REQUIRED, "Please update the Kisan app to continue.")


async def current_seller(
    x_seller_id: uuid.UUID = Header(...), session: AsyncSession = Depends(get_session)
) -> Seller:
    seller = await session.get(Seller, x_seller_id)
    if seller is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown seller.")
    return seller


async def pilot_gate(
    seller: Seller = Depends(current_seller), settings: Settings = Depends(get_settings)
) -> Seller:
    """Rule 6: only sellers in enabled states can create verified listings."""
    if seller.state.upper() not in settings.enabled_states:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Verified listings are not available in your state yet. We will notify you when they are.",
        )
    return seller


async def current_reviewer(x_reviewer_id: str = Header(...)) -> str:
    return x_reviewer_id
