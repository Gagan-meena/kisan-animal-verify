import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update(
    KISAN_ENV="test",
    KISAN_DATABASE_URL=f"sqlite+aiosqlite:///{_db}",
    KISAN_ENABLED_STATES="RJ",
    KISAN_INFERENCE_BACKEND="fake",
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from kisan.db.models import Base  # noqa: E402
from kisan.db.session import get_engine, get_sessionmaker  # noqa: E402
from kisan.storage import MemoryStorage, get_storage  # noqa: E402


class FakeGateway:
    def __init__(self):
        self.signals: list[tuple[str, dict]] = []

    async def signal_review(self, workflow_id, decision):
        self.signals.append((workflow_id, decision))


@pytest.fixture
async def db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield get_sessionmaker()


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
async def client(db, storage, gateway):
    from kisan.services.api import app
    from kisan.services.verification.gateway import get_gateway

    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
