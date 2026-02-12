"""
Celery worker tasks for the Full-Featured App.

These tasks demonstrate background job processing that VenomQA can test.
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from celery import Celery

SMTP_HOST = os.getenv("SMTP_HOST", "mailhog")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@app.example.com")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

celery_app = Celery(
    "workers",
    broker=CELERY_BROKER_URL,
    backend=CELERY_BROKER_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(
    self,
    to: str,
    subject: str,
    body: str,
    html_body: str | None = None,
):
    """Send an email via SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_FROM
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USER and SMTP_PASSWORD:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, to, msg.as_string())

        return {
            "success": True,
            "to": to,
            "subject": subject,
            "sent_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        self.retry(exc=e)


@celery_app.task(bind=True)
def process_order_task(self, order_id: int):
    """Process an order in the background."""
    import time

    self.update_state(state="PROCESSING", meta={"order_id": order_id, "step": "validating"})
    time.sleep(2)

    self.update_state(state="PROCESSING", meta={"order_id": order_id, "step": "charging_payment"})
    time.sleep(1)

    self.update_state(state="PROCESSING", meta={"order_id": order_id, "step": "fulfilling"})
    time.sleep(2)

    self.update_state(state="PROCESSING", meta={"order_id": order_id, "step": "shipping"})
    time.sleep(1)

    return {
        "order_id": order_id,
        "status": "completed",
        "processed_at": datetime.utcnow().isoformat(),
        "steps": ["validated", "charged", "fulfilled", "shipped"],
    }


@celery_app.task(bind=True)
def generate_report_task(self, report_type: str):
    """Generate a report in the background."""
    import time

    self.update_state(state="GENERATING", meta={"report_type": report_type, "progress": 0})

    for progress in range(0, 101, 20):
        self.update_state(
            state="GENERATING", meta={"report_type": report_type, "progress": progress}
        )
        time.sleep(0.5)

    report_data = {
        "sales": {
            "total_sales": 150000.00,
            "items_sold": 1234,
            "top_products": ["Product A", "Product B", "Product C"],
        },
        "inventory": {
            "total_items": 5000,
            "low_stock": 23,
            "out_of_stock": 5,
        },
        "users": {
            "total_users": 892,
            "active_users": 456,
            "new_users_today": 12,
        },
    }

    return {
        "report_type": report_type,
        "data": report_data.get(report_type, {}),
        "generated_at": datetime.utcnow().isoformat(),
    }


@celery_app.task
def cleanup_expired_sessions():
    """Cleanup expired sessions (scheduled task)."""
    return {
        "cleaned": 42,
        "cleaned_at": datetime.utcnow().isoformat(),
    }


@celery_app.task
def send_notification(user_id: int, message: str, notification_type: str = "info"):
    """Send a notification to a user."""
    return {
        "user_id": user_id,
        "message": message,
        "type": notification_type,
        "sent_at": datetime.utcnow().isoformat(),
    }


@celery_app.task
def batch_process_items(item_ids: list[int]):
    """Process multiple items in batch."""
    results = []
    for item_id in item_ids:
        results.append(
            {
                "item_id": item_id,
                "processed": True,
                "processed_at": datetime.utcnow().isoformat(),
            }
        )
    return {
        "total": len(item_ids),
        "results": results,
    }


@celery_app.task(bind=True, max_retries=5)
def retryable_task(self, should_fail: bool = False):
    """Task that can be configured to fail for testing retry logic."""
    if should_fail and self.request.retries < 3:
        raise Exception("Intentional failure for retry testing")

    return {
        "success": True,
        "retries": self.request.retries,
        "completed_at": datetime.utcnow().isoformat(),
    }


@celery_app.task
def long_running_task(duration_seconds: int = 60):
    """A long-running task for testing timeouts."""
    import time

    time.sleep(duration_seconds)
    return {
        "completed": True,
        "duration": duration_seconds,
        "completed_at": datetime.utcnow().isoformat(),
    }
