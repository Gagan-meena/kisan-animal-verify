from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KISAN_", env_file=".env", extra="ignore")

    env: Literal["local", "test", "staging", "prod"] = "local"

    database_url: str = "postgresql+asyncpg://kisan:kisan@localhost:5432/kisan"
    kafka_bootstrap: str = "localhost:9092"
    temporal_host: str = "localhost:7233"
    temporal_task_queue: str = "verify-animal"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "animal_identity"
    qdrant_shards:int=1 
    qdrant_replicas:int=1

    s3_endpoint: str | None = None
    s3_public_endpoint: str | None = None
    s3_bucket: str = "kisan-media"
    s3_region: str = "ap-south-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    presign_ttl_seconds: int = 900

    # Rule 6: pilot gate
    enabled_states: Annotated[frozenset[str], NoDecode] = frozenset({"RJ"})
    # Pilot: a human confirms every AI approval until precision is proven
    pilot_human_confirms_all: bool = True
    review_sla_hours: float = 4.0

    # Rule 3: inference
    inference_backend: Literal["fake", "local", "triton"] = "fake"
    triton_url: str = "localhost:8001"

    jwt_secret: str = "change-me"
    min_app_version: str = "1.0.0"

    @field_validator("enabled_states", mode="before")
    @classmethod
    def _split_states(cls, v):
        if isinstance(v, str):
            return frozenset(s.strip().upper() for s in v.split(",") if s.strip())
        return frozenset(s.upper() for s in v)


@lru_cache
def get_settings() -> Settings:
    return Settings()
