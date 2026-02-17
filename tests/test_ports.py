"""Tests for all Port interfaces in VenomQA.

These tests use mocks to test the port interfaces independently
of any concrete implementations.
"""

from __future__ import annotations

from abc import ABC
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from venomqa.ports import (
    CacheEntry,
    CachePort,
    CacheStats,
    ClientPort,
    ColumnInfo,
    DatabasePort,
    Email,
    EmailAttachment,
    FileInfo,
    FilePort,
    IndexedDocument,
    JobInfo,
    JobResult,
    JobStatus,
    MailPort,
    MockEndpoint,
    MockPort,
    MockResponse,
    NotificationPort,
    PushNotification,
    QueryResult,
    QueuePort,
    RecordedRequest,
    Request,
    RequestBuilder,
    Response,
    ScheduledTask,
    SearchIndex,
    SearchPort,
    SearchResult,
    SMSMessage,
    StateEntry,
    StatePort,
    StateQuery,
    StorageObject,
    StoragePort,
    TableInfo,
    TimeInfo,
    TimePort,
    WebhookPort,
    WebhookRequest,
    WebhookResponse,
    WebhookSubscription,
    WebSocketPort,
    WSConnection,
    WSMessage,
)


class TestPortInterfacesExist:
    """Test that all port interfaces are properly defined as ABCs."""

    def test_client_port_is_abstract(self) -> None:
        assert issubclass(ClientPort, ABC)
        with pytest.raises(TypeError):
            ClientPort()

    def test_state_port_is_abstract(self) -> None:
        assert issubclass(StatePort, ABC)
        with pytest.raises(TypeError):
            StatePort()

    def test_database_port_is_abstract(self) -> None:
        assert issubclass(DatabasePort, ABC)
        with pytest.raises(TypeError):
            DatabasePort()

    def test_time_port_is_abstract(self) -> None:
        assert issubclass(TimePort, ABC)
        with pytest.raises(TypeError):
            TimePort()

    def test_file_port_is_abstract(self) -> None:
        assert issubclass(FilePort, ABC)
        with pytest.raises(TypeError):
            FilePort()

    def test_storage_port_is_abstract(self) -> None:
        assert issubclass(StoragePort, ABC)
        with pytest.raises(TypeError):
            StoragePort()

    def test_websocket_port_is_abstract(self) -> None:
        assert issubclass(WebSocketPort, ABC)
        with pytest.raises(TypeError):
            WebSocketPort()

    def test_queue_port_is_abstract(self) -> None:
        assert issubclass(QueuePort, ABC)
        with pytest.raises(TypeError):
            QueuePort()

    def test_mail_port_is_abstract(self) -> None:
        assert issubclass(MailPort, ABC)
        with pytest.raises(TypeError):
            MailPort()

    def test_concurrency_port_is_abstract(self) -> None:
        from venomqa.ports.concurrency import ConcurrencyPort

        assert issubclass(ConcurrencyPort, ABC)
        with pytest.raises(TypeError):
            ConcurrencyPort()

    def test_cache_port_is_abstract(self) -> None:
        assert issubclass(CachePort, ABC)
        with pytest.raises(TypeError):
            CachePort()

    def test_search_port_is_abstract(self) -> None:
        assert issubclass(SearchPort, ABC)
        with pytest.raises(TypeError):
            SearchPort()

    def test_notification_port_is_abstract(self) -> None:
        assert issubclass(NotificationPort, ABC)
        with pytest.raises(TypeError):
            NotificationPort()

    def test_webhook_port_is_abstract(self) -> None:
        assert issubclass(WebhookPort, ABC)
        with pytest.raises(TypeError):
            WebhookPort()

    def test_mock_port_is_abstract(self) -> None:
        assert issubclass(MockPort, ABC)
        with pytest.raises(TypeError):
            MockPort()


class TestRequestDataclass:
    """Tests for Request dataclass."""

    def test_request_creation_minimal(self) -> None:
        request = Request(method="GET", url="https://api.example.com/users")
        assert request.method == "GET"
        assert request.url == "https://api.example.com/users"
        assert request.headers == {}
        assert request.params == {}
        assert request.body is None
        assert request.timeout == 30.0

    def test_request_creation_full(self) -> None:
        request = Request(
            method="POST",
            url="https://api.example.com/users",
            headers={"Content-Type": "application/json"},
            params={"page": "1"},
            json_body={"name": "John"},
            timeout=60.0,
            cookies={"session": "abc123"},
        )
        assert request.method == "POST"
        assert request.headers["Content-Type"] == "application/json"
        assert request.params["page"] == "1"
        assert request.json_body == {"name": "John"}
        assert request.timeout == 60.0
        assert request.cookies["session"] == "abc123"


class TestResponseDataclass:
    """Tests for Response dataclass."""

    def test_response_ok_property_2xx(self) -> None:
        for code in [200, 201, 202, 204, 299]:
            response = Response(status_code=code, headers={}, body=b"")
            assert response.ok is True

    def test_response_ok_property_non_2xx(self) -> None:
        for code in [100, 300, 400, 404, 500, 503]:
            response = Response(status_code=code, headers={}, body=b"")
            assert response.ok is False

    def test_response_json_method_with_json_data(self) -> None:
        response = Response(
            status_code=200,
            headers={},
            body=b"",
            json_data={"id": 1, "name": "Test"},
        )
        assert response.json() == {"id": 1, "name": "Test"}

    def test_response_json_method_parses_text(self) -> None:
        response = Response(
            status_code=200,
            headers={},
            body=b"",
            text='{"id": 2, "name": "Test2"}',
        )
        result = response.json()
        assert result == {"id": 2, "name": "Test2"}


class TestRequestBuilderDataclass:
    """Tests for RequestBuilder dataclass."""

    def test_request_builder_defaults(self) -> None:
        builder = RequestBuilder()
        assert builder.base_url == ""
        assert builder.default_headers == {}
        assert builder.default_params == {}
        assert builder.default_timeout == 30.0
        assert builder.auth_token is None

    def test_request_builder_with_values(self) -> None:
        builder = RequestBuilder(
            base_url="https://api.example.com",
            default_headers={"X-API-Key": "secret"},
            auth_token="mytoken",
        )
        assert builder.base_url == "https://api.example.com"
        assert builder.default_headers["X-API-Key"] == "secret"
        assert builder.auth_token == "mytoken"


class TestStateEntryDataclass:
    """Tests for StateEntry dataclass."""

    def test_state_entry_creation(self) -> None:
        entry = StateEntry(
            key="user:1",
            value={"name": "John"},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert entry.key == "user:1"
        assert entry.value == {"name": "John"}
        assert entry.ttl_seconds is None

    def test_state_entry_is_expired_no_ttl(self) -> None:
        entry = StateEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert entry.is_expired() is False

    def test_state_entry_is_expired_with_ttl_not_expired(self) -> None:
        entry = StateEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            ttl_seconds=3600,
        )
        assert entry.is_expired() is False


class TestStateQueryDataclass:
    """Tests for StateQuery dataclass."""

    def test_state_query_defaults(self) -> None:
        query = StateQuery()
        assert query.key_prefix is None
        assert query.key_pattern is None
        assert query.metadata_filter == {}
        assert query.limit == 100
        assert query.offset == 0

    def test_state_query_with_filters(self) -> None:
        query = StateQuery(
            key_prefix="user:",
            metadata_filter={"type": "premium"},
            limit=50,
        )
        assert query.key_prefix == "user:"
        assert query.metadata_filter["type"] == "premium"
        assert query.limit == 50


class TestJobInfoDataclass:
    """Tests for JobInfo dataclass."""

    def test_job_info_creation(self) -> None:
        job = JobInfo(
            id="job-123",
            name="process_data",
            queue="default",
            status=JobStatus.PENDING,
        )
        assert job.id == "job-123"
        assert job.status == JobStatus.PENDING
        assert job.retries == 0

    def test_job_status_enum_values(self) -> None:
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


class TestJobResultDataclass:
    """Tests for JobResult dataclass."""

    def test_job_result_success(self) -> None:
        result = JobResult(
            job_id="job-123",
            success=True,
            result={"processed": 100},
            duration=150.5,
        )
        assert result.success is True
        assert result.result == {"processed": 100}
        assert result.error is None

    def test_job_result_failure(self) -> None:
        result = JobResult(
            job_id="job-456",
            success=False,
            error="Connection timeout",
        )
        assert result.success is False
        assert result.error == "Connection timeout"


class TestEmailDataclass:
    """Tests for Email dataclass."""

    def test_email_creation(self) -> None:
        email = Email(
            sender="test@example.com",
            recipients=["user@example.com"],
            subject="Test Subject",
            body="Test body content",
        )
        assert email.recipients == ["user@example.com"]
        assert email.subject == "Test Subject"
        assert email.cc == []
        assert email.attachments == []

    def test_email_with_attachments(self) -> None:
        attachment = EmailAttachment(
            filename="report.pdf",
            content=b"pdf content",
            content_type="application/pdf",
        )
        email = Email(
            sender="test@example.com",
            recipients=["user@example.com"],
            subject="Report",
            body="See attached",
            attachments=[attachment],
        )
        assert len(email.attachments) == 1
        assert email.attachments[0].filename == "report.pdf"


class TestCacheEntryDataclass:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self) -> None:
        entry = CacheEntry(
            key="user:1",
            value={"name": "John"},
            created_at=datetime.now(),
            ttl=3600,
        )
        assert entry.key == "user:1"
        assert entry.ttl == 3600


class TestCacheStatsDataclass:
    """Tests for CacheStats dataclass."""

    def test_cache_stats_creation(self) -> None:
        stats = CacheStats(
            hits=1000,
            misses=200,
            hit_rate=0.83,
            size=500,
        )
        assert stats.hits == 1000
        assert stats.misses == 200
        assert stats.hit_rate == 0.83


class TestTaskInfoDataclass:
    """Tests for TaskInfo dataclass."""

    def test_task_info_creation(self) -> None:
        from venomqa.ports.concurrency import TaskInfo

        task = TaskInfo(
            id="task-123",
            name="process_item",
            status="running",
        )
        assert task.id == "task-123"
        assert task.status == "running"
        assert task.progress == 0.0


class TestTaskResultDataclass:
    """Tests for TaskResult dataclass."""

    def test_task_result_success(self) -> None:
        from venomqa.ports.concurrency import TaskResult

        result = TaskResult(
            task_id="task-123",
            success=True,
            result="completed",
            duration_ms=100.0,
        )
        assert result.success is True
        assert result.result == "completed"


class TestTimeInfoDataclass:
    """Tests for TimeInfo dataclass."""

    def test_time_info_creation(self) -> None:
        info = TimeInfo(
            now=datetime.now(),
            timezone="UTC",
            utc_offset_seconds=0,
        )
        assert info.timezone == "UTC"
        assert info.utc_offset_seconds == 0


class TestScheduledTaskDataclass:
    """Tests for ScheduledTask dataclass."""

    def test_scheduled_task_creation(self) -> None:
        task = ScheduledTask(
            id="sched-123",
            name="cleanup",
            scheduled_at=datetime.now(),
        )
        assert task.id == "sched-123"
        assert task.recurring is False
        assert task.enabled is True


class TestFileInfoDataclass:
    """Tests for FileInfo dataclass."""

    def test_file_info_creation(self) -> None:
        info = FileInfo(
            name="test.txt",
            path="/tmp/test.txt",
            size=1024,
            content_type="text/plain",
            modified_at=datetime.now(),
        )
        assert info.name == "test.txt"
        assert info.size == 1024


class TestStorageObjectDataclass:
    """Tests for StorageObject dataclass."""

    def test_storage_object_creation(self) -> None:
        obj = StorageObject(
            key="documents/report.pdf",
            bucket="uploads",
            content=b"pdf content",
        )
        assert obj.key == "documents/report.pdf"
        assert obj.bucket == "uploads"


class TestWSMessageDataclass:
    """Tests for WSMessage dataclass."""

    def test_ws_message_text(self) -> None:
        msg = WSMessage(data="Hello", type="text")
        assert msg.data == "Hello"
        assert msg.type == "text"

    def test_ws_message_binary(self) -> None:
        msg = WSMessage(data=b"\x00\x01", type="binary")
        assert msg.data == b"\x00\x01"
        assert msg.type == "binary"


class TestWSConnectionDataclass:
    """Tests for WSConnection dataclass."""

    def test_ws_connection_creation(self) -> None:
        conn = WSConnection(
            id="conn-123",
            url="wss://example.com/ws",
            connected_at=datetime.now(),
        )
        assert conn.id == "conn-123"
        assert conn.is_connected is True


class TestWebhookRequestDataclass:
    """Tests for WebhookRequest dataclass."""

    def test_webhook_request_creation(self) -> None:
        req = WebhookRequest(
            id="req-123",
            method="POST",
            url="https://example.com/webhook",
        )
        assert req.method == "POST"
        assert req.headers == {}


class TestWebhookResponseDataclass:
    """Tests for WebhookResponse dataclass."""

    def test_webhook_response_defaults(self) -> None:
        resp = WebhookResponse()
        assert resp.status_code == 200
        assert resp.body == ""


class TestWebhookSubscriptionDataclass:
    """Tests for WebhookSubscription dataclass."""

    def test_webhook_subscription_creation(self) -> None:
        sub = WebhookSubscription(
            id="sub-123",
            url="https://client.com/callback",
            events=["order.created", "order.updated"],
        )
        assert sub.url == "https://client.com/callback"
        assert "order.created" in sub.events


class TestMockEndpointDataclass:
    """Tests for MockEndpoint dataclass."""

    def test_mock_endpoint_creation(self) -> None:
        endpoint = MockEndpoint(
            path="/api/users",
            method="GET",
        )
        assert endpoint.path == "/api/users"
        assert endpoint.method == "GET"


class TestMockResponseDataclass:
    """Tests for MockResponse dataclass."""

    def test_mock_response_defaults(self) -> None:
        resp = MockResponse(status_code=200)
        assert resp.status_code == 200
        assert resp.headers == {}


class TestRecordedRequestDataclass:
    """Tests for RecordedRequest dataclass."""

    def test_recorded_request_creation(self) -> None:
        req = RecordedRequest(
            id="rec-123",
            method="POST",
            path="/users",
        )
        assert req.method == "POST"
        assert req.path == "/users"


class TestPortMethodSignatures:
    """Test that port methods have expected signatures using mocks."""

    def test_client_port_methods_exist(self) -> None:
        mock_port = MagicMock(spec=ClientPort)
        mock_port.get("https://example.com")
        mock_port.post("https://example.com", json={})
        mock_port.put("https://example.com")
        mock_port.patch("https://example.com")
        mock_port.delete("https://example.com")
        mock_port.set_base_url("https://api.example.com")
        mock_port.set_auth_token("token")
        assert mock_port.get.called
        assert mock_port.post.called

    def test_state_port_methods_exist(self) -> None:
        mock_port = MagicMock(spec=StatePort)
        mock_port.get("key")
        mock_port.set("key", "value")
        mock_port.delete("key")
        mock_port.exists("key")
        mock_port.keys("*")
        assert mock_port.get.called

    def test_cache_port_methods_exist(self) -> None:
        mock_port = MagicMock(spec=CachePort)
        mock_port.get("key")
        mock_port.set("key", "value", ttl=60)
        mock_port.delete("key")
        mock_port.exists("key")
        mock_port.get_stats()
        assert mock_port.get.called

    def test_queue_port_methods_exist(self) -> None:
        mock_port = MagicMock(spec=QueuePort)
        mock_port.get_job("job-id")
        mock_port.cancel_job("job-id")
        mock_port.get_queue_length("default")
        assert mock_port.get_job.called

    def test_mail_port_methods_exist(self) -> None:
        mock_port = MagicMock(spec=MailPort)
        mock_port.get_all_emails()
        mock_port.wait_for_email(to="user@example.com")
        assert mock_port.get_all_emails.called


class TestDatabasePortDataclasses:
    """Tests for database-related dataclasses."""

    def test_column_info_creation(self) -> None:
        col = ColumnInfo(
            name="id",
            data_type="INTEGER",
            nullable=False,
            primary_key=True,
        )
        assert col.name == "id"
        assert col.primary_key is True

    def test_table_info_creation(self) -> None:
        cols = [ColumnInfo(name="id", data_type="INTEGER", nullable=False)]
        table = TableInfo(name="users", columns=cols)
        assert table.name == "users"
        assert len(table.columns) == 1

    def test_query_result_creation(self) -> None:
        result = QueryResult(
            rows=[{"id": 1}, {"id": 2}],
            affected_rows=2,
        )
        assert len(result.rows) == 2
        assert result.affected_rows == 2


class TestSearchPortDataclasses:
    """Tests for search-related dataclasses."""

    def test_indexed_document_creation(self) -> None:
        doc = IndexedDocument(
            id="doc-1",
            content="Hello world",
            title="Test Document",
        )
        assert doc.id == "doc-1"
        assert doc.title == "Test Document"

    def test_search_result_creation(self) -> None:
        result = SearchResult(
            id="doc-1",
            score=0.95,
        )
        assert result.score == 0.95

    def test_search_index_creation(self) -> None:
        index = SearchIndex(name="products", document_count=100)
        assert index.name == "products"
        assert index.document_count == 100


class TestNotificationPortDataclasses:
    """Tests for notification-related dataclasses."""

    def test_push_notification_creation(self) -> None:
        notif = PushNotification(
            token="device-token-123",
            title="New Message",
            body="You have a new message",
        )
        assert notif.token == "device-token-123"
        assert notif.title == "New Message"

    def test_sms_message_creation(self) -> None:
        sms = SMSMessage(
            to="+1234567890",
            body="Your code is 123456",
        )
        assert sms.to == "+1234567890"
        assert sms.body == "Your code is 123456"
