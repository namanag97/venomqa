"""SMTP Mock adapter for email server testing.

This adapter provides an in-memory SMTP mock server for testing
email functionality without sending real emails.

Example:
    >>> from venomqa.adapters import SMTPMockAdapter
    >>> adapter = SMTPMockAdapter(port=2500)
    >>> adapter.start()
    >>> # Send email to localhost:2500
    >>> emails = adapter.get_emails()
"""

from __future__ import annotations

import email
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from typing import Any

from venomqa.ports.mail import Email, EmailAttachment, MailPort


@dataclass
class SMTPMockConfig:
    """Configuration for SMTP Mock adapter."""

    host: str = "localhost"
    port: int = 2500
    timeout: float = 10.0
    poll_interval: float = 0.5


class _MockSMTPChannel:
    """Mock SMTP channel for handling connections."""

    def __init__(self, server: Any, conn: Any, addr: Any) -> None:
        self.server = server
        self.conn = conn
        self.addr = addr
        self._buffer = b""
        self._mail_from = ""
        self._rcpt_to: list[str] = []
        self._in_data = False
        self._current_message = b""

    def handle_read(self) -> None:
        data = self.conn.recv(1024)
        if not data:
            return

        if self._in_data:
            self._handle_data(data)
        else:
            self._buffer += data
            while b"\r\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\r\n", 1)
                self._handle_command(line.decode())

    def _handle_command(self, line: str) -> None:
        parts = line.split(maxsplit=1)
        cmd = parts[0].upper() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "HELO" or cmd == "EHLO":
            self._send(f"250 {self.server.config.host} Hello")
        elif cmd == "MAIL":
            if arg.lower().startswith("from:"):
                self._mail_from = arg[5:].strip().strip("<>")
                self._send("250 OK")
        elif cmd == "RCPT":
            if arg.lower().startswith("to:"):
                self._rcpt_to.append(arg[3:].strip().strip("<>"))
                self._send("250 OK")
        elif cmd == "DATA":
            self._send("354 End data with <CR><LF>.<CR><LF>")
            self._in_data = True
        elif cmd == "QUIT":
            self._send("221 Bye")
            self.close()
        elif cmd == "RSET":
            self._mail_from = ""
            self._rcpt_to = []
            self._send("250 OK")
        elif cmd == "NOOP":
            self._send("250 OK")
        else:
            self._send("500 Unknown command")

    def _handle_data(self, data: bytes) -> None:
        self._current_message += data
        if b"\r\n.\r\n" in self._current_message:
            message = self._current_message.split(b"\r\n.\r\n")[0]
            self._process_message(message)
            self._in_data = False
            self._current_message = b""
            self._mail_from = ""
            self._rcpt_to = []
            self._send("250 OK Message accepted")

    def _process_message(self, raw_message: bytes) -> None:
        try:
            msg = email.message_from_bytes(raw_message)

            headers = {}
            for key in msg.keys():
                headers[key] = msg[key]

            _, sender = parseaddr(msg.get("From", ""))

            recipients = []
            to_header = msg.get("To", "")
            for addr in to_header.split(","):
                _, email_addr = parseaddr(addr.strip())
                if email_addr:
                    recipients.append(email_addr)

            cc = []
            cc_header = msg.get("Cc", "")
            for addr in cc_header.split(","):
                _, email_addr = parseaddr(addr.strip())
                if email_addr:
                    cc.append(email_addr)

            body = ""
            html_body = None
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        body = payload.decode() if payload else ""
                    elif content_type == "text/html":
                        payload = part.get_payload(decode=True)
                        html_body = payload.decode() if payload else ""
                    elif part.get_filename():
                        payload = part.get_payload(decode=True)
                        attachments.append(
                            EmailAttachment(
                                filename=part.get_filename(),
                                content=payload or b"",
                                content_type=content_type,
                            )
                        )
            else:
                payload = msg.get_payload(decode=True)
                body = payload.decode() if payload else ""

            email_obj = Email(
                sender=sender,
                recipients=recipients,
                subject=msg.get("Subject", ""),
                body=body,
                html_body=html_body,
                cc=cc,
                attachments=attachments,
                headers=headers,
                message_id=msg.get("Message-ID"),
                received_at=datetime.now(),
            )

            self.server._emails.append(email_obj)
        except Exception:
            pass

    def _send(self, message: str) -> None:
        self.conn.send((message + "\r\n").encode())

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


class SMTPMockAdapter(MailPort):
    """Adapter for in-memory SMTP mock server.

    This adapter provides a mock SMTP server that captures emails
    in memory for testing purposes.

    Attributes:
        config: Configuration for the mock server.

    Example:
        >>> adapter = SMTPMockAdapter(port=2500)
        >>> adapter.start()
        >>> # Send email via SMTP to localhost:2500
        >>> emails = adapter.get_emails_to("test@example.com")
        >>> adapter.stop()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2500,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the SMTP Mock adapter.

        Args:
            host: Hostname to bind to.
            port: Port to listen on.
            timeout: Operation timeout in seconds.
        """
        self.config = SMTPMockConfig(
            host=host,
            port=port,
            timeout=timeout,
        )
        self._emails: list[Email] = []
        self._running = False
        self._server_thread: threading.Thread | None = None
        self._socket: Any = None

    def start(self) -> None:
        """Start the mock SMTP server."""
        import socket

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.config.host, self.config.port))
        self._socket.listen(5)
        self._socket.settimeout(1.0)
        self._running = True

        def accept_loop() -> None:
            while self._running:
                try:
                    conn, addr = self._socket.accept()
                    channel = _MockSMTPChannel(self, conn, addr)
                    conn.send(b"220 smtp.mock ESMTP Mock SMTP Server\r\n")

                    def handle_client(
                        c: Any = conn,
                        ch: _MockSMTPChannel = channel,
                    ) -> None:
                        c.settimeout(30.0)
                        while self._running:
                            try:
                                data = c.recv(1024)
                                if not data:
                                    break
                                ch.handle_read()
                            except TimeoutError:
                                break
                            except Exception:
                                break
                        c.close()

                    threading.Thread(target=handle_client, daemon=True).start()
                except TimeoutError:
                    continue
                except Exception:
                    break

        self._server_thread = threading.Thread(target=accept_loop, daemon=True)
        self._server_thread.start()

    def stop(self) -> None:
        """Stop the mock SMTP server."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass

    def get_all_emails(self) -> list[Email]:
        """Retrieve all captured emails.

        Returns:
            List of all captured email messages.
        """
        return list(self._emails)

    def get_emails_to(self, recipient: str) -> list[Email]:
        """Retrieve emails sent to a specific recipient.

        Args:
            recipient: Email address to filter by.

        Returns:
            List of emails sent to the recipient.
        """
        return [e for e in self._emails if recipient in e.recipients]

    def get_emails_from(self, sender: str) -> list[Email]:
        """Retrieve emails from a specific sender.

        Args:
            sender: Email address to filter by.

        Returns:
            List of emails from the sender.
        """
        return [e for e in self._emails if sender in e.sender]

    def get_emails_with_subject(self, subject: str, exact: bool = False) -> list[Email]:
        """Retrieve emails matching a subject.

        Args:
            subject: Subject to search for.
            exact: If True, match exact subject; otherwise partial match.

        Returns:
            List of matching emails.
        """
        if exact:
            return [e for e in self._emails if e.subject == subject]
        return [e for e in self._emails if subject.lower() in e.subject.lower()]

    def get_latest_email(self, timeout: float = 10.0) -> Email | None:
        """Wait for and return the latest email.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            The latest email or None if timeout.
        """
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
        """Wait for an email matching the given criteria.

        Args:
            to: Recipient email address to match.
            from_: Sender email address to match.
            subject: Subject pattern to match.
            timeout: Maximum time to wait in seconds.

        Returns:
            Matching email or None if timeout.
        """
        start = time.time()
        seen_count = 0

        while time.time() - start < timeout:
            emails = self._emails[seen_count:]
            seen_count = len(self._emails)

            for email_obj in emails:
                if to and to not in email_obj.recipients:
                    continue
                if from_ and from_ not in email_obj.sender:
                    continue
                if subject and subject.lower() not in email_obj.subject.lower():
                    continue
                return email_obj

            time.sleep(self.config.poll_interval)

        return None

    def delete_all_emails(self) -> None:
        """Delete all captured emails."""
        self._emails.clear()

    def send_email(self, email: Email) -> str:
        """Send an email (stores in memory).

        Args:
            email: Email to send.

        Returns:
            Message ID of the sent email.
        """
        email.received_at = datetime.now()
        self._emails.append(email)
        return email.message_id or ""

    def health_check(self) -> bool:
        """Check if the mock server is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        return self._running

    def count_emails(self) -> int:
        """Get the number of captured emails.

        Returns:
            Number of emails.
        """
        return len(self._emails)
