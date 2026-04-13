from __future__ import annotations

import asyncio

import boto3

from apps.api.config import settings


class S3Client:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=str(settings.s3_endpoint_url),
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            region_name=settings.s3_region,
            use_ssl=settings.s3_secure,
        )

    async def upload_file(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        def _upload() -> str:
            self._client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
            return f"s3://{bucket}/{key}"

        return await asyncio.to_thread(_upload)

    async def download_file(self, bucket: str, key: str) -> bytes:
        def _download() -> bytes:
            response = self._client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_download)

    async def get_presigned_url(self, bucket: str, key: str, expires_in: int) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
