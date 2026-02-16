"""Mock storage adapter for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import copy

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


@dataclass
class StoredFile:
    """A file in storage."""

    path: str
    content: bytes
    content_type: str = "application/octet-stream"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, str] = field(default_factory=dict)


class MockStorage:
    """In-memory file storage for testing.

    Implements Rollbackable protocol for checkpoint/restore.
    """

    def __init__(self, bucket: str = "default") -> None:
        self.bucket = bucket
        self._files: dict[str, StoredFile] = {}

    def put(
        self,
        path: str,
        content: bytes | str,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StoredFile:
        """Store a file."""
        if isinstance(content, str):
            content = content.encode()

        file = StoredFile(
            path=path,
            content=content,
            content_type=content_type,
            metadata=metadata or {},
        )
        self._files[path] = file
        return file

    def get(self, path: str) -> StoredFile | None:
        """Get a file by path."""
        return self._files.get(path)

    def delete(self, path: str) -> bool:
        """Delete a file."""
        if path in self._files:
            del self._files[path]
            return True
        return False

    def exists(self, path: str) -> bool:
        """Check if a file exists."""
        return path in self._files

    def list(self, prefix: str = "") -> list[str]:
        """List files with the given prefix."""
        return [p for p in self._files if p.startswith(prefix)]

    @property
    def file_count(self) -> int:
        return len(self._files)

    def clear(self) -> None:
        """Clear all files."""
        self._files.clear()

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current storage state."""
        return copy.deepcopy(self._files)

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore storage state."""
        self._files = copy.deepcopy(checkpoint)

    def observe(self) -> Observation:
        """Get current storage state."""
        return Observation(
            system=f"storage:{self.bucket}",
            data={
                "file_count": self.file_count,
                "files": list(self._files.keys()),
                "total_size": sum(len(f.content) for f in self._files.values()),
            },
            observed_at=datetime.now(),
        )
