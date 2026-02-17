"""Unit tests for mock adapters."""

from datetime import datetime

import pytest

from venomqa.v1.adapters.mock_mail import MockMail
from venomqa.v1.adapters.mock_queue import MockQueue
from venomqa.v1.adapters.mock_storage import MockStorage
from venomqa.v1.adapters.mock_time import MockTime


class TestMockQueue:
    def test_push_and_pop(self):
        queue = MockQueue()
        queue.push({"task": "send_email"})
        queue.push({"task": "process_order"})

        assert queue.pending_count == 2

        msg = queue.pop()
        assert msg is not None
        assert msg.payload["task"] == "send_email"
        assert msg.processed

        assert queue.pending_count == 1
        assert queue.processed_count == 1

    def test_peek(self):
        queue = MockQueue()
        queue.push("test")

        msg = queue.peek()
        assert msg is not None
        assert not msg.processed
        assert queue.pending_count == 1

    def test_checkpoint_rollback(self):
        queue = MockQueue()
        queue.push("msg1")

        cp = queue.checkpoint("before_msg2")

        queue.push("msg2")
        queue.push("msg3")
        assert queue.pending_count == 3

        queue.rollback(cp)
        assert queue.pending_count == 1

    def test_observe(self):
        queue = MockQueue(name="tasks")
        queue.push("a")
        queue.push("b")
        queue.pop()

        obs = queue.observe()
        assert obs.system == "queue:tasks"
        assert obs.data["pending"] == 1
        assert obs.data["processed"] == 1


class TestMockMail:
    def test_send_and_get(self):
        mail = MockMail()
        mail.send("user@example.com", "Welcome", "Hello!")
        mail.send(["a@ex.com", "b@ex.com"], "Update", "News")

        assert mail.sent_count == 2

        sent = mail.get_sent("user@example.com")
        assert len(sent) == 1
        assert sent[0].subject == "Welcome"

    def test_get_by_subject(self):
        mail = MockMail()
        mail.send("a@ex.com", "Password Reset", "Click here")
        mail.send("b@ex.com", "Welcome", "Hello")

        found = mail.get_by_subject("Password")
        assert len(found) == 1

    def test_checkpoint_rollback(self):
        mail = MockMail()
        mail.send("a@ex.com", "Email 1", "Body")

        cp = mail.checkpoint("after_first")

        mail.send("b@ex.com", "Email 2", "Body")
        assert mail.sent_count == 2

        mail.rollback(cp)
        assert mail.sent_count == 1

    def test_observe(self):
        mail = MockMail()
        mail.send("user@example.com", "Test", "Body")

        obs = mail.observe()
        assert obs.system == "mail"
        assert obs.data["sent_count"] == 1
        assert "user@example.com" in obs.data["recipients"]


class TestMockStorage:
    def test_put_and_get(self):
        storage = MockStorage()
        storage.put("files/test.txt", b"content")

        file = storage.get("files/test.txt")
        assert file is not None
        assert file.content == b"content"

    def test_string_content(self):
        storage = MockStorage()
        storage.put("file.txt", "text content")

        file = storage.get("file.txt")
        assert file.content == b"text content"

    def test_delete(self):
        storage = MockStorage()
        storage.put("file.txt", b"data")
        assert storage.exists("file.txt")

        storage.delete("file.txt")
        assert not storage.exists("file.txt")

    def test_list(self):
        storage = MockStorage()
        storage.put("a/1.txt", b"")
        storage.put("a/2.txt", b"")
        storage.put("b/1.txt", b"")

        files = storage.list("a/")
        assert len(files) == 2

    def test_checkpoint_rollback(self):
        storage = MockStorage()
        storage.put("file1.txt", b"data1")

        cp = storage.checkpoint("before_file2")

        storage.put("file2.txt", b"data2")
        assert storage.file_count == 2

        storage.rollback(cp)
        assert storage.file_count == 1
        assert not storage.exists("file2.txt")

    def test_observe(self):
        storage = MockStorage(bucket="uploads")
        storage.put("a.txt", b"123")
        storage.put("b.txt", b"456789")

        obs = storage.observe()
        assert obs.system == "storage:uploads"
        assert obs.data["file_count"] == 2
        assert obs.data["total_size"] == 9


class TestMockTime:
    def test_freeze(self):
        mock_time = MockTime()
        frozen_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_time.freeze(frozen_at)

        assert mock_time.now == frozen_at

    def test_advance(self):
        mock_time = MockTime()
        mock_time.freeze(datetime(2024, 1, 1, 12, 0, 0))

        new_time = mock_time.advance(hours=2, minutes=30)
        assert new_time == datetime(2024, 1, 1, 14, 30, 0)

    def test_advance_requires_frozen(self):
        mock_time = MockTime()
        with pytest.raises(RuntimeError):
            mock_time.advance(hours=1)

    def test_set(self):
        mock_time = MockTime()
        mock_time.set(datetime(2024, 6, 15, 10, 0, 0))
        assert mock_time.now == datetime(2024, 6, 15, 10, 0, 0)

    def test_checkpoint_rollback(self):
        mock_time = MockTime()
        mock_time.freeze(datetime(2024, 1, 1, 0, 0, 0))

        cp = mock_time.checkpoint("start")

        mock_time.advance(days=5)
        assert mock_time.now == datetime(2024, 1, 6, 0, 0, 0)

        mock_time.rollback(cp)
        assert mock_time.now == datetime(2024, 1, 1, 0, 0, 0)

    def test_observe(self):
        mock_time = MockTime()
        mock_time.freeze(datetime(2024, 1, 1, 12, 0, 0))

        obs = mock_time.observe()
        assert obs.system == "time"
        assert obs.data["frozen"]
        assert "2024-01-01" in obs.data["current"]
