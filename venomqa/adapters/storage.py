"""Mock Storage adapter for testing.

This adapter provides an in-memory object storage mock for testing.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO


@dataclass
class StorageObject:
    """Represents a stored object."""

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
    """File information."""

    name: str
    path: str
    size: int
    modified_time: datetime
    is_dir: bool = False


class MockStorageAdapter:
    """In-memory mock storage adapter for testing bucket/object operations."""

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, StorageObject]] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self._buckets

    def create_bucket(self, bucket: str) -> bool:
        if bucket not in self._buckets:
            self._buckets[bucket] = {}
        return True

    def delete_bucket(self, bucket: str) -> bool:
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
        if bucket not in self._buckets:
            self._buckets[bucket] = {}

        if isinstance(content, str):
            content_bytes = content.encode()
        elif hasattr(content, "read"):
            content_bytes = content.read()
            if isinstance(content_bytes, str):
                content_bytes = content_bytes.encode()
        else:
            content_bytes = content

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
        if bucket not in self._buckets:
            return None
        return self._buckets[bucket].get(key)

    def get_content(self, bucket: str, key: str) -> bytes | None:
        obj = self.get(bucket, key)
        return obj.content if obj else None

    def exists(self, bucket: str, key: str) -> bool:
        if bucket not in self._buckets:
            return False
        return key in self._buckets[bucket]

    def delete(self, bucket: str, key: str) -> bool:
        if bucket not in self._buckets:
            return False
        if key in self._buckets[bucket]:
            del self._buckets[bucket][key]
            return True
        return False

    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> bool:
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

    def move(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> bool:
        if self.copy(src_bucket, src_key, dst_bucket, dst_key):
            return self.delete(src_bucket, src_key)
        return False

    def list_objects(self, bucket: str, prefix: str | None = None) -> list[str]:
        if bucket not in self._buckets:
            return []
        keys = list(self._buckets[bucket].keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return keys

    def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        return f"mock://storage/{bucket}/{key}?expires={expires_in}"

    def health_check(self) -> bool:
        return True


class LocalFileAdapter:
    """Local filesystem adapter for file operations."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        return self._base_dir / path

    def write(self, path: str, content: str | bytes, binary: bool = False) -> int:
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if binary or isinstance(content, bytes) else "w"
        with open(file_path, mode) as f:
            written = f.write(content)
            return written if isinstance(written, int) else len(content)

    def read(self, path: str, binary: bool = False) -> str | bytes:
        file_path = self._resolve_path(path)
        mode = "rb" if binary else "r"
        with open(file_path, mode) as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return self._resolve_path(path).exists()

    def delete(self, path: str) -> bool:
        file_path = self._resolve_path(path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def append(self, path: str, content: str | bytes) -> int:
        file_path = self._resolve_path(path)
        mode = "ab" if isinstance(content, bytes) else "a"
        with open(file_path, mode) as f:
            written = f.write(content)
            return written if isinstance(written, int) else len(content)

    def copy(self, src: str, dst: str) -> bool:
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        if not src_path.exists():
            return False
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(src_path, dst_path)
        return True

    def move(self, src: str, dst: str) -> bool:
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        if not src_path.exists():
            return False
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dst_path)
        return True

    def get_info(self, path: str) -> FileInfo | None:
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
        file_path = self._resolve_path(path)
        file_path.mkdir(parents=True, exist_ok=True)
        return True

    def remove_dir(self, path: str, recursive: bool = False) -> bool:
        file_path = self._resolve_path(path)
        if not file_path.exists():
            return False
        import shutil

        if recursive:
            shutil.rmtree(file_path)
        else:
            file_path.rmdir()
        return True

    def list_dir(self, path: str, recursive: bool = False) -> list[str]:
        file_path = self._resolve_path(path)
        if not file_path.exists():
            return []
        if recursive:
            return [str(p.relative_to(file_path)) for p in file_path.rglob("*") if p.is_file()]
        return [p.name for p in file_path.iterdir() if p.is_file()]

    def tempfile(self) -> str:
        fd, path = tempfile.mkstemp(dir=self._base_dir)
        os.close(fd)
        return path

    def tempdir(self) -> str:
        return tempfile.mkdtemp(dir=self._base_dir)

    def health_check(self) -> bool:
        return True
