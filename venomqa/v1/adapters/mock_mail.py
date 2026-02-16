"""Mock mail adapter for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import copy

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


@dataclass
class Email:
    """An email message."""

    id: str
    to: list[str]
    subject: str
    body: str
    from_addr: str = ""
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    sent_at: datetime = field(default_factory=datetime.now)


class MockMail:
    """In-memory mail service for testing.

    Implements Rollbackable protocol for checkpoint/restore.
    """

    def __init__(self) -> None:
        self._sent: list[Email] = []
        self._email_counter = 0

    def send(
        self,
        to: list[str] | str,
        subject: str,
        body: str,
        from_addr: str = "test@example.com",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> Email:
        """Send an email (store it in memory)."""
        self._email_counter += 1
        if isinstance(to, str):
            to = [to]

        email = Email(
            id=f"email_{self._email_counter}",
            to=to,
            subject=subject,
            body=body,
            from_addr=from_addr,
            cc=cc or [],
            bcc=bcc or [],
        )
        self._sent.append(email)
        return email

    def get_sent(self, to: str | None = None) -> list[Email]:
        """Get sent emails, optionally filtered by recipient."""
        if to is None:
            return list(self._sent)
        return [e for e in self._sent if to in e.to]

    def get_by_subject(self, subject: str) -> list[Email]:
        """Get emails by subject (contains match)."""
        return [e for e in self._sent if subject in e.subject]

    @property
    def sent_count(self) -> int:
        return len(self._sent)

    def clear(self) -> None:
        """Clear all sent emails."""
        self._sent.clear()

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current mail state."""
        return copy.deepcopy(self._sent)

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore mail state."""
        self._sent = copy.deepcopy(checkpoint)

    def observe(self) -> Observation:
        """Get current mail state."""
        return Observation(
            system="mail",
            data={
                "sent_count": self.sent_count,
                "recipients": list({addr for e in self._sent for addr in e.to}),
            },
            observed_at=datetime.now(),
        )
