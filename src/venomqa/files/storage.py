"""Storage backends for file handling (Local, S3, GCS, Azure Blob)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Configuration for storage backends."""

    bucket_name: str | None = None
    region: str = "us-east-1"
    endpoint_url: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    prefix: str = ""
    max_retries: int = 3
    timeout_seconds: int = 30
    enable_encryption: bool = False
    extra_config: dict[str, Any] = field(default_factory=dict)


class StorageBackend(Protocol):
    """Protocol for storage backend implementations."""

    def upload(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def download(self, key: str) -> bytes: ...

    def delete(self, key: str) -> bool: ...

    def exists(self, key: str) -> bool: ...

    def get_url(self, key: str, expires_in: int | None = None) -> str: ...

    def list_files(self, prefix: str | None = None) -> list[str]: ...


class BaseStorageBackend(ABC):
    """Abstract base class for storage backends."""

    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self._connected = False

    @abstractmethod
    def upload(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        pass

    @abstractmethod
    def download(self, key: str) -> bytes:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    def get_url(self, key: str, expires_in: int | None = None) -> str:
        pass

    @abstractmethod
    def list_files(self, prefix: str | None = None) -> list[str]:
        pass

    def _get_full_key(self, key: str) -> str:
        if self.config.prefix:
            return f"{self.config.prefix.rstrip('/')}/{key.lstrip('/')}"
        return key


class LocalStorageBackend(BaseStorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, config: StorageConfig, base_path: str | Path | None = None) -> None:
        super().__init__(config)
        self.base_path = Path(base_path or self.config.extra_config.get("base_path", "./storage"))
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._connected = True

    def upload(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        full_key = self._get_full_key(key)
        file_path = self.base_path / full_key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(data)

        if metadata:
            meta_path = file_path.with_suffix(file_path.suffix + ".meta")
            import json

            with open(meta_path, "w") as f:
                json.dump({"content_type": content_type, "metadata": metadata}, f)

        logger.debug(f"Uploaded file to local storage: {full_key}")
        return full_key

    def download(self, key: str) -> bytes:
        full_key = self._get_full_key(key)
        file_path = self.base_path / full_key

        if not file_path.exists():
            raise FileNotFoundError(f"File not found in local storage: {full_key}")

        with open(file_path, "rb") as f:
            return f.read()

    def delete(self, key: str) -> bool:
        full_key = self._get_full_key(key)
        file_path = self.base_path / full_key

        if not file_path.exists():
            return False

        file_path.unlink()
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        if meta_path.exists():
            meta_path.unlink()

        logger.debug(f"Deleted file from local storage: {full_key}")
        return True

    def exists(self, key: str) -> bool:
        full_key = self._get_full_key(key)
        return (self.base_path / full_key).exists()

    def get_url(self, key: str, expires_in: int | None = None) -> str:
        full_key = self._get_full_key(key)
        return f"file://{(self.base_path / full_key).absolute()}"

    def list_files(self, prefix: str | None = None) -> list[str]:
        search_path = self.base_path / self._get_full_key(prefix or "")
        if not search_path.exists():
            return []

        if search_path.is_file():
            return [str(search_path.relative_to(self.base_path))]

        files = []
        for file_path in search_path.rglob("*"):
            if file_path.is_file() and not file_path.suffix.endswith(".meta"):
                files.append(str(file_path.relative_to(self.base_path)))
        return files

    def clear(self) -> int:
        count = 0
        for file_path in self.base_path.rglob("*"):
            if file_path.is_file():
                file_path.unlink()
                count += 1
        return count


class S3StorageBackend(BaseStorageBackend):
    """AWS S3 storage backend using boto3."""

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._client = None
        self._resource = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config

                boto3_config = Config(
                    retries={"max_attempts": self.config.max_retries},
                    connect_timeout=self.config.timeout_seconds,
                )

                session_kwargs = {}
                if self.config.access_key and self.config.secret_key:
                    session_kwargs["aws_access_key_id"] = self.config.access_key
                    session_kwargs["aws_secret_access_key"] = self.config.secret_key

                session = boto3.Session(**session_kwargs)

                client_kwargs = {"config": boto3_config}
                if self.config.region:
                    client_kwargs["region_name"] = self.config.region
                if self.config.endpoint_url:
                    client_kwargs["endpoint_url"] = self.config.endpoint_url

                self._client = session.client("s3", **client_kwargs)
                self._resource = session.resource("s3", **client_kwargs)
                self._connected = True

            except ImportError as e:
                raise ImportError(
                    "boto3 is required for S3 storage. Install with: pip install boto3"
                ) from e

        return self._client

    @property
    def bucket_name(self) -> str:
        if not self.config.bucket_name:
            raise ValueError("S3 bucket_name is required in StorageConfig")
        return self.config.bucket_name

    def upload(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        client = self._get_client()
        full_key = self._get_full_key(key)

        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}
        if self.config.enable_encryption:
            extra_args["ServerSideEncryption"] = "AES256"

        client.put_object(Bucket=self.bucket_name, Key=full_key, Body=data, **extra_args)

        logger.debug(f"Uploaded file to S3: {full_key}")
        return full_key

    def download(self, key: str) -> bytes:
        client = self._get_client()
        full_key = self._get_full_key(key)

        response = client.get_object(Bucket=self.bucket_name, Key=full_key)
        return response["Body"].read()

    def delete(self, key: str) -> bool:
        client = self._get_client()
        full_key = self._get_full_key(key)

        try:
            client.delete_object(Bucket=self.bucket_name, Key=full_key)
            logger.debug(f"Deleted file from S3: {full_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from S3: {e}")
            return False

    def exists(self, key: str) -> bool:
        client = self._get_client()
        full_key = self._get_full_key(key)

        try:
            client.head_object(Bucket=self.bucket_name, Key=full_key)
            return True
        except Exception:
            return False

    def get_url(self, key: str, expires_in: int | None = None) -> str:
        client = self._get_client()
        full_key = self._get_full_key(key)

        if expires_in is None:
            expires_in = 3600

        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": full_key},
            ExpiresIn=expires_in,
        )

    def list_files(self, prefix: str | None = None) -> list[str]:
        client = self._get_client()
        search_prefix = self._get_full_key(prefix or "")

        files = []
        paginator = client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=search_prefix):
            for obj in page.get("Contents", []):
                files.append(obj["Key"])

        return files


class GCSStorageBackend(BaseStorageBackend):
    """Google Cloud Storage backend."""

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._client = None
        self._bucket = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import storage

                client_kwargs = {}
                if self.config.extra_config.get("credentials_path"):
                    client_kwargs["filename"] = self.config.extra_config["credentials_path"]

                self._client = storage.Client(**client_kwargs)
                self._connected = True

            except ImportError as e:
                raise ImportError(
                    "google-cloud-storage is required for GCS. "
                    "Install with: pip install google-cloud-storage"
                ) from e

        return self._client

    def _get_bucket(self):
        if self._bucket is None:
            client = self._get_client()
            if not self.config.bucket_name:
                raise ValueError("GCS bucket_name is required in StorageConfig")
            self._bucket = client.bucket(self.config.bucket_name)
        return self._bucket

    def upload(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        bucket = self._get_bucket()
        full_key = self._get_full_key(key)

        blob = bucket.blob(full_key)

        if content_type:
            blob.content_type = content_type
        if metadata:
            blob.metadata = metadata

        blob.upload_from_string(data)

        logger.debug(f"Uploaded file to GCS: {full_key}")
        return full_key

    def download(self, key: str) -> bytes:
        bucket = self._get_bucket()
        full_key = self._get_full_key(key)

        blob = bucket.blob(full_key)
        if not blob.exists():
            raise FileNotFoundError(f"File not found in GCS: {full_key}")

        return blob.download_as_bytes()

    def delete(self, key: str) -> bool:
        bucket = self._get_bucket()
        full_key = self._get_full_key(key)

        blob = bucket.blob(full_key)
        try:
            blob.delete()
            logger.debug(f"Deleted file from GCS: {full_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from GCS: {e}")
            return False

    def exists(self, key: str) -> bool:
        bucket = self._get_bucket()
        full_key = self._get_full_key(key)
        return bucket.blob(full_key).exists()

    def get_url(self, key: str, expires_in: int | None = None) -> str:
        bucket = self._get_bucket()
        full_key = self._get_full_key(key)

        blob = bucket.blob(full_key)

        if expires_in is None:
            expires_in = 3600

        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_in),
        )

    def list_files(self, prefix: str | None = None) -> list[str]:
        bucket = self._get_bucket()
        search_prefix = self._get_full_key(prefix or "")

        return [blob.name for blob in bucket.list_blobs(prefix=search_prefix)]


class AzureBlobBackend(BaseStorageBackend):
    """Azure Blob Storage backend."""

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._blob_service_client = None
        self._container_client = None

    def _get_client(self):
        if self._blob_service_client is None:
            try:
                from azure.storage.blob import BlobServiceClient

                connection_string = self.config.extra_config.get("connection_string")
                account_url = self.config.extra_config.get("account_url")

                if connection_string:
                    self._blob_service_client = BlobServiceClient.from_connection_string(
                        connection_string
                    )
                elif account_url and self.config.access_key:
                    credential = self.config.access_key
                    self._blob_service_client = BlobServiceClient(
                        account_url=account_url,
                        credential=credential,
                    )
                else:
                    raise ValueError(
                        "Azure requires either connection_string or account_url + access_key"
                    )

                self._connected = True

            except ImportError as e:
                raise ImportError(
                    "azure-storage-blob is required for Azure. "
                    "Install with: pip install azure-storage-blob"
                ) from e

        return self._blob_service_client

    def _get_container_client(self):
        if self._container_client is None:
            client = self._get_client()
            if not self.config.bucket_name:
                raise ValueError("Azure container name (bucket_name) is required in StorageConfig")
            self._container_client = client.get_container_client(self.config.bucket_name)
        return self._container_client

    @property
    def container_name(self) -> str:
        return self.config.bucket_name or ""

    def upload(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        container = self._get_container_client()
        full_key = self._get_full_key(key)

        blob_client = container.get_blob_client(full_key)

        headers = {}
        if content_type:
            headers["content_type"] = content_type

        blob_client.upload_blob(data, overwrite=True, metadata=metadata, **headers)

        logger.debug(f"Uploaded file to Azure Blob: {full_key}")
        return full_key

    def download(self, key: str) -> bytes:
        container = self._get_container_client()
        full_key = self._get_full_key(key)

        blob_client = container.get_blob_client(full_key)

        try:
            download_stream = blob_client.download_blob()
            return download_stream.readall()
        except Exception as e:
            raise FileNotFoundError(f"File not found in Azure Blob: {full_key}") from e

    def delete(self, key: str) -> bool:
        container = self._get_container_client()
        full_key = self._get_full_key(key)

        blob_client = container.get_blob_client(full_key)

        try:
            blob_client.delete_blob()
            logger.debug(f"Deleted file from Azure Blob: {full_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from Azure Blob: {e}")
            return False

    def exists(self, key: str) -> bool:
        container = self._get_container_client()
        full_key = self._get_full_key(key)

        blob_client = container.get_blob_client(full_key)
        return blob_client.exists()

    def get_url(self, key: str, expires_in: int | None = None) -> str:
        container = self._get_container_client()
        full_key = self._get_full_key(key)

        blob_client = container.get_blob_client(full_key)

        if expires_in is None:
            expires_in = 3600

        from datetime import timedelta

        sas_token = blob_client.generate_sas(
            permission="r",
            expiry=datetime.utcnow() + timedelta(seconds=expires_in),
        )

        return f"{blob_client.url}?{sas_token}"

    def list_files(self, prefix: str | None = None) -> list[str]:
        container = self._get_container_client()
        search_prefix = self._get_full_key(prefix or "")

        files = []
        for blob in container.list_blobs(name_starts_with=search_prefix):
            files.append(blob.name)

        return files
