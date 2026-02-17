"""Tests for mail adapters in VenomQA."""

from __future__ import annotations

from datetime import datetime

import pytest

from venomqa.adapters.mail import MockMailAdapter
from venomqa.ports.mail import Email, EmailAttachment


class TestMockMailAdapter:
    """Tests for MockMailAdapter."""

    @pytest.fixture
    def adapter(self) -> MockMailAdapter:
        return MockMailAdapter()

    @pytest.fixture
    def sample_email(self) -> Email:
        return Email(
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            subject="Test Subject",
            body="Test body content",
        )

    def test_adapter_initialization(self, adapter: MockMailAdapter) -> None:
        assert adapter.get_all_emails() == []
        assert adapter.health_check() is True

    def test_send_email_returns_message_id(
        self, adapter: MockMailAdapter, sample_email: Email
    ) -> None:
        message_id = adapter.send_email(sample_email)
        assert message_id is not None
        assert message_id.startswith("msg-")

    def test_send_email_stores_email(self, adapter: MockMailAdapter, sample_email: Email) -> None:
        adapter.send_email(sample_email)
        emails = adapter.get_all_emails()
        assert len(emails) == 1
        assert emails[0].subject == "Test Subject"

    def test_get_emails_to_filters_by_recipient(self, adapter: MockMailAdapter) -> None:
        email1 = Email(
            sender="a@example.com",
            recipients=["user1@example.com"],
            subject="Email 1",
            body="Body 1",
        )
        email2 = Email(
            sender="b@example.com",
            recipients=["user2@example.com"],
            subject="Email 2",
            body="Body 2",
        )
        adapter.send_email(email1)
        adapter.send_email(email2)

        result = adapter.get_emails_to("user1@example.com")
        assert len(result) == 1
        assert result[0].subject == "Email 1"

    def test_get_emails_from_filters_by_sender(self, adapter: MockMailAdapter) -> None:
        email1 = Email(
            sender="sender1@example.com",
            recipients=["user@example.com"],
            subject="From Sender 1",
            body="Body",
        )
        email2 = Email(
            sender="sender2@example.com",
            recipients=["user@example.com"],
            subject="From Sender 2",
            body="Body",
        )
        adapter.send_email(email1)
        adapter.send_email(email2)

        result = adapter.get_emails_from("sender1@example.com")
        assert len(result) == 1
        assert result[0].subject == "From Sender 1"

    def test_get_emails_with_subject_exact_match(self, adapter: MockMailAdapter) -> None:
        email1 = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Welcome",
            body="Body",
        )
        email2 = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Welcome User",
            body="Body",
        )
        adapter.send_email(email1)
        adapter.send_email(email2)

        result = adapter.get_emails_with_subject("Welcome", exact=True)
        assert len(result) == 1
        assert result[0].subject == "Welcome"

    def test_get_emails_with_subject_partial_match(self, adapter: MockMailAdapter) -> None:
        email1 = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Welcome",
            body="Body",
        )
        email2 = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Welcome User",
            body="Body",
        )
        adapter.send_email(email1)
        adapter.send_email(email2)

        result = adapter.get_emails_with_subject("Welcome", exact=False)
        assert len(result) == 2

    def test_get_latest_email_returns_most_recent(self, adapter: MockMailAdapter) -> None:
        email1 = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="First",
            body="Body",
        )
        email2 = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Second",
            body="Body",
        )
        adapter.send_email(email1)
        adapter.send_email(email2)

        latest = adapter.get_latest_email()
        assert latest is not None
        assert latest.subject == "Second"

    def test_get_latest_email_returns_none_when_empty(self, adapter: MockMailAdapter) -> None:
        result = adapter.get_latest_email()
        assert result is None

    def test_wait_for_email_finds_matching(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="sender@example.com",
            recipients=["user@example.com"],
            subject="Verification Code",
            body="Your code is 123456",
        )
        adapter.send_email(email)

        result = adapter.wait_for_email(to="user@example.com")
        assert result is not None
        assert result.subject == "Verification Code"

    def test_wait_for_email_with_multiple_criteria(self, adapter: MockMailAdapter) -> None:
        email1 = Email(
            sender="sender@example.com",
            recipients=["user1@example.com"],
            subject="Reset Password",
            body="Body 1",
        )
        email2 = Email(
            sender="sender@example.com",
            recipients=["user2@example.com"],
            subject="Reset Password",
            body="Body 2",
        )
        adapter.send_email(email1)
        adapter.send_email(email2)

        result = adapter.wait_for_email(
            to="user2@example.com",
            from_="sender@example.com",
            subject="Reset",
        )
        assert result is not None
        assert "user2@example.com" in result.recipients

    def test_wait_for_email_returns_none_when_no_match(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Test",
            body="Body",
        )
        adapter.send_email(email)

        result = adapter.wait_for_email(to="nonexistent@example.com")
        assert result is None

    def test_delete_all_emails(self, adapter: MockMailAdapter, sample_email: Email) -> None:
        adapter.send_email(sample_email)
        adapter.send_email(sample_email)
        assert len(adapter.get_all_emails()) == 2

        adapter.delete_all_emails()
        assert len(adapter.get_all_emails()) == 0

    def test_health_check_returns_true_by_default(self, adapter: MockMailAdapter) -> None:
        assert adapter.health_check() is True

    def test_set_healthy_changes_health_status(self, adapter: MockMailAdapter) -> None:
        adapter.set_healthy(False)
        assert adapter.health_check() is False

        adapter.set_healthy(True)
        assert adapter.health_check() is True

    def test_inject_email_with_custom_message_id(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Test",
            body="Body",
            message_id="custom-msg-id",
        )
        adapter.inject_email(email)

        emails = adapter.get_all_emails()
        assert len(emails) == 1
        assert emails[0].message_id == "custom-msg-id"

    def test_inject_email_auto_generates_message_id(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Test",
            body="Body",
        )
        adapter.inject_email(email)

        emails = adapter.get_all_emails()
        assert emails[0].message_id is not None
        assert emails[0].message_id.startswith("msg-")

    def test_email_with_attachments(self, adapter: MockMailAdapter) -> None:
        attachment = EmailAttachment(
            filename="report.pdf",
            content=b"PDF content here",
            content_type="application/pdf",
        )
        email = Email(
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            subject="Report Attached",
            body="Please find attached",
            attachments=[attachment],
        )
        adapter.send_email(email)

        emails = adapter.get_all_emails()
        assert len(emails[0].attachments) == 1
        assert emails[0].attachments[0].filename == "report.pdf"

    def test_email_with_cc_and_bcc(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="sender@example.com",
            recipients=["to@example.com"],
            subject="CC/BCC Test",
            body="Body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )
        adapter.send_email(email)

        result = adapter.get_emails_to("cc@example.com")
        assert len(result) == 1

    def test_multiple_emails_to_same_recipient(self, adapter: MockMailAdapter) -> None:
        for i in range(5):
            email = Email(
                sender="sender@example.com",
                recipients=["user@example.com"],
                subject=f"Email {i}",
                body=f"Body {i}",
            )
            adapter.send_email(email)

        result = adapter.get_emails_to("user@example.com")
        assert len(result) == 5

    def test_email_timestamp_is_set(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="a@example.com",
            recipients=["b@example.com"],
            subject="Test",
            body="Body",
        )
        adapter.send_email(email)

        emails = adapter.get_all_emails()
        assert emails[0].received_at is not None
        assert isinstance(emails[0].received_at, datetime)

    def test_html_email(self, adapter: MockMailAdapter) -> None:
        email = Email(
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            subject="HTML Email",
            body="Plain text",
            html_body="<html><body>HTML content</body></html>",
        )
        adapter.send_email(email)

        emails = adapter.get_all_emails()
        assert emails[0].html_body == "<html><body>HTML content</body></html>"
