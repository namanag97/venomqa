from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TimeInfo:
    now: datetime
    timezone: str
    utc_offset_seconds: int
    is_dst: bool = False


@dataclass
class ScheduledTask:
    id: str
    name: str
    scheduled_at: datetime
    callback: Callable[[], Any] | None = None
    recurring: bool = False
    interval_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


class TimePort(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Get the current time."""
        ...

    @abstractmethod
    def now_utc(self) -> datetime:
        """Get the current UTC time."""
        ...

    @abstractmethod
    def now_iso(self) -> str:
        """Get the current time in ISO format."""
        ...

    @abstractmethod
    def timestamp(self) -> float:
        """Get the current Unix timestamp."""
        ...

    @abstractmethod
    def sleep(self, seconds: float) -> None:
        """Sleep for a specified number of seconds."""
        ...

    @abstractmethod
    def schedule(self, task: ScheduledTask) -> str:
        """Schedule a task to run at a specific time."""
        ...

    @abstractmethod
    def schedule_after(
        self, delay_seconds: float, callback: Callable[[], Any], name: str = ""
    ) -> str:
        """Schedule a callback to run after a delay."""
        ...

    @abstractmethod
    def schedule_every(
        self, interval_seconds: float, callback: Callable[[], Any], name: str = ""
    ) -> str:
        """Schedule a callback to run periodically."""
        ...

    @abstractmethod
    def cancel_schedule(self, task_id: str) -> bool:
        """Cancel a scheduled task."""
        ...

    @abstractmethod
    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        """Get all scheduled tasks."""
        ...

    @abstractmethod
    def get_time_info(self) -> TimeInfo:
        """Get information about the current time."""
        ...

    @abstractmethod
    def set_timezone(self, timezone: str) -> None:
        """Set the timezone for time operations."""
        ...

    @abstractmethod
    def get_timezone(self) -> str:
        """Get the current timezone."""
        ...

    @abstractmethod
    def parse(self, time_string: str, format: str | None = None) -> datetime:
        """Parse a time string into a datetime."""
        ...

    @abstractmethod
    def format(self, dt: datetime, format: str | None = None) -> str:
        """Format a datetime into a string."""
        ...

    @abstractmethod
    def add_seconds(self, dt: datetime, seconds: float) -> datetime:
        """Add seconds to a datetime."""
        ...

    @abstractmethod
    def add_minutes(self, dt: datetime, minutes: int) -> datetime:
        """Add minutes to a datetime."""
        ...

    @abstractmethod
    def add_hours(self, dt: datetime, hours: int) -> datetime:
        """Add hours to a datetime."""
        ...

    @abstractmethod
    def add_days(self, dt: datetime, days: int) -> datetime:
        """Add days to a datetime."""
        ...

    @abstractmethod
    def diff_seconds(self, start: datetime, end: datetime) -> float:
        """Get the difference between two datetimes in seconds."""
        ...
