"""Local Storage adapter for filesystem storage testing.

This adapter provides a simple local filesystem-based storage
implementation for testing purposes.

Example:
    >>> from venomqa.adapters import LocalStorageAdapter
    >>> adapter = LocalStorageAdapter(base_path="/tmp/storage")
    >>> adapter.upload("bucket", "key.txt", b"content")
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from venomqa.ports.files import StorageObject, StoragePort


@dataclass
class LocalStorageConfig:
    """Configuration for Local Storage adapter."""

    base_path: str = "./storage"
    create_dirs: bool = True
    hash_key_paths: bool = False


class LocalStorageAdapter(StoragePort):
    """Adapter for local filesystem storage.

    This adapter implements the StoragePort interface using the
    local filesystem, useful for testing without external dependencies.

    Attributes:
        config: Configuration for storage.

    Example:
        >>> adapter = LocalStorageAdapter(base_path="/tmp/test-storage")
        >>> adapter.create_bucket("test")
        >>> adapter.upload("test", "file.txt", b"hello world")
        >>> data = adapter.download("test", "file.txt")
    """

    def __init__(
        self,
        base_path: str = "./storage",
        create_dirs: bool = True,
        hash_key_paths: bool = False,
    ) -> None:
        """Initialize the Local Storage adapter.

        Args:
            base_path: Base directory for storage.
            create_dirs: Whether to create directories automatically.
            hash_key_paths: Whether to hash keys for file paths.
        """
        self.config = LocalStorageConfig(
            base_path=base_path,
            create_dirs=create_dirs,
            hash_key_paths=hash_key_paths,
        )
        self._base_path = Path(base_path)
        if create_dirs:
            self._base_path.mkdir(parents=True, exist_ok=True)

    def _get_bucket_path(self, bucket: str) -> Path:
        """Get the path for a bucket."""
        return self._base_path / bucket

    def _get_key_path(self, bucket: str, key: str) -> Path:
        """Get the path for an object key."""
        bucket_path = self._get_bucket_path(bucket)
        if self.config.hash_key_paths:
            key_hash = hashlib.md5(key.encode()).hexdigest()[:2]
            return bucket_path / key_hash / key
        return bucket_path / key

    def _read_metadata(self, path: Path) -> dict[str, str]:
        """Read metadata file for an object."""
        meta_path = path.with_suffix(path.suffix + ".meta")
        if meta_path.exists():
            import json

            with open(meta_path) as f:
                return json.load(f)
        return {}

    def _write_metadata(self, path: Path, metadata: dict[str, str]) -> None:
        """Write metadata file for an object."""
        meta_path = path.with_suffix(path.suffix + ".meta")
        import json

        with open(meta_path, "w") as f:
            json.dump(metadata, f)

    def upload(
        self,
        bucket: str,
        key: str,
        data: BinaryIO | bytes | str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        """Upload an object.

        Args:
            bucket: Bucket/container name.
            key: Object key.
            data: Data to upload.
            content_type: Content type.
            metadata: Custom metadata.

        Returns:
            True if successful.
        """
        bucket_path = self._get_bucket_path(bucket)
        if self.config.create_dirs:
            bucket_path.mkdir(parents=True, exist_ok=True)

        key_path = self._get_key_path(bucket, key)
        key_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, str):
            data = data.encode("utf-8")

        if isinstance(data, bytes):
            with open(key_path, "wb") as f:
                f.write(data)
        else:
            with open(key_path, "wb") as f:
                shutil.copyfileobj(data, f)

        meta = metadata or {}
        if content_type:
            meta["content_type"] = content_type
        if meta:
            self._write_metadata(key_path, meta)

        return True

    def download(self, bucket: str, key: str) -> bytes | None:
        """Download an object.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            Object data or None if not found.
        """
        key_path = self._get_key_path(bucket, key)
        if not key_path.exists():
            return None
        return key_path.read_bytes()

    def delete(self, bucket: str, key: str) -> bool:
        """Delete an object.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            True if deleted, False if not found.
        """
        key_path = self._get_key_path(bucket, key)
        if not key_path.exists():
            return False

        key_path.unlink()
        meta_path = key_path.with_suffix(key_path.suffix + ".meta")
        if meta_path.exists():
            meta_path.unlink()
        return True

    def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            True if exists, False otherwise.
        """
        key_path = self._get_key_path(bucket, key)
        return key_path.exists()

    def get_object(self, bucket: str, key: str) -> StorageObject | None:
        """Get object metadata.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            Object metadata or None if not found.
        """
        key_path = self._get_key_path(bucket, key)
        if not key_path.exists():
            return None

        stat = key_path.stat()
        meta = self._read_metadata(key_path)

        return StorageObject(
            key=key,
            size=stat.st_size,
            content_type=meta.get("content_type", "application/octet-stream"),
            etag=hashlib.md5(key.encode()).hexdigest(),
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            metadata=meta,
        )

    def list_objects(
        self,
        bucket: str,
        prefix: str | None = None,
        limit: int | None = None,
    ) -> Iterator[StorageObject]:
        """List objects in a bucket.

        Args:
            bucket: Bucket/container name.
            prefix: Key prefix filter.
            limit: Maximum objects to return.

        Yields:
            Storage objects.
        """
        bucket_path = self._get_bucket_path(bucket)
        if not bucket_path.exists():
            return

        count = 0
        for path in bucket_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix == ".meta":
                continue

            key = str(path.relative_to(bucket_path))

            if prefix and not key.startswith(prefix):
                continue

            yield self.get_object(bucket, key)  # type: ignore
            count += 1
            if limit and count >= limit:
                return

    def create_bucket(self, bucket: str) -> bool:
        """Create a bucket.

        Args:
            bucket: Bucket name.

        Returns:
            True if successful.
        """
        bucket_path = self._get_bucket_path(bucket)
        bucket_path.mkdir(parents=True, exist_ok=True)
        return True

    def delete_bucket(self, bucket: str, force: bool = False) -> bool:
        """Delete a bucket.

        Args:
            bucket: Bucket name.
            force: Delete all objects first.

        Returns:
            True if successful.
        """
        bucket_path = self._get_bucket_path(bucket)
        if not bucket_path.exists():
            return False

        if force:
            shutil.rmtree(bucket_path)
            return True

        try:
            bucket_path.rmdir()
            return True
        except OSError:
            return False

    def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists.

        Args:
            bucket: Bucket name.

        Returns:
            True if exists, False otherwise.
        """
        return self._get_bucket_path(bucket).exists()

    def get_presigned_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
        method: str = "GET",
    ) -> str | None:
        """Get a presigned URL for an object.

        Note: This returns a file:// URL for local storage.

        Args:
            bucket: Bucket name.
            key: Object key.
            expires_in: URL expiration in seconds (ignored).
            method: HTTP method (ignored).

        Returns:
            File URL or None if not found.
        """
        key_path = self._get_key_path(bucket, key)
        if key_path.exists():
            return key_path.as_uri()
        return None

    def health_check(self) -> bool:
        """Check if the storage service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            return self._base_path.exists() and self._base_path.is_dir()
        except Exception:
            return False

    def copy(
        self,
        src_bucket: str,
        src_key: str,
        dst_bucket: str,
        dst_key: str,
    ) -> bool:
        """Copy an object.

        Args:
            src_bucket: Source bucket.
            src_key: Source key.
            dst_bucket: Destination bucket.
            dst_key: Destination key.

        Returns:
            True if successful.
        """
        src_path = self._get_key_path(src_bucket, src_key)
        if not src_path.exists():
            return False

        dst_path = self._get_key_path(dst_bucket, dst_key)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

        src_meta = src_path.with_suffix(src_path.suffix + ".meta")
        if src_meta.exists():
            shutil.copy2(src_meta, dst_path.with_suffix(dst_path.suffix + ".meta"))

        return True

    def move(
        self,
        src_bucket: str,
        src_key: str,
        dst_bucket: str,
        dst_key: str,
    ) -> bool:
        """Move an object.

        Args:
            src_bucket: Source bucket.
            src_key: Source key.
            dst_bucket: Destination bucket.
            dst_key: Destination key.

        Returns:
            True if successful.
        """
        if self.copy(src_bucket, src_key, dst_bucket, dst_key):
            return self.delete(src_bucket, src_key)
        return False

    def clear_bucket(self, bucket: str) -> int:
        """Clear all objects from a bucket.

        Args:
            bucket: Bucket name.

        Returns:
            Number of objects deleted.
        """
        bucket_path = self._get_bucket_path(bucket)
        if not bucket_path.exists():
            return 0

        count = 0
        for path in list(bucket_path.rglob("*")):
            if path.is_file() and not path.suffix == ".meta":
                path.unlink()
                count += 1

        return count

    def get_bucket_size(self, bucket: str) -> int:
        """Get the total size of a bucket.

        Args:
            bucket: Bucket name.

        Returns:
            Total size in bytes.
        """
        total = 0
        for obj in self.list_objects(bucket):
            total += obj.size
        return total

    def list_buckets(self) -> list[str]:
        """List all buckets.

        Returns:
            List of bucket names.
        """
        if not self._base_path.exists():
            return []
        return [p.name for p in self._base_path.iterdir() if p.is_dir()]
