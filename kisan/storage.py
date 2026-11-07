"""Object storage (S3 in ap-south-1; MinIO locally). Photos never pass through API pods."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from kisan.config import Settings, get_settings


class Storage(Protocol):
    def presign_put(self, key: str, content_type: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def get(self, key: str) -> bytes: ...


class S3Storage:
    def __init__(self, s: Settings):
        import boto3
        from botocore.config import Config

        common = dict(
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "adaptive"}),
        )
        self.bucket = s.s3_bucket
        self.ttl = s.presign_ttl_seconds
        self._s3 = boto3.client("s3", endpoint_url=s.s3_endpoint, **common)
        # Presigned URLs must use the host the phone can reach.
        self._signer = boto3.client("s3", endpoint_url=s.s3_public_endpoint or s.s3_endpoint, **common)

    def presign_put(self, key: str, content_type: str) -> str:
        return self._signer.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self.ttl,
        )

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()


class MemoryStorage:
    """For tests and offline demos."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def presign_put(self, key: str, content_type: str) -> str:
        return f"memory://{key}"

    def exists(self, key: str) -> bool:
        return key in self.objects

    def get(self, key: str) -> bytes:
        return self.objects[key]


def media_key(seller_id: str, animal_id: str, image_id: str, ext: str) -> str:
    # Prefix by seller so lifecycle rules and deletion requests (DPDP) are per seller.
    return f"sellers/{seller_id}/animals/{animal_id}/{image_id}.{ext}"


@lru_cache
def get_storage() -> Storage:
    return S3Storage(get_settings())
