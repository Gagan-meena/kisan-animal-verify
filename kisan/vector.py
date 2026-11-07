"""Qdrant identity index (rule 4): one centroid vector per approved animal."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from kisan.config import get_settings
from kisan.ml.stages.fraud import DuplicateHit


class IdentityIndex(Protocol):
    def search(
        self, vector: list[float], *, species: str, exclude_animal_id: str, limit: int = 5
    ) -> list[DuplicateHit]: ...
    def upsert(self, animal_id: str, vector: list[float], payload: dict) -> None: ...
    def set_status(self, animal_id: str, status: str) -> None: ...


class QdrantIndex:
    def __init__(self, url: str, collection: str):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=url, timeout=10)
        self.collection = collection

    def ensure_collection(self, dim: int, shards: int = 6, replicas: int = 2) -> None:
        from qdrant_client import models as m

        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config=m.VectorParams(size=dim, distance=m.Distance.COSINE, on_disk=True),
            shard_number=shards,
            replication_factor=replicas,
            quantization_config=m.ScalarQuantization(
                scalar=m.ScalarQuantizationConfig(type=m.ScalarType.INT8, always_ram=True)
            ),
        )
        for field in ("species", "status", "state", "seller_id"):
            self.client.create_payload_index(self.collection, field, m.PayloadSchemaType.KEYWORD)

    def search(self, vector, *, species, exclude_animal_id, limit=5):
        from qdrant_client import models as m

        res = self.client.query_points(
            self.collection,
            query=vector,
            limit=limit,
            query_filter=m.Filter(
                must=[
                    m.FieldCondition(key="species", match=m.MatchValue(value=species)),
                    m.FieldCondition(key="status", match=m.MatchValue(value="active")),
                ],
                must_not=[m.HasIdCondition(has_id=[exclude_animal_id])],
            ),
            search_params=m.SearchParams(quantization=m.QuantizationSearchParams(rescore=True)),
            with_payload=True,
        ).points
        return [
            DuplicateHit(
                animal_id=str(p.id),
                listing_id=p.payload.get("listing_id"),
                seller_id=p.payload.get("seller_id"),
                sim=float(p.score),
            )
            for p in res
        ]

    def upsert(self, animal_id, vector, payload):
        from qdrant_client import models as m

        self.ensure_collection(len(vector))
        self.client.upsert(self.collection, [m.PointStruct(id=animal_id, vector=vector, payload=payload)])

    def set_status(self, animal_id, status):
        self.client.set_payload(self.collection, {"status": status}, points=[animal_id])


class MemoryIndex:
    def __init__(self):
        self.points: dict[str, tuple[list[float], dict]] = {}

    def search(self, vector, *, species, exclude_animal_id, limit=5):
        import numpy as np

        q = np.asarray(vector)
        hits = [
            DuplicateHit(aid, p.get("listing_id"), p.get("seller_id"), float(np.dot(q, np.asarray(v))))
            for aid, (v, p) in self.points.items()
            if aid != exclude_animal_id and p.get("species") == species and p.get("status") == "active"
        ]
        return sorted(hits, key=lambda h: -h.sim)[:limit]

    def upsert(self, animal_id, vector, payload):
        self.points[animal_id] = (vector, payload)

    def set_status(self, animal_id, status):
        if animal_id in self.points:
            self.points[animal_id][1]["status"] = status


@lru_cache
def get_index() -> IdentityIndex:
    s = get_settings()
    return QdrantIndex(s.qdrant_url, s.qdrant_collection)
