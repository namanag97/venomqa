"""Mock Storage adapter for testing.

This adapter provides an in-memory object storage mock for testing
bucket/object operations without external dependencies.

Example:
    >>> from venomqa.adapters.storage import MockStorageAdapter, LocalFileAdapter
    >>> storage = MockStorageAdapter()
    >>> storage.create_bucket("my-bucket")
    >>> storage.put("my-bucket", "file.txt", b"content")
    >>> content = storage.get_content("my-bucket", "file.txt")
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, cast

if TYPE_CHECKING:
    pass


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class BucketNotFoundError(StorageError):
    """Raised when a bucket is not found."""

    pass


class ObjectNotFoundError(StorageError):
    """Raised when an object is not found."""

    pass


@dataclass
class StorageObject:
    """Represents a stored object.

    Attributes:
        key: Object key/path within the bucket.
        content: Binary content of the object.
        bucket: Bucket name.
        content_type: MIME type of the content.
        metadata: Custom metadata key-value pairs.
        etag: Entity tag (MD5 hash of content).
        size: Size in bytes.
        last_modified: Last modification timestamp.
    """

    key: str
    content: bytes
    bucket: str
    content_type: str = "application/octet-stream"
    metadata: dict[str, str] = field(default_factory=dict)
    etag: str = ""
    size: int = 0
    last_modified: datetime = field(default_factory=datetime.now)


@dataclass
class FileInfo:
    """File information for local filesystem.

    Attributes:
        name: File name.
        path: Full file path.
        size: Size in bytes.
        modified_time: Last modification timestamp.
        is_dir: Whether this is a directory.
    """

    name: str
    path: str
    size: int
    modified_time: datetime
    is_dir: bool = False


class MockStorageAdapter:
    """In-memory mock storage adapter for testing bucket/object operations.

    This adapter provides a fully functional in-memory object storage system
    for testing. It mimics S3-like bucket/object semantics.

    Example:
        >>> storage = MockStorageAdapter()
        >>> storage.create_bucket("test")
        >>> storage.put("test", "key", b"data")
        >>> obj = storage.get("test", "key")
        >>> print(obj.content)  # b"data"
    """

    def __init__(self) -> None:
        """Initialize the Mock Storage adapter."""
        self._buckets: dict[str, dict[str, StorageObject]] = {}

    def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists.

        Args:
            bucket: Bucket name.

        Returns:
            True if bucket exists.
        """
        return bucket in self._buckets

    def create_bucket(self, bucket: str) -> bool:
        """Create a new bucket.

        Args:
            bucket: Bucket name.

        Returns:
            True if created or already exists.

        Raises:
            ValueError: If bucket name is empty.
        """
        if not bucket:
            raise ValueError("Bucket name cannot be empty")
        if bucket not in self._buckets:
            self._buckets[bucket] = {}
        return True

    def delete_bucket(self, bucket: str) -> bool:
        """Delete a bucket.

        Args:
            bucket: Bucket name.

        Returns:
            True if deleted, False if not found.
        """
        if bucket in self._buckets:
            del self._buckets[bucket]
            return True
        return False

    def put(
        self,
        bucket: str,
        key: str,
        content: bytes | str | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> bool:
        """Store an object in a bucket.

        Args:
            bucket: Bucket name.
            key: Object key.
            content: Object content (bytes, string, or file-like).
            content_type: MIME type.
            metadata: Custom metadata.

        Returns:
            True if successful.

        Raises:
            BucketNotFoundError: If bucket doesn't exist.
            ValueError: If key is empty.
        """
        if not bucket:
            raise ValueError("Bucket name cannot be empty")
        if not key:
            raise ValueError("Object key cannot be empty")

        if bucket not in self._buckets:
            self._buckets[bucket] = {}

        content_bytes: bytes
        if isinstance(content, str):
            content_bytes = content.encode()
        elif isinstance(content, bytes):
            content_bytes = content
        elif hasattr(content, "read"):
            io_content = cast("BinaryIO", content)
            read_result = io_content.read()
            content_bytes = read_result if isinstance(read_result, bytes) else read_result.encode()
        else:
            raise TypeError(f"Unsupported content type: {type(content)}")

        etag = hashlib.md5(content_bytes).hexdigest()
        self._buckets[bucket][key] = StorageObject(
            key=key,
            content=content_bytes,
            bucket=bucket,
            content_type=content_type,
            metadata=metadata or {},
            etag=etag,
            size=len(content_bytes),
        )
        return True

    def get(self, bucket: str, key: str) -> StorageObject | None:
        """Get an object from a bucket.

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            StorageObject or None if not found.
        """
        if bucket not in self._buckets:
            return None
        return self._buckets[bucket].get(key)

    def get_content(self, bucket: str, key: str) -> bytes | None:
        """Get object content directly.

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            Content bytes or None if not found.
        """
        obj = self.get(bucket, key)
        return obj.content if obj else None

    def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists.

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            True if object exists.
        """
        if bucket not in self._buckets:
            return False
        return key in self._buckets[bucket]

    def delete(self, bucket: str, key: str) -> bool:
        """Delete an object from a bucket.

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            True if deleted, False if not found.
        """
        if bucket not in self._buckets:
            return False
        if key in self._buckets[bucket]:
            del self._buckets[bucket][key]
            return True
        return False

    def copy(
        self,
        src_bucket: str,
        src_key: str,
        dst_bucket: str,
        dst_key: str,
    ) -> bool:
        """Copy an object to another location.

        Args:
            src_bucket: Source bucket.
            src_key: Source key.
            dst_bucket: Destination bucket.
            dst_key: Destination key.

        Returns:
            True if copied, False if source not found.
        """
        src_obj = self.get(src_bucket, src_key)
        if src_obj is None:
            return False
        if dst_bucket not in self._buckets:
            self._buckets[dst_bucket] = {}
        self._buckets[dst_bucket][dst_key] = StorageObject(
            key=dst_key,
            content=src_obj.content,
            bucket=dst_bucket,
            content_type=src_obj.content_type,
            metadata=dict(src_obj.metadata),
            etag=src_obj.etag,
            size=src_obj.size,
        )
        return True

    def move(
        self,
        src_bucket: str,
        src_key: str,
        dst_bucket: str,
        dst_key: str,
    ) -> bool:
        """Move an object to another location.

        Args:
            src_bucket: Source bucket.
            src_key: Source key.
            dst_bucket: Destination bucket.
            dst_key: Destination key.

        Returns:
            True if moved, False if source not found.
        """
        if self.copy(src_bucket, src_key, dst_bucket, dst_key):
            return self.delete(src_bucket, src_key)
        return False

    def list_objects(self, bucket: str, prefix: str | None = None) -> list[str]:
        """List object keys in a bucket.

        Args:
            bucket: Bucket name.
            prefix: Optional prefix filter.

        Returns:
            List of object keys.
        """
        if bucket not in self._buckets:
            return []
        keys = list(self._buckets[bucket].keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return keys

    def list_all_objects(self, bucket: str, prefix: str | None = None) -> list[StorageObject]:
        """List all objects in a bucket.

        Args:
            bucket: Bucket name.
            prefix: Optional prefix filter.

        Returns:
            List of StorageObject instances.
        """
        if bucket not in self._buckets:
            return []
        objects = list(self._buckets[bucket].values())
        if prefix:
            objects = [o for o in objects if o.key.startswith(prefix)]
        return objects

    def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        """Get a mock presigned URL.

        Args:
            bucket: Bucket name.
            key: Object key.
            expires_in: Expiration in seconds.

        Returns:
            Mock URL string.
        """
        return f"mock://storage/{bucket}/{key}?expires={expires_in}"

    def health_check(self) -> bool:
        """Check if storage is healthy.

        Returns:
            Always True for mock storage.
        """
        return True

    def get_bucket_count(self) -> int:
        """Get the number of buckets.

        Returns:
            Number of buckets.
        """
        return len(self._buckets)

    def get_object_count(self, bucket: str | None = None) -> int:
        """Get the number of objects.

        Args:
            bucket: Optional bucket to count in.

        Returns:
            Number of objects.
        """
        if bucket:
            return len(self._buckets.get(bucket, {}))
        return sum(len(objects) for objects in self._buckets.values())

    def clear_bucket(self, bucket: str) -> int:
        """Clear all objects from a bucket.

        Args:
            bucket: Bucket name.

        Returns:
            Number of objects removed.
        """
        if bucket not in self._buckets:
            return 0
        count = len(self._buckets[bucket])
        self._buckets[bucket] = {}
        return count

    def clear_all(self) -> int:
        """Clear all buckets and objects.

        Returns:
            Total number of objects removed.
        """
        count = self.get_object_count()
        self._buckets.clear()
        return count

    def update_metadata(
        self,
        bucket: str,
        key: str,
        metadata: dict[str, str],
        merge: bool = True,
    ) -> bool:
        """Update object metadata.

        Args:
            bucket: Bucket name.
            key: Object key.
            metadata: New metadata.
            merge: If True, merge with existing; if False, replace.

        Returns:
            True if updated, False if not found.
        """
        obj = self.get(bucket, key)
        if obj is None:
            return False
        if merge:
            obj.metadata.update(metadata)
        else:
            obj.metadata = metadata
        return True


class LocalFileAdapter:
    """Local filesystem adapter for file operations.

    This adapter provides file operations on the local filesystem,
    useful for testing file I/O without external dependencies.

    Example:
        >>> adapter = LocalFileAdapter(base_dir="/tmp/test")
        >>> adapter.write("file.txt", "content")
        >>> content = adapter.read("file.txt")
    """

    def __init__(self, base_dir: str | None = None) -> None:
        """Initialize the Local File adapter.

        Args:
            base_dir: Base directory for file operations.
                Defaults to system temp directory.
        """
        self._base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to base directory.

        Args:
            path: Relative path.

        Returns:
            Absolute Path object.
        """
        return self._base_dir / path

    def write(self, path: str, content: str | bytes, binary: bool = False) -> int:
        """Write content to a file.

        Args:
            path: Relative file path.
            content: Content to write.
            binary: Whether to write in binary mode.

        Returns:
            Number of bytes/characters written.
        """
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if binary or isinstance(content, bytes) else "w"
        with open(file_path, mode) as f:
            written = f.write(content)
            return written if isinstance(written, int) else len(content)

    def read(self, path: str, binary: bool = False) -> str | bytes:
        """Read content from a file.

        Args:
            path: Relative file path.
            binary: Whether to read in binary mode.

        Returns:
            File content.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        file_path = self._resolve_path(path)
        mode = "rb" if binary else "r"
        with open(file_path, mode) as f:
            return f.read()

    def exists(self, path: str) -> bool:
        """Check if a file or directory exists.

        Args:
            path: Relative path.

        Returns:
            True if exists.
        """
        return self._resolve_path(path).exists()

    def delete(self, path: str) -> bool:
        """Delete a file.

        Args:
            path: Relative file path.

        Returns:
            True if deleted, False if not found.
        """
        file_path = self._resolve_path(path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def append(self, path: str, content: str | bytes) -> int:
        """Append content to a file.

        Args:
            path: Relative file path.
            content: Content to append.

        Returns:
            Number of bytes/characters written.
        """
        file_path = self._resolve_path(path)
        mode = "ab" if isinstance(content, bytes) else "a"
        with open(file_path, mode) as f:
            written = f.write(content)
            return written if isinstance(written, int) else len(content)

    def copy(self, src: str, dst: str) -> bool:
        """Copy a file.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            True if copied, False if source not found.
        """
        import shutil

        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        if not src_path.exists():
            return False
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return True

    def move(self, src: str, dst: str) -> bool:
        """Move a file.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            True if moved, False if source not found.
        """
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        if not src_path.exists():
            return False
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dst_path)
        return True

    def get_info(self, path: str) -> FileInfo | None:
        """Get file information.

        Args:
            path: Relative path.

        Returns:
            FileInfo or None if not found.
        """
        file_path = self._resolve_path(path)
        if not file_path.exists():
            return None
        stat = file_path.stat()
        return FileInfo(
            name=file_path.name,
            path=str(file_path),
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime),
            is_dir=file_path.is_dir(),
        )

    def create_dir(self, path: str) -> bool:
        """Create a directory.

        Args:
            path: Relative directory path.

        Returns:
            True if created.
        """
        file_path = self._resolve_path(path)
        file_path.mkdir(parents=True, exist_ok=True)
        return True

    def remove_dir(self, path: str, recursive: bool = False) -> bool:
        """Remove a directory.

        Args:
            path: Relative directory path.
            recursive: Whether to remove contents recursively.

        Returns:
            True if removed, False if not found.
        """
        import shutil

        file_path = self._resolve_path(path)
        if not file_path.exists():
            return False
        if recursive:
            shutil.rmtree(file_path)
        else:
            file_path.rmdir()
        return True

    def list_dir(self, path: str, recursive: bool = False) -> list[str]:
        """List directory contents.

        Args:
            path: Relative directory path.
            recursive: Whether to list recursively.

        Returns:
            List of file names/paths.
        """
        file_path = self._resolve_path(path)
        if not file_path.exists():
            return []
        if recursive:
            return [str(p.relative_to(file_path)) for p in file_path.rglob("*") if p.is_file()]
        return [p.name for p in file_path.iterdir() if p.is_file()]

    def tempfile(self) -> str:
        """Create a temporary file.

        Returns:
            Absolute path to the temporary file.
        """
        fd, path = tempfile.mkstemp(dir=self._base_dir)
        os.close(fd)
        return path

    def tempdir(self) -> str:
        """Create a temporary directory.

        Returns:
            Absolute path to the temporary directory.
        """
        return tempfile.mkdtemp(dir=self._base_dir)

    def health_check(self) -> bool:
        """Check if storage is healthy.

        Returns:
            True if base directory exists.
        """
        return self._base_dir.exists() and self._base_dir.is_dir()

    def get_base_dir(self) -> str:
        """Get the base directory path.

        Returns:
            Base directory path as string.
        """
        return str(self._base_dir)

    def size(self, path: str) -> int:
        """Get file size.

        Args:
            path: Relative file path.

        Returns:
            Size in bytes.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        file_path = self._resolve_path(path)
        return file_path.stat().st_size

    def modified_time(self, path: str) -> datetime:
        """Get file modification time.

        Args:
            path: Relative file path.

        Returns:
            Modification timestamp.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        file_path = self._resolve_path(path)
        return datetime.fromtimestamp(file_path.stat().st_mtime)
