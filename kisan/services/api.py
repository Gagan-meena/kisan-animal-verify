"""Public API process. In production the listing/media and verification routers can run as
separate Deployments from this same image; locally they share one process."""

import uuid

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kisan.config import get_settings
from kisan.db.models import Seller
from kisan.db.session import get_session
from kisan.services.media.routes import router as media_router
from kisan.services.verification.routes import review_router, seller_router

app = FastAPI(title="Kisan Verification API", version="0.1.0")
app.include_router(media_router)
app.include_router(seller_router)
app.include_router(review_router)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


if get_settings().env in ("local", "test"):

    class DevSellerIn(BaseModel):
        state: str
        kyc_status: str = "VERIFIED"

    @app.post("/dev/sellers", tags=["dev"])
    async def dev_create_seller(body: DevSellerIn, session: AsyncSession = Depends(get_session)):
        """Local only: create a seller (production sellers come from the identity service)."""
        seller = Seller(id=uuid.uuid4(), state=body.state.upper(), kyc_status=body.kyc_status)
        session.add(seller)
        await session.commit()
        return {"seller_id": str(seller.id)}
