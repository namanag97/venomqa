from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, BinaryIO


@dataclass
class FileInfo:
    name: str
    path: str
    size: int
    content_type: str
    modified_at: datetime
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StorageObject:
    key: str
    bucket: str
    content: bytes | None = None
    content_type: str = "application/octet-stream"
    metadata: dict[str, Any] = field(default_factory=dict)
    size: int = 0
    etag: str | None = None
    last_modified: datetime | None = None


class FilePort(ABC):
    @abstractmethod
    def read(self, path: str, binary: bool = False) -> str | bytes:
        """Read file contents."""
        ...

    @abstractmethod
    def write(self, path: str, content: str | bytes, binary: bool = False) -> int:
        """Write content to a file."""
        ...

    @abstractmethod
    def append(self, path: str, content: str | bytes) -> int:
        """Append content to a file."""
        ...

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete a file."""
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file exists."""
        ...

    @abstractmethod
    def copy(self, src: str, dst: str) -> bool:
        """Copy a file."""
        ...

    @abstractmethod
    def move(self, src: str, dst: str) -> bool:
        """Move a file."""
        ...

    @abstractmethod
    def get_info(self, path: str) -> FileInfo | None:
        """Get file information."""
        ...

    @abstractmethod
    def list_dir(self, path: str, recursive: bool = False) -> list[FileInfo]:
        """List files in a directory."""
        ...

    @abstractmethod
    def create_dir(self, path: str, exist_ok: bool = True) -> bool:
        """Create a directory."""
        ...

    @abstractmethod
    def remove_dir(self, path: str, recursive: bool = False) -> bool:
        """Remove a directory."""
        ...

    @abstractmethod
    def tempfile(self, suffix: str = "", prefix: str = "") -> str:
        """Create a temporary file and return its path."""
        ...

    @abstractmethod
    def tempdir(self) -> str:
        """Create a temporary directory and return its path."""
        ...


class StoragePort(ABC):
    @abstractmethod
    def get(self, bucket: str, key: str) -> StorageObject | None:
        """Get an object from storage."""
        ...

    @abstractmethod
    def get_content(self, bucket: str, key: str) -> bytes | None:
        """Get object content from storage."""
        ...

    @abstractmethod
    def put(
        self,
        bucket: str,
        key: str,
        content: bytes | str | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Put an object into storage."""
        ...

    @abstractmethod
    def delete(self, bucket: str, key: str) -> bool:
        """Delete an object from storage."""
        ...

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists."""
        ...

    @abstractmethod
    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> bool:
        """Copy an object."""
        ...

    @abstractmethod
    def move(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> bool:
        """Move an object."""
        ...

    @abstractmethod
    def list_objects(self, bucket: str, prefix: str = "") -> list[StorageObject]:
        """List objects in a bucket."""
        ...

    @abstractmethod
    def create_bucket(self, bucket: str) -> bool:
        """Create a bucket."""
        ...

    @abstractmethod
    def delete_bucket(self, bucket: str) -> bool:
        """Delete a bucket."""
        ...

    @abstractmethod
    def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists."""
        ...

    @abstractmethod
    def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        """Get a presigned URL for an object."""
        ...
