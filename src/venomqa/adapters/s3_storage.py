"""S3 Storage adapter for object storage testing.

AWS S3 is a widely used object storage service. This adapter also
supports S3-compatible services like MinIO, DigitalOcean Spaces, etc.

Installation:
    pip install boto3

Example:
    >>> from venomqa.adapters import S3StorageAdapter
    >>> adapter = S3StorageAdapter(endpoint_url="http://localhost:9000")
    >>> adapter.upload("my-bucket", "file.txt", b"content")
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO

from venomqa.ports.files import StorageObject, StoragePort

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None


@dataclass
class S3StorageConfig:
    """Configuration for S3 Storage adapter."""

    endpoint_url: str | None = None
    region_name: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    signature_version: str = "s3v4"
    connect_timeout: int = 5
    read_timeout: int = 30


class S3StorageAdapter(StoragePort):
    """Adapter for S3-compatible object storage.

    This adapter provides integration with AWS S3 and compatible
    services for object storage in test environments.

    Attributes:
        config: Configuration for the S3 connection.

    Example:
        >>> adapter = S3StorageAdapter()
        >>> adapter.create_bucket("test-bucket")
        >>> adapter.upload("test-bucket", "key", b"data")
        >>> data = adapter.download("test-bucket", "key")
    """

    def __init__(
        self,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        """Initialize the S3 Storage adapter.

        Args:
            endpoint_url: S3 endpoint URL (for MinIO, etc).
            region_name: AWS region name.
            aws_access_key_id: AWS access key.
            aws_secret_access_key: AWS secret key.

        Raises:
            ImportError: If boto3 is not installed.
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required. Install with: pip install boto3")

        self.config = S3StorageConfig(
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        config = Config(
            connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout,
            signature_version=self.config.signature_version,
        )

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            config=config,
        )

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
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata

        if isinstance(data, str):
            data = data.encode("utf-8")

        if isinstance(data, bytes):
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                **extra_args,
            )
        else:
            self._client.upload_fileobj(
                data,
                bucket,
                key,
                ExtraArgs=extra_args if extra_args else None,
            )
        return True

    def download(self, bucket: str, key: str) -> bytes | None:
        """Download an object.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            Object data or None if not found.
        """
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def delete(self, bucket: str, key: str) -> bool:
        """Delete an object.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            True if deleted, False if not found.
        """
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            True if exists, False otherwise.
        """
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def get_object(self, bucket: str, key: str) -> StorageObject | None:
        """Get object metadata.

        Args:
            bucket: Bucket/container name.
            key: Object key.

        Returns:
            Object metadata or None if not found.
        """
        try:
            response = self._client.head_object(Bucket=bucket, Key=key)
            return StorageObject(
                key=key,
                size=response.get("ContentLength", 0),
                content_type=response.get("ContentType", "application/octet-stream"),
                etag=response.get("ETag", "").strip('"'),
                last_modified=response.get("LastModified"),
                metadata=response.get("Metadata", {}),
            )
        except ClientError:
            return None

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
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix

        count = 0
        paginator = self._client.get_paginator("list_objects_v2")

        for page in paginator.paginate(**kwargs):
            for obj in page.get("Contents", []):
                yield StorageObject(
                    key=obj["Key"],
                    size=obj["Size"],
                    content_type="application/octet-stream",
                    etag=obj.get("ETag", "").strip('"'),
                    last_modified=obj.get("LastModified"),
                )
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
        try:
            if self.config.region_name == "us-east-1":
                self._client.create_bucket(Bucket=bucket)
            else:
                self._client.create_bucket(
                    Bucket=bucket,
                    CreateBucketConfiguration={"LocationConstraint": self.config.region_name},
                )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "BucketAlreadyOwnedByYou":
                return True
            raise

    def delete_bucket(self, bucket: str, force: bool = False) -> bool:
        """Delete a bucket.

        Args:
            bucket: Bucket name.
            force: Delete all objects first.

        Returns:
            True if successful.
        """
        try:
            if force:
                for obj in self.list_objects(bucket):
                    self._client.delete_object(Bucket=bucket, Key=obj.key)

            self._client.delete_bucket(Bucket=bucket)
            return True
        except ClientError:
            return False

    def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists.

        Args:
            bucket: Bucket name.

        Returns:
            True if exists, False otherwise.
        """
        try:
            self._client.head_bucket(Bucket=bucket)
            return True
        except ClientError:
            return False

    def get_presigned_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
        method: str = "GET",
    ) -> str | None:
        """Get a presigned URL for an object.

        Args:
            bucket: Bucket name.
            key: Object key.
            expires_in: URL expiration in seconds.
            method: HTTP method (GET or PUT).

        Returns:
            Presigned URL or None if not possible.
        """
        try:
            client_method = "get_object" if method == "GET" else "put_object"
            return self._client.generate_presigned_url(
                client_method,
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except ClientError:
            return None

    def health_check(self) -> bool:
        """Check if the storage service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            self._client.list_buckets()
            return True
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
        try:
            self._client.copy_object(
                Bucket=dst_bucket,
                Key=dst_key,
                CopySource={"Bucket": src_bucket, "Key": src_key},
            )
            return True
        except ClientError:
            return False

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

    def get_bucket_policy(self, bucket: str) -> dict[str, Any] | None:
        """Get bucket policy.

        Args:
            bucket: Bucket name.

        Returns:
            Policy document or None.
        """
        try:
            response = self._client.get_bucket_policy(Bucket=bucket)
            import json

            return json.loads(response["Policy"])
        except ClientError:
            return None

    def set_bucket_policy(self, bucket: str, policy: dict[str, Any]) -> bool:
        """Set bucket policy.

        Args:
            bucket: Bucket name.
            policy: Policy document.

        Returns:
            True if successful.
        """
        try:
            import json

            self._client.put_bucket_policy(
                Bucket=bucket,
                Policy=json.dumps(policy),
            )
            return True
        except ClientError:
            return False

    def list_buckets(self) -> list[str]:
        """List all buckets.

        Returns:
            List of bucket names.
        """
        try:
            response = self._client.list_buckets()
            return [b["Name"] for b in response.get("Buckets", [])]
        except ClientError:
            return []

    def set_object_tags(
        self,
        bucket: str,
        key: str,
        tags: dict[str, str],
    ) -> bool:
        """Set tags on an object.

        Args:
            bucket: Bucket name.
            key: Object key.
            tags: Tag key-value pairs.

        Returns:
            True if successful.
        """
        try:
            self._client.put_object_tagging(
                Bucket=bucket,
                Key=key,
                Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]},
            )
            return True
        except ClientError:
            return False

    def get_object_tags(self, bucket: str, key: str) -> dict[str, str]:
        """Get tags on an object.

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            Tag key-value pairs.
        """
        try:
            response = self._client.get_object_tagging(Bucket=bucket, Key=key)
            return {t["Key"]: t["Value"] for t in response.get("TagSet", [])}
        except ClientError:
            return {}
