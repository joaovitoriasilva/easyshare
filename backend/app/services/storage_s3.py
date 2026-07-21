"""S3-compatible object-storage backend.

Imported lazily by :func:`app.services.storage.build_storage` only when
``EASYSHARE_STORAGE_URI`` uses the ``s3://`` scheme, so a default (local)
deployment never imports boto3 (the optional ``s3`` extra).

Downloads are served by redirecting the client to a short-lived presigned GET
URL rather than proxying object bytes through this process, so file traffic is
offloaded to the object store / CDN. The presigned URL forces an
``attachment`` Content-Disposition and the stored content type, preserving the
same "always download, never render inline" behaviour as the local backend.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, BinaryIO, cast
from urllib.parse import parse_qs, urlparse

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi.responses import RedirectResponse
from starlette import status
from starlette.responses import Response

from app.services.storage import (
    FileTooLargeError,
    StorageBackend,
    content_disposition_attachment,
)

# HeadObject error codes meaning "the object is not there" (as opposed to auth,
# region, throttling or 5xx failures, which must surface rather than masquerade
# as a missing object). "404" is what S3 returns for HeadObject; the aliases
# cover S3-compatible providers (MinIO, R2, Ceph).
_MISSING_OBJECT_CODES = frozenset({"404", "NoSuchKey", "NotFound"})

# Default presigned-URL lifetime (seconds). Long enough for a browser to follow
# the redirect and start the transfer, short enough to limit link sharing.
_DEFAULT_URL_EXPIRY = 900


def _measure(source: BinaryIO) -> int:
    """Return the byte length of a seekable stream, leaving it rewound.

    FastAPI has already streamed the whole upload into ``UploadFile.file``
    (a spooled temp file) before the route runs, so the size is available
    without reading the content again.
    """
    source.seek(0, os.SEEK_END)
    size = source.tell()
    source.seek(0)
    return size


class S3StorageBackend(StorageBackend):
    """Stores objects in an S3-compatible bucket under an optional key prefix."""

    def __init__(
        self, client: Any, bucket: str, prefix: str = "", *, url_expiry: int = _DEFAULT_URL_EXPIRY
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._url_expiry = url_expiry

    @classmethod
    def from_uri(cls, uri: str) -> S3StorageBackend:
        """Build a backend from ``s3://bucket/prefix?region=…&endpoint_url=…``.

        ``region``, ``endpoint_url`` (for MinIO / R2 / Ceph) and ``url_expiry``
        (presigned-URL seconds) are optional query parameters.

        Raises:
            ValueError: When the URI has no bucket.
        """
        parsed = urlparse(uri)
        bucket = parsed.netloc
        if not bucket:
            raise ValueError(f"EASYSHARE_STORAGE_URI is missing a bucket: {uri!r}")
        params = parse_qs(parsed.query)
        client = boto3.client(
            "s3",
            region_name=params.get("region", [None])[0],
            endpoint_url=params.get("endpoint_url", [None])[0],
            config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        )
        expiry = int(params.get("url_expiry", [str(_DEFAULT_URL_EXPIRY)])[0])
        return cls(client, bucket, parsed.path, url_expiry=expiry)

    def _object_key(self, storage_key: str) -> str:
        return "/".join(part for part in (self._prefix, storage_key) if part)

    def save(
        self, storage_key: str, source: BinaryIO, max_bytes: int | None = None
    ) -> int:
        size = _measure(source)
        if max_bytes is not None and size > max_bytes:
            raise FileTooLargeError(max_bytes)
        # use_threads=False keeps the (already fully-received) upload on the
        # calling worker thread rather than spawning extra transfer threads.
        self._client.upload_fileobj(
            source,
            self._bucket,
            self._object_key(storage_key),
            Config=TransferConfig(use_threads=False),
        )
        return size

    def open_stream(self, storage_key: str) -> BinaryIO:
        obj = self._client.get_object(
            Bucket=self._bucket, Key=self._object_key(storage_key)
        )
        return cast("BinaryIO", obj["Body"])

    def delete(self, storage_key: str) -> None:
        self._client.delete_object(
            Bucket=self._bucket, Key=self._object_key(storage_key)
        )

    def exists(self, storage_key: str) -> bool:
        try:
            self._client.head_object(
                Bucket=self._bucket, Key=self._object_key(storage_key)
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _MISSING_OBJECT_CODES:
                return False
            raise
        return True

    def iter_objects(self) -> Iterator[tuple[str, float]]:
        """Yield ``(storage_key, modified_epoch)`` for every object under the prefix.

        Pages through ``list_objects_v2`` and strips the configured key prefix so
        the yielded key matches what is stored in ``package_files.storage_key``.
        ``modified_epoch`` comes from each object's ``LastModified`` timestamp.
        """
        prefix = f"{self._prefix}/" if self._prefix else ""
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                storage_key = key[len(prefix):] if prefix else key
                if storage_key:
                    yield storage_key, obj["LastModified"].timestamp()

    def check_writable(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError) as error:
            # Translate to OSError so the readiness probe's ``except OSError``
            # treats an unreachable bucket the same as an unwritable volume.
            raise OSError(f"S3 bucket is not reachable: {error}") from error

    def download_response(
        self, storage_key: str, *, filename: str, content_type: str
    ) -> Response:
        url = self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": self._object_key(storage_key),
                "ResponseContentDisposition": content_disposition_attachment(
                    filename
                ),
                "ResponseContentType": content_type,
            },
            ExpiresIn=self._url_expiry,
        )
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
