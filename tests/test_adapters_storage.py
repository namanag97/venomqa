"""Tests for storage adapters in VenomQA."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO

import pytest

from venomqa.adapters.storage import MockStorageAdapter, LocalFileAdapter


class TestMockStorageAdapter:
    """Tests for MockStorageAdapter."""

    @pytest.fixture
    def adapter(self) -> MockStorageAdapter:
        return MockStorageAdapter()

    def test_adapter_initialization(self, adapter: MockStorageAdapter) -> None:
        assert adapter.bucket_exists("test") is False

    def test_create_bucket(self, adapter: MockStorageAdapter) -> None:
        result = adapter.create_bucket("test-bucket")
        assert result is True
        assert adapter.bucket_exists("test-bucket") is True

    def test_create_bucket_idempotent(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        result = adapter.create_bucket("test-bucket")
        assert result is True

    def test_delete_bucket(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        result = adapter.delete_bucket("test-bucket")
        assert result is True
        assert adapter.bucket_exists("test-bucket") is False

    def test_delete_nonexistent_bucket(self, adapter: MockStorageAdapter) -> None:
        result = adapter.delete_bucket("nonexistent")
        assert result is False

    def test_put_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        result = adapter.put("test-bucket", "file.txt", b"Hello World")
        assert result is True

    def test_put_object_auto_creates_bucket(self, adapter: MockStorageAdapter) -> None:
        result = adapter.put("auto-bucket", "file.txt", b"content")
        assert result is True
        assert adapter.bucket_exists("auto-bucket") is True

    def test_put_object_with_string_content(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        result = adapter.put("test-bucket", "file.txt", "Hello World")
        assert result is True

    def test_get_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"Hello World")
        obj = adapter.get("test-bucket", "file.txt")
        assert obj is not None
        assert obj.content == b"Hello World"
        assert obj.key == "file.txt"

    def test_get_nonexistent_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        result = adapter.get("test-bucket", "nonexistent.txt")
        assert result is None

    def test_get_content(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"Hello World")
        content = adapter.get_content("test-bucket", "file.txt")
        assert content == b"Hello World"

    def test_exists(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"content")
        assert adapter.exists("test-bucket", "file.txt") is True
        assert adapter.exists("test-bucket", "nonexistent.txt") is False

    def test_delete_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"content")
        result = adapter.delete("test-bucket", "file.txt")
        assert result is True
        assert adapter.exists("test-bucket", "file.txt") is False

    def test_delete_nonexistent_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        result = adapter.delete("test-bucket", "nonexistent.txt")
        assert result is False

    def test_copy_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("src-bucket")
        adapter.create_bucket("dst-bucket")
        adapter.put("src-bucket", "file.txt", b"content")

        result = adapter.copy("src-bucket", "file.txt", "dst-bucket", "copy.txt")
        assert result is True
        assert adapter.exists("dst-bucket", "copy.txt") is True
        assert adapter.get_content("dst-bucket", "copy.txt") == b"content"

    def test_copy_nonexistent_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("src-bucket")
        adapter.create_bucket("dst-bucket")
        result = adapter.copy("src-bucket", "nonexistent.txt", "dst-bucket", "copy.txt")
        assert result is False

    def test_move_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("src-bucket")
        adapter.create_bucket("dst-bucket")
        adapter.put("src-bucket", "file.txt", b"content")

        result = adapter.move("src-bucket", "file.txt", "dst-bucket", "moved.txt")
        assert result is True
        assert adapter.exists("dst-bucket", "moved.txt") is True
        assert adapter.exists("src-bucket", "file.txt") is False

    def test_list_objects(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file1.txt", b"content1")
        adapter.put("test-bucket", "file2.txt", b"content2")
        adapter.put("test-bucket", "docs/file3.txt", b"content3")

        objects = adapter.list_objects("test-bucket")
        assert len(objects) == 3

    def test_list_objects_with_prefix(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "docs/file1.txt", b"content1")
        adapter.put("test-bucket", "docs/file2.txt", b"content2")
        adapter.put("test-bucket", "images/file3.txt", b"content3")

        objects = adapter.list_objects("test-bucket", prefix="docs/")
        assert len(objects) == 2

    def test_list_objects_empty_bucket(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        objects = adapter.list_objects("test-bucket")
        assert objects == []

    def test_list_objects_nonexistent_bucket(self, adapter: MockStorageAdapter) -> None:
        objects = adapter.list_objects("nonexistent")
        assert objects == []

    def test_get_presigned_url(self, adapter: MockStorageAdapter) -> None:
        url = adapter.get_presigned_url("test-bucket", "file.txt", expires_in=3600)
        assert "test-bucket" in url
        assert "file.txt" in url
        assert "expires=3600" in url

    def test_put_with_metadata(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"content", metadata={"author": "test"})
        obj = adapter.get("test-bucket", "file.txt")
        assert obj is not None
        assert obj.metadata.get("author") == "test"

    def test_put_with_content_type(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.json", b"{}", content_type="application/json")
        obj = adapter.get("test-bucket", "file.json")
        assert obj is not None
        assert obj.content_type == "application/json"

    def test_object_size(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"Hello World")
        obj = adapter.get("test-bucket", "file.txt")
        assert obj is not None
        assert obj.size == 11

    def test_object_has_etag(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"content")
        obj = adapter.get("test-bucket", "file.txt")
        assert obj is not None
        assert obj.etag is not None

    def test_object_has_last_modified(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        adapter.put("test-bucket", "file.txt", b"content")
        obj = adapter.get("test-bucket", "file.txt")
        assert obj is not None
        assert obj.last_modified is not None

    def test_put_with_file_like_object(self, adapter: MockStorageAdapter) -> None:
        adapter.create_bucket("test-bucket")
        file_obj = BytesIO(b"stream content")
        result = adapter.put("test-bucket", "stream.txt", file_obj)
        assert result is True
        assert adapter.get_content("test-bucket", "stream.txt") == b"stream content"


class TestLocalFileAdapter:
    """Tests for LocalFileAdapter."""

    @pytest.fixture
    def temp_dir(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def adapter(self, temp_dir: str) -> LocalFileAdapter:
        return LocalFileAdapter(base_dir=temp_dir)

    def test_write_and_read_text_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("test.txt", "Hello World")
        content = adapter.read("test.txt")
        assert content == "Hello World"

    def test_write_and_read_binary_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("test.bin", b"\x00\x01\x02", binary=True)
        content = adapter.read("test.bin", binary=True)
        assert content == b"\x00\x01\x02"

    def test_write_creates_directories(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("subdir/nested/file.txt", "content")
        assert adapter.exists("subdir/nested/file.txt")

    def test_exists_true_for_existing_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("test.txt", "content")
        assert adapter.exists("test.txt") is True

    def test_exists_false_for_nonexistent_file(
        self, adapter: LocalFileAdapter, temp_dir: str
    ) -> None:
        assert adapter.exists("nonexistent.txt") is False

    def test_delete_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("test.txt", "content")
        result = adapter.delete("test.txt")
        assert result is True
        assert adapter.exists("test.txt") is False

    def test_delete_nonexistent_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        result = adapter.delete("nonexistent.txt")
        assert result is False

    def test_append_to_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("test.txt", "Hello")
        adapter.append("test.txt", " World")
        assert adapter.read("test.txt") == "Hello World"

    def test_copy_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("source.txt", "content")
        result = adapter.copy("source.txt", "dest.txt")
        assert result is True
        assert adapter.read("dest.txt") == "content"

    def test_copy_nonexistent_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        result = adapter.copy("nonexistent.txt", "dest.txt")
        assert result is False

    def test_move_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("source.txt", "content")
        result = adapter.move("source.txt", "dest.txt")
        assert result is True
        assert adapter.exists("source.txt") is False
        assert adapter.read("dest.txt") == "content"

    def test_get_info(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("test.txt", "Hello World")
        info = adapter.get_info("test.txt")
        assert info is not None
        assert info.name == "test.txt"
        assert info.size == 11

    def test_get_info_nonexistent_file(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        info = adapter.get_info("nonexistent.txt")
        assert info is None

    def test_create_dir(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        result = adapter.create_dir("newdir")
        assert result is True
        assert adapter.exists("newdir") or os.path.isdir(os.path.join(temp_dir, "newdir"))

    def test_create_nested_dirs(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        result = adapter.create_dir("a/b/c/d")
        assert result is True

    def test_remove_dir(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.create_dir("testdir")
        result = adapter.remove_dir("testdir")
        assert result is True

    def test_remove_dir_recursive(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.create_dir("testdir/subdir")
        adapter.write("testdir/file.txt", "content")
        result = adapter.remove_dir("testdir", recursive=True)
        assert result is True

    def test_list_dir(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("file1.txt", "content1")
        adapter.write("file2.txt", "content2")
        adapter.create_dir("subdir")
        adapter.write("subdir/file3.txt", "content3")

        files = adapter.list_dir("")
        assert len(files) == 2

    def test_list_dir_recursive(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        adapter.write("file1.txt", "content1")
        adapter.create_dir("subdir")
        adapter.write("subdir/file2.txt", "content2")

        files = adapter.list_dir("", recursive=True)
        assert len(files) == 2

    def test_tempfile(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        path = adapter.tempfile()
        assert adapter.exists(path) or os.path.exists(path)

    def test_tempdir(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        path = adapter.tempdir()
        assert os.path.isdir(path)

    def test_write_returns_bytes_written(self, adapter: LocalFileAdapter, temp_dir: str) -> None:
        count = adapter.write("test.txt", "Hello World")
        assert count == 11
