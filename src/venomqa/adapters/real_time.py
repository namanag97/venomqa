"""Real Time adapter for actual system time.

This adapter provides real system time operations for production use.

Example:
    >>> from venomqa.adapters import RealTimeAdapter
    >>> adapter = RealTimeAdapter()
    >>> now = adapter.now()
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
class RealTimeConfig:
    """Configuration for Real Time adapter."""

    timezone_name: str = "UTC"


class RealTimeAdapter(TimePort):
    """Adapter for real system time.

    This adapter implements the TimePort interface using actual
    system time for production environments.

    Attributes:
        config: Configuration for time operations.

    Example:
        >>> adapter = RealTimeAdapter()
        >>> start = adapter.now()
        >>> adapter.sleep(1)
        >>> elapsed = adapter.diff_seconds(start, adapter.now())
    """

    def __init__(self, timezone_name: str = "UTC") -> None:
        """Initialize the Real Time adapter.

        Args:
            timezone_name: Timezone name.
        """
        self.config = RealTimeConfig(timezone_name=timezone_name)
        self._scheduled_tasks: dict[str, ScheduledTask] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def now(self) -> datetime:
        """Get the current time.

        Returns:
            Current datetime.
        """
        return datetime.now(timezone.utc)

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
        return time.time()

    def sleep(self, seconds: float) -> None:
        """Sleep for a specified number of seconds.

        Args:
            seconds: Duration to sleep.
        """
        time.sleep(seconds)

    def freeze(self, time: datetime | None = None) -> None:
        """Freeze time at a specific moment.

        Note: Real time cannot be frozen. This is a no-op.

        Args:
            time: Time to freeze at (ignored).
        """
        pass

    def unfreeze(self) -> None:
        """Unfreeze time. This is a no-op for real time."""
        pass

    def is_frozen(self) -> bool:
        """Check if time is frozen.

        Returns:
            Always False for real time.
        """
        return False

    def advance(self, delta: timedelta) -> datetime:
        """Advance time by a delta.

        Note: Real time cannot be advanced. Returns current time.

        Args:
            delta: Amount to advance (ignored).

        Returns:
            Current time.
        """
        return self.now()

    def set_time(self, time: datetime) -> None:
        """Set the current time.

        Note: Real time cannot be set. This is a no-op.

        Args:
            time: Time to set (ignored).
        """
        pass

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

        def wrapped_callback() -> None:
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
            with self._lock:
                self._scheduled_tasks.pop(task_id, None)
                self._timers.pop(task_id, None)

        delay = (when - self.now()).total_seconds()
        if delay > 0:
            timer = threading.Timer(delay, wrapped_callback)
            with self._lock:
                self._scheduled_tasks[task_id] = ScheduledTask(
                    id=task_id,
                    name=callback.__name__,
                    scheduled_at=when,
                    callback=callback,
                    recurring=False,
                )
                self._timers[task_id] = timer
            timer.start()
        else:
            threading.Thread(target=wrapped_callback, daemon=True).start()

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
        stop_event = threading.Event()

        def recurring_callback() -> None:
            while not stop_event.is_set():
                try:
                    callback()
                except Exception:
                    pass
                stop_event.wait(interval_seconds)

        with self._lock:
            self._scheduled_tasks[task_id] = ScheduledTask(
                id=task_id,
                name=name or callback.__name__,
                scheduled_at=self.now() + timedelta(seconds=interval_seconds),
                callback=callback,
                recurring=True,
                interval_seconds=int(interval_seconds),
            )

        thread = threading.Thread(target=recurring_callback, daemon=True)
        thread.start()

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
            if task_id in self._timers:
                self._timers[task_id].cancel()
                del self._timers[task_id]
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
        """Get information about the current time.

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
        """Clear all scheduled tasks."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
            self._scheduled_tasks.clear()

    def health_check(self) -> bool:
        """Check if the time service is healthy."""
        return True
