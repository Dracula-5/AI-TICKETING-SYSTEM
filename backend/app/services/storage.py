"""
Attachment storage and upload validation.

Validation is allow-list based: extension AND leading "magic" bytes must agree
for binary formats, text formats must decode as UTF-8, and anything executable
is rejected. Files are stored under random keys (never the user's filename),
served only through an authenticated endpoint with `Content-Disposition:
attachment` and `nosniff`, so an upload cannot be rendered as HTML/JS in the
app's origin.

Backends: LocalStorage (development / single VM with a mounted volume) and
S3Storage (any S3-compatible object store, for multi-host deployments), chosen
by STORAGE_BACKEND.
"""

import hashlib
import os
import re
import secrets
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings

# extension -> (content type, magic-byte prefixes or None for UTF-8 text)
ALLOWED_TYPES: dict[str, tuple[str, tuple[bytes, ...] | None]] = {
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", (b"RIFF",)),
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK\x03\x04",)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK\x03\x04",)),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", (b"PK\x03\x04",)),
    ".txt": ("text/plain", None),
    ".log": ("text/plain", None),
    ".csv": ("text/csv", None),
    ".json": ("application/json", None),
    ".md": ("text/markdown", None),
}


class UploadRejected(Exception):
    pass


def sanitize_filename(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return (base or "file")[:200]


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Returns (safe filename, content type) or raises UploadRejected."""
    safe = sanitize_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise UploadRejected(f"File type '{ext or 'none'}' is not allowed")
    if not data:
        raise UploadRejected("File is empty")
    if len(data) > settings.attachment_max_bytes:
        raise UploadRejected(f"File exceeds the {settings.attachment_max_bytes // (1024 * 1024)} MB limit")
    content_type, magic = ALLOWED_TYPES[ext]
    if magic is None:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadRejected("Text file is not valid UTF-8") from None
        if b"\x00" in data:
            raise UploadRejected("Text file contains binary data")
    elif not any(data.startswith(m) for m in magic):
        raise UploadRejected(f"File content does not match its '{ext}' extension")
    if ext == ".webp" and data[8:12] != b"WEBP":
        raise UploadRejected("File content does not match its '.webp' extension")
    return safe, content_type


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_KEY_RE = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+")


def _new_key(tenant_id: int) -> str:
    return f"t{tenant_id}/{secrets.token_urlsafe(24)}"


def _check_key(key: str) -> str:
    # Keys are generated server-side; still refuse anything path-like.
    if not _KEY_RE.fullmatch(key):
        raise ValueError("invalid storage key")
    return key


class Storage(Protocol):
    def save(self, tenant_id: int, data: bytes) -> str: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    """Directory / mounted volume. Right for a single VM (backed up with the VM)."""

    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _check_key(key)

    def save(self, tenant_id: int, data: bytes) -> str:
        key = _new_key(tenant_id)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """Any S3-compatible object store (AWS S3, Cloudflare R2, MinIO). Objects
    stay private; the API streams them after its own authorization check, so no
    presigned URLs ever leave the server."""

    def __init__(self, bucket: str, client: Any = None):
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                region_name=settings.s3_region or None,
                aws_access_key_id=settings.s3_access_key_id or None,
                aws_secret_access_key=settings.s3_secret_access_key or None,
            )
        self.bucket = bucket
        self.client = client

    def save(self, tenant_id: int, data: bytes) -> str:
        key = _new_key(tenant_id)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        return key

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=_check_key(key))["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_check_key(key))


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if settings.storage_backend == "s3":
        if _storage is None:
            _storage = S3Storage(settings.s3_bucket)
        return _storage
    return LocalStorage(settings.attachment_dir)
