"""Mock Mail adapter for testing.

This adapter provides an in-memory email mock for testing purposes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from venomqa.ports.mail import Email, MailPort


@dataclass
class MockMailConfig:
    """Configuration for Mock Mail adapter."""

    poll_interval: float = 0.5


class MockMailAdapter(MailPort):
    """In-memory mock mail adapter for testing.

    Attributes:
        config: Configuration for the mock mail.
    """

    def __init__(self, poll_interval: float = 0.5) -> None:
        self.config = MockMailConfig(poll_interval=poll_interval)
        self._emails: list[Email] = []

    def get_all_emails(self) -> list[Email]:
        return list(self._emails)

    def get_emails_to(self, recipient: str) -> list[Email]:
        return [e for e in self._emails if recipient in e.recipients]

    def get_emails_from(self, sender: str) -> list[Email]:
        return [e for e in self._emails if sender in e.sender]

    def get_emails_with_subject(self, subject: str, exact: bool = False) -> list[Email]:
        if exact:
            return [e for e in self._emails if e.subject == subject]
        return [e for e in self._emails if subject.lower() in e.subject.lower()]

    def get_latest_email(self, timeout: float = 10.0) -> Email | None:
        start = time.time()
        initial_count = len(self._emails)
        while time.time() - start < timeout:
            if len(self._emails) > initial_count:
                return self._emails[-1]
            time.sleep(self.config.poll_interval)
        return self._emails[-1] if self._emails else None

    def wait_for_email(
        self,
        to: str | None = None,
        from_: str | None = None,
        subject: str | None = None,
        timeout: float = 30.0,
    ) -> Email | None:
        start = time.time()
        seen_count = 0
        while time.time() - start < timeout:
            emails = self._emails[seen_count:]
            seen_count = len(self._emails)
            for email in emails:
                if to and to not in email.recipients:
                    continue
                if from_ and from_ not in email.sender:
                    continue
                if subject and subject.lower() not in email.subject.lower():
                    continue
                return email
            time.sleep(self.config.poll_interval)
        return None

    def delete_all_emails(self) -> None:
        self._emails.clear()

    def send_email(self, email: Email) -> str:
        email.received_at = datetime.now()
        self._emails.append(email)
        return email.message_id or ""

    def health_check(self) -> bool:
        return True
