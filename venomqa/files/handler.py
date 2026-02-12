"""FileHandler for upload, download, and management operations."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

import httpx

from venomqa.files.storage import StorageBackend, StorageConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class FileUploadResult:
    """Result of a file upload operation."""

    success: bool
    file_id: str | None = None
    filename: str | None = None
    url: str | None = None
    size_bytes: int = 0
    content_type: str | None = None
    hash_md5: str | None = None
    hash_sha256: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileDownloadResult:
    """Result of a file download operation."""

    success: bool
    local_path: str | None = None
    size_bytes: int = 0
    content_type: str | None = None
    hash_md5: str | None = None
    hash_sha256: str | None = None
    error: str | None = None


@dataclass
class FileInfo:
    """Information about a file."""

    path: str
    name: str
    size_bytes: int
    content_type: str | None
    hash_md5: str
    hash_sha256: str
    created_at: datetime | None = None
    modified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class FileHandler:
    """Handler for file upload, download, and management operations."""

    def __init__(
        self,
        storage_backend: StorageBackend | None = None,
        storage_config: StorageConfig | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
        temp_dir: str | Path | None = None,
        chunk_size: int = 8192,
    ) -> None:
        self.storage_backend = storage_backend
        self.storage_config = storage_config or StorageConfig()
        self.base_url = base_url.rstrip("/") if base_url else None
        self.default_headers = default_headers or {}
        self.temp_dir = (
            Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "venomqa_files"
        )
        self.chunk_size = chunk_size
        self._client: httpx.Client | None = None
        self._uploaded_files: dict[str, FileUploadResult] = {}

        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers=self.default_headers, timeout=60.0)
        return self._client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def upload_file(
        self,
        source: str | Path | BinaryIO,
        destination: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileUploadResult:
        if isinstance(source, str) and (
            source.startswith("http://") or source.startswith("https://")
        ):
            return self._upload_from_url(source, destination, content_type, metadata)
        elif isinstance(source, (str, Path)):
            return self._upload_from_path(Path(source), destination, content_type, metadata)
        else:
            return self._upload_from_stream(source, destination, content_type, metadata)

    def _upload_from_path(
        self,
        path: Path,
        destination: str | None,
        content_type: str | None,
        metadata: dict[str, Any] | None,
    ) -> FileUploadResult:
        if not path.exists():
            return FileUploadResult(success=False, error=f"File not found: {path}")

        if not path.is_file():
            return FileUploadResult(success=False, error=f"Not a file: {path}")

        try:
            file_size = path.stat().st_size
            detected_type = content_type or mimetypes.guess_type(str(path))[0]
            filename = destination or path.name

            with open(path, "rb") as f:
                content = f.read()

            hash_md5 = hashlib.md5(content).hexdigest()
            hash_sha256 = hashlib.sha256(content).hexdigest()

            if self.storage_backend:
                file_id = self.storage_backend.upload(
                    data=content,
                    key=filename,
                    content_type=detected_type,
                    metadata=metadata,
                )
                url = self.storage_backend.get_url(file_id)
            else:
                file_id = filename
                url = None

            result = FileUploadResult(
                success=True,
                file_id=file_id,
                filename=filename,
                url=url,
                size_bytes=file_size,
                content_type=detected_type,
                hash_md5=hash_md5,
                hash_sha256=hash_sha256,
                metadata=metadata or {},
            )
            self._uploaded_files[file_id] = result
            return result

        except Exception as e:
            logger.error(f"Failed to upload file {path}: {e}")
            return FileUploadResult(success=False, error=str(e))

    def _upload_from_url(
        self,
        url: str,
        destination: str | None,
        content_type: str | None,
        metadata: dict[str, Any] | None,
    ) -> FileUploadResult:
        try:
            client = self._get_client()
            response = client.get(url)
            response.raise_for_status()

            content = response.content
            detected_type = content_type or response.headers.get("content-type")
            filename = destination or url.split("/")[-1] or "downloaded_file"

            hash_md5 = hashlib.md5(content).hexdigest()
            hash_sha256 = hashlib.sha256(content).hexdigest()

            if self.storage_backend:
                file_id = self.storage_backend.upload(
                    data=content,
                    key=filename,
                    content_type=detected_type,
                    metadata=metadata,
                )
                storage_url = self.storage_backend.get_url(file_id)
            else:
                file_id = filename
                storage_url = None

            result = FileUploadResult(
                success=True,
                file_id=file_id,
                filename=filename,
                url=storage_url,
                size_bytes=len(content),
                content_type=detected_type,
                hash_md5=hash_md5,
                hash_sha256=hash_sha256,
                metadata=metadata or {},
            )
            self._uploaded_files[file_id] = result
            return result

        except Exception as e:
            logger.error(f"Failed to upload from URL {url}: {e}")
            return FileUploadResult(success=False, error=str(e))

    def _upload_from_stream(
        self,
        stream: BinaryIO,
        destination: str | None,
        content_type: str | None,
        metadata: dict[str, Any] | None,
    ) -> FileUploadResult:
        try:
            content = stream.read()
            filename = destination or "uploaded_file"

            hash_md5 = hashlib.md5(content).hexdigest()
            hash_sha256 = hashlib.sha256(content).hexdigest()

            if self.storage_backend:
                file_id = self.storage_backend.upload(
                    data=content,
                    key=filename,
                    content_type=content_type,
                    metadata=metadata,
                )
                url = self.storage_backend.get_url(file_id)
            else:
                file_id = filename
                url = None

            result = FileUploadResult(
                success=True,
                file_id=file_id,
                filename=filename,
                url=url,
                size_bytes=len(content),
                content_type=content_type,
                hash_md5=hash_md5,
                hash_sha256=hash_sha256,
                metadata=metadata or {},
            )
            self._uploaded_files[file_id] = result
            return result

        except Exception as e:
            logger.error(f"Failed to upload from stream: {e}")
            return FileUploadResult(success=False, error=str(e))

    def download_file(
        self,
        source: str,
        destination: str | Path | None = None,
        verify_hash: str | None = None,
        hash_algorithm: str = "sha256",
    ) -> FileDownloadResult:
        dest_path = Path(destination) if destination else self.temp_dir / source.split("/")[-1]

        try:
            if source.startswith("http://") or source.startswith("https://"):
                content, content_type = self._download_from_http(source)
            elif self.storage_backend and source in self._uploaded_files:
                content = self.storage_backend.download(source)
                content_type = self._uploaded_files[source].content_type
            elif self.storage_backend:
                content = self.storage_backend.download(source)
                content_type = None
            else:
                with open(source, "rb") as f:
                    content = f.read()
                content_type = mimetypes.guess_type(source)[0]

            if verify_hash:
                computed_hash = self._compute_hash(content, hash_algorithm)
                if computed_hash != verify_hash:
                    error_msg = (
                        f"Hash verification failed. Expected {verify_hash}, got {computed_hash}"
                    )
                    return FileDownloadResult(
                        success=False,
                        error=error_msg,
                    )

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(content)

            hash_md5 = hashlib.md5(content).hexdigest()
            hash_sha256 = hashlib.sha256(content).hexdigest()

            return FileDownloadResult(
                success=True,
                local_path=str(dest_path),
                size_bytes=len(content),
                content_type=content_type,
                hash_md5=hash_md5,
                hash_sha256=hash_sha256,
            )

        except Exception as e:
            logger.error(f"Failed to download file from {source}: {e}")
            return FileDownloadResult(success=False, error=str(e))

    def _download_from_http(self, url: str) -> tuple[bytes, str | None]:
        client = self._get_client()
        response = client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get("content-type")

    def multipart_upload(
        self,
        file_path: str | Path,
        field_name: str = "file",
        url: str | None = None,
        additional_fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        upload_url = url
        if not upload_url and self.base_url:
            upload_url = f"{self.base_url}/upload"
        elif not upload_url:
            raise ValueError("No upload URL provided and no base_url configured")

        with open(path, "rb") as f:
            files = {field_name: (path.name, f, mimetypes.guess_type(str(path))[0])}
            data = additional_fields or {}

            client = self._get_client()
            request_headers = {**self.default_headers, **(headers or {})}
            if "Content-Type" in request_headers:
                del request_headers["Content-Type"]

            response = client.post(upload_url, files=files, data=data, headers=request_headers)

        return response

    def file_exists(self, path: str | Path) -> bool:
        path = Path(path)
        if path.exists():
            return True

        if self.storage_backend:
            return self.storage_backend.exists(str(path))

        return False

    def delete_file(self, path: str) -> bool:
        try:
            local_path = Path(path)
            if local_path.exists():
                local_path.unlink()
                logger.info(f"Deleted local file: {path}")
                return True

            if self.storage_backend:
                result = self.storage_backend.delete(path)
                if result:
                    self._uploaded_files.pop(path, None)
                    logger.info(f"Deleted storage file: {path}")
                return result

            return False

        except Exception as e:
            logger.error(f"Failed to delete file {path}: {e}")
            return False

    def file_hash(
        self,
        path: str | Path,
        algorithm: str = "sha256",
        chunk_size: int | None = None,
    ) -> str:
        chunk_size = chunk_size or self.chunk_size
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        hash_func = self._get_hash_algorithm(algorithm)

        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                hash_func.update(chunk)

        return hash_func.hexdigest()

    def _compute_hash(self, content: bytes, algorithm: str) -> str:
        hash_func = self._get_hash_algorithm(algorithm)
        hash_func.update(content)
        return hash_func.hexdigest()

    def _get_hash_algorithm(self, algorithm: str):
        algorithms = {
            "md5": hashlib.md5,
            "sha1": hashlib.sha1,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
        }
        algorithm_lower = algorithm.lower()
        if algorithm_lower not in algorithms:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        return algorithms[algorithm_lower]()

    def get_file_info(self, path: str | Path) -> FileInfo:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        stat = path.stat()
        content_type = mimetypes.guess_type(str(path))[0]

        return FileInfo(
            path=str(path.absolute()),
            name=path.name,
            size_bytes=stat.st_size,
            content_type=content_type,
            hash_md5=self.file_hash(path, "md5"),
            hash_sha256=self.file_hash(path, "sha256"),
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )

    def copy_file(self, source: str | Path, destination: str | Path) -> bool:
        try:
            src_path = Path(source)
            dest_path = Path(destination)

            if not src_path.exists():
                logger.error(f"Source file not found: {src_path}")
                return False

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with open(src_path, "rb") as src:
                with open(dest_path, "wb") as dest:
                    while chunk := src.read(self.chunk_size):
                        dest.write(chunk)

            logger.info(f"Copied {src_path} to {dest_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy {source} to {destination}: {e}")
            return False

    def move_file(self, source: str | Path, destination: str | Path) -> bool:
        if self.copy_file(source, destination):
            Path(source).unlink()
            logger.info(f"Moved {source} to {destination}")
            return True
        return False

    def cleanup_temp_files(self) -> int:
        cleaned = 0
        try:
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
                    cleaned += 1
            logger.info(f"Cleaned up {cleaned} temporary files")
        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")
        return cleaned

    def get_uploaded_files(self) -> dict[str, FileUploadResult]:
        return self._uploaded_files.copy()

    def __enter__(self) -> FileHandler:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
