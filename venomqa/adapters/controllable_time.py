"""Controllable Time adapter for deterministic testing.

This adapter provides controllable time for testing time-dependent
functionality without waiting for real time to pass.

Example:
    >>> from venomqa.adapters import ControllableTimeAdapter
    >>> adapter = ControllableTimeAdapter()
    >>> adapter.freeze()
    >>> adapter.advance(hours=1)
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from venomqa.ports.time import ScheduledTask, TimeInfo, TimePort


@dataclass
class ControllableTimeConfig:
    """Configuration for Controllable Time adapter."""

    initial_time: datetime | None = None
    timezone_name: str = "UTC"


class ControllableTimeAdapter(TimePort):
    """Adapter for controllable time in testing.

    This adapter implements the TimePort interface with the ability
    to freeze, advance, and control time for deterministic testing.

    Attributes:
        config: Configuration for time control.

    Example:
        >>> adapter = ControllableTimeAdapter()
        >>> now = adapter.now()
        >>> adapter.advance(timedelta(hours=1))
        >>> assert adapter.now() > now
    """

    def __init__(
        self,
        initial_time: datetime | None = None,
        timezone_name: str = "UTC",
    ) -> None:
        """Initialize the Controllable Time adapter.

        Args:
            initial_time: Starting time (defaults to now).
            timezone_name: Timezone name.
        """
        self.config = ControllableTimeConfig(
            initial_time=initial_time,
            timezone_name=timezone_name,
        )
        self._frozen_time: datetime | None = None
        self._is_frozen = False
        self._offset = timedelta()
        self._scheduled_tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()

        if initial_time:
            self._frozen_time = initial_time

    def now(self) -> datetime:
        """Get the current time.

        Returns:
            Current datetime.
        """
        if self._is_frozen and self._frozen_time:
            return self._frozen_time + self._offset
        return datetime.now(timezone.utc) + self._offset

    def today(self) -> datetime:
        """Get today's date at midnight.

        Returns:
            Today's date as datetime.
        """
        now = self.now()
        return datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)

    def now_utc(self) -> datetime:
        """Get the current UTC time.

        Returns:
            Current UTC datetime.
        """
        return self.now()

    def now_iso(self) -> str:
        """Get the current time in ISO format.

        Returns:
            ISO formatted time string.
        """
        return self.now().isoformat()

    def timestamp(self) -> float:
        """Get the current Unix timestamp.

        Returns:
            Unix timestamp.
        """
        return self.now().timestamp()

    def sleep(self, seconds: float) -> None:
        """Sleep for a duration.

        If time is frozen, this advances time instead.

        Args:
            seconds: Duration to sleep.
        """
        if self._is_frozen:
            self._offset += timedelta(seconds=seconds)
            self._process_scheduled_tasks()
        else:
            time.sleep(seconds)

    def freeze(self, time: datetime | None = None) -> None:
        """Freeze time at a specific moment.

        Args:
            time: Time to freeze at, or current time if None.
        """
        with self._lock:
            self._is_frozen = True
            if time:
                self._frozen_time = time
            elif self._frozen_time is None:
                self._frozen_time = datetime.now(timezone.utc)

    def unfreeze(self) -> None:
        """Unfreeze time, allowing it to progress normally."""
        with self._lock:
            self._is_frozen = False

    def is_frozen(self) -> bool:
        """Check if time is frozen.

        Returns:
            True if time is frozen.
        """
        return self._is_frozen

    def advance(self, delta: timedelta) -> datetime:
        """Advance time by a delta.

        Args:
            delta: Amount to advance time.

        Returns:
            New current time.
        """
        with self._lock:
            self._offset += delta
            self._process_scheduled_tasks()
        return self.now()

    def set_time(self, time: datetime) -> None:
        """Set the current time.

        Args:
            time: Time to set.
        """
        with self._lock:
            if self._is_frozen:
                self._frozen_time = time
                self._offset = timedelta()
            else:
                now = datetime.now(timezone.utc)
                self._offset = time - now
            self._process_scheduled_tasks()

    def _process_scheduled_tasks(self) -> None:
        """Process any scheduled tasks that are due."""
        current = self.now()
        for task_id, task in list(self._scheduled_tasks.items()):
            if task.cancelled:
                continue
            if task.scheduled_at <= current:
                if task.callback:
                    try:
                        task.callback()
                    except Exception:
                        pass
                if task.recurring and task.interval_seconds:
                    task.scheduled_at = current + timedelta(seconds=task.interval_seconds)
                else:
                    del self._scheduled_tasks[task_id]

    def schedule(
        self,
        callback: Callable[..., Any],
        when: datetime,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Schedule a callback for execution at a specific time.

        Args:
            callback: Function to call.
            when: When to execute.
            *args: Positional arguments for callback.
            **kwargs: Keyword arguments for callback.

        Returns:
            Scheduled task ID.
        """
        task_id = str(uuid.uuid4())
        with self._lock:
            self._scheduled_tasks[task_id] = ScheduledTask(
                id=task_id,
                name=callback.__name__,
                scheduled_at=when,
                callback=callback,
                recurring=False,
            )
        return task_id

    def schedule_after(
        self,
        delay_seconds: float,
        callback: Callable[[], Any],
        name: str = "",
    ) -> str:
        """Schedule a callback to run after a delay.

        Args:
            delay_seconds: Delay before execution.
            callback: Function to call.
            name: Task name.

        Returns:
            Scheduled task ID.
        """
        when = self.now() + timedelta(seconds=delay_seconds)
        return self.schedule(callback, when)

    def schedule_every(
        self,
        interval_seconds: float,
        callback: Callable[[], Any],
        name: str = "",
    ) -> str:
        """Schedule a callback to run periodically.

        Args:
            interval_seconds: Time between executions.
            callback: Function to call.
            name: Task name.

        Returns:
            Scheduled task ID.
        """
        task_id = str(uuid.uuid4())
        with self._lock:
            self._scheduled_tasks[task_id] = ScheduledTask(
                id=task_id,
                name=name or callback.__name__,
                scheduled_at=self.now() + timedelta(seconds=interval_seconds),
                callback=callback,
                recurring=True,
                interval_seconds=int(interval_seconds),
            )
        return task_id

    def schedule_recurring(
        self,
        callback: Callable[..., Any],
        interval: timedelta,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Schedule a recurring callback.

        Args:
            callback: Function to call.
            interval: Time between executions.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Scheduled task ID.
        """
        return self.schedule_every(interval.total_seconds(), callback)

    def cancel_schedule(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: Task ID to cancel.

        Returns:
            True if cancelled, False if not found.
        """
        with self._lock:
            if task_id in self._scheduled_tasks:
                self._scheduled_tasks[task_id].enabled = False
                self._scheduled_tasks[task_id].cancelled = True
                return True
        return False

    def get_scheduled(self, task_id: str) -> ScheduledTask | None:
        """Get information about a scheduled task.

        Args:
            task_id: Task ID.

        Returns:
            Task information or None if not found.
        """
        return self._scheduled_tasks.get(task_id)

    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        """Get all scheduled tasks.

        Returns:
            List of scheduled tasks.
        """
        return list(self._scheduled_tasks.values())

    def get_time_info(self) -> TimeInfo:
        """Get current time state information.

        Returns:
            Time state information.
        """
        return TimeInfo(
            now=self.now(),
            timezone=self.config.timezone_name,
            utc_offset_seconds=0,
            is_dst=False,
        )

    def set_timezone(self, timezone: str) -> None:
        """Set the timezone for time operations.

        Args:
            timezone: Timezone name.
        """
        self.config.timezone_name = timezone

    def get_timezone(self) -> str:
        """Get the current timezone.

        Returns:
            Timezone name.
        """
        return self.config.timezone_name

    def parse(self, time_string: str, format: str | None = None) -> datetime:
        """Parse a time string into a datetime.

        Args:
            time_string: Time string to parse.
            format: Optional format string.

        Returns:
            Parsed datetime.
        """
        if format:
            return datetime.strptime(time_string, format)
        return datetime.fromisoformat(time_string)

    def format(self, dt: datetime, format: str | None = None) -> str:
        """Format a datetime into a string.

        Args:
            dt: Datetime to format.
            format: Optional format string.

        Returns:
            Formatted string.
        """
        if format:
            return dt.strftime(format)
        return dt.isoformat()

    def add_seconds(self, dt: datetime, seconds: float) -> datetime:
        """Add seconds to a datetime."""
        return dt + timedelta(seconds=seconds)

    def add_minutes(self, dt: datetime, minutes: int) -> datetime:
        """Add minutes to a datetime."""
        return dt + timedelta(minutes=minutes)

    def add_hours(self, dt: datetime, hours: int) -> datetime:
        """Add hours to a datetime."""
        return dt + timedelta(hours=hours)

    def add_days(self, dt: datetime, days: int) -> datetime:
        """Add days to a datetime."""
        return dt + timedelta(days=days)

    def diff_seconds(self, start: datetime, end: datetime) -> float:
        """Get the difference between two datetimes in seconds."""
        return (end - start).total_seconds()

    def reset(self) -> None:
        """Reset time to real time and clear all scheduled tasks."""
        with self._lock:
            self._is_frozen = False
            self._frozen_time = None
            self._offset = timedelta()
            self._scheduled_tasks.clear()

    def health_check(self) -> bool:
        """Check if the time service is healthy."""
        return True
