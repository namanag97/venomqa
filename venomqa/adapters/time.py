"""Time adapters for testing.

This module provides time-related adapters for testing purposes.
It includes SystemTimeAdapter for real time and MockTimeAdapter for
controllable time in tests.

Example:
    >>> from venomqa.adapters.time import MockTimeAdapter
    >>> from datetime import datetime
    >>> adapter = MockTimeAdapter(initial_time=datetime(2024, 1, 1))
    >>> adapter.advance(hours=1)
    >>> print(adapter.now())  # 2024-01-01 01:00:00
"""

from __future__ import annotations

import time as time_module
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from venomqa.ports.time import ScheduledTask, TimeInfo, TimePort


@dataclass
class SystemTimeConfig:
    """Configuration for System Time adapter.

    Attributes:
        timezone: Default timezone name.
    """

    timezone: str = "UTC"


class SystemTimeAdapter(TimePort):
    """System time adapter using real system time.

    This adapter provides real system time operations. It's useful for
    production code or tests that need actual time behavior.

    Attributes:
        config: Configuration for time operations.

    Example:
        >>> adapter = SystemTimeAdapter()
        >>> now = adapter.now()
        >>> adapter.sleep(1)
        >>> elapsed = adapter.diff_seconds(now, adapter.now())
    """

    def __init__(self, timezone: str = "UTC") -> None:
        """Initialize the System Time adapter.

        Args:
            timezone: Default timezone name. Defaults to "UTC".
        """
        self.config = SystemTimeConfig(timezone=timezone)
        self._scheduled_tasks: dict[str, ScheduledTask] = {}

    def now(self) -> datetime:
        """Get the current local time.

        Returns:
            Current datetime.
        """
        return datetime.now()

    def now_utc(self) -> datetime:
        """Get the current UTC time.

        Returns:
            Current UTC datetime.
        """
        from datetime import timezone

        return datetime.now(timezone.utc).replace(tzinfo=None)

    def now_iso(self) -> str:
        """Get the current time in ISO format.

        Returns:
            ISO formatted time string.
        """
        return datetime.now().isoformat()

    def timestamp(self) -> float:
        """Get the current Unix timestamp.

        Returns:
            Unix timestamp as a float.
        """
        return time_module.time()

    def sleep(self, seconds: float) -> None:
        """Sleep for a specified number of seconds.

        Args:
            seconds: Duration to sleep in seconds.

        Raises:
            ValueError: If seconds is negative.
        """
        if seconds < 0:
            raise ValueError("Cannot sleep for negative duration")
        time_module.sleep(seconds)

    def schedule(self, task: ScheduledTask) -> str:
        """Schedule a task to run at a specific time.

        Note: This adapter stores tasks but does not execute them.
        Use ControllableTimeAdapter for testing scheduled tasks.

        Args:
            task: The scheduled task.

        Returns:
            Task ID.
        """
        task_id = task.id or f"sched-{uuid.uuid4()}"
        task.id = task_id
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_after(
        self,
        delay_seconds: float,
        callback: Callable[[], Any],
        name: str = "",
    ) -> str:
        """Schedule a callback to run after a delay.

        Args:
            delay_seconds: Delay before execution in seconds.
            callback: Function to call.
            name: Optional task name.

        Returns:
            Task ID.
        """
        task_id = f"sched-{uuid.uuid4()}"
        task = ScheduledTask(
            id=task_id,
            name=name or f"task_{task_id[:8]}",
            scheduled_at=datetime.now() + timedelta(seconds=delay_seconds),
            callback=callback,
        )
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_every(
        self,
        interval_seconds: float,
        callback: Callable[[], Any],
        name: str = "",
    ) -> str:
        """Schedule a callback to run periodically.

        Args:
            interval_seconds: Time between executions in seconds.
            callback: Function to call.
            name: Optional task name.

        Returns:
            Task ID.
        """
        task_id = f"sched-{uuid.uuid4()}"
        task = ScheduledTask(
            id=task_id,
            name=name or f"task_{task_id[:8]}",
            scheduled_at=datetime.now() + timedelta(seconds=interval_seconds),
            callback=callback,
            recurring=True,
            interval_seconds=int(interval_seconds),
        )
        self._scheduled_tasks[task_id] = task
        return task_id

    def cancel_schedule(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel.

        Returns:
            True if cancelled, False if not found.
        """
        if task_id in self._scheduled_tasks:
            del self._scheduled_tasks[task_id]
            return True
        return False

    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        """Get all scheduled tasks.

        Returns:
            List of all scheduled tasks.
        """
        return list(self._scheduled_tasks.values())

    def get_time_info(self) -> TimeInfo:
        """Get information about the current time.

        Returns:
            TimeInfo with current time and timezone.
        """
        now = datetime.now()
        return TimeInfo(
            now=now,
            timezone=self.config.timezone,
            utc_offset_seconds=0,
            is_dst=False,
        )

    def set_timezone(self, timezone: str) -> None:
        """Set the timezone for time operations.

        Args:
            timezone: Timezone name to set.
        """
        self.config.timezone = timezone

    def get_timezone(self) -> str:
        """Get the current timezone.

        Returns:
            Timezone name.
        """
        return self.config.timezone

    def parse(self, time_string: str, format: str | None = None) -> datetime:
        """Parse a time string into a datetime.

        Args:
            time_string: Time string to parse.
            format: Optional strptime format string.

        Returns:
            Parsed datetime.

        Raises:
            ValueError: If the string cannot be parsed.
        """
        if format:
            return datetime.strptime(time_string, format)
        return datetime.fromisoformat(time_string)

    def format(self, dt: datetime, format: str | None = None) -> str:
        """Format a datetime into a string.

        Args:
            dt: Datetime to format.
            format: Optional strftime format string.

        Returns:
            Formatted string.
        """
        if format:
            return dt.strftime(format)
        return dt.isoformat()

    def add_seconds(self, dt: datetime, seconds: float) -> datetime:
        """Add seconds to a datetime.

        Args:
            dt: Base datetime.
            seconds: Seconds to add.

        Returns:
            New datetime with seconds added.
        """
        return dt + timedelta(seconds=seconds)

    def add_minutes(self, dt: datetime, minutes: int) -> datetime:
        """Add minutes to a datetime.

        Args:
            dt: Base datetime.
            minutes: Minutes to add.

        Returns:
            New datetime with minutes added.
        """
        return dt + timedelta(minutes=minutes)

    def add_hours(self, dt: datetime, hours: int) -> datetime:
        """Add hours to a datetime.

        Args:
            dt: Base datetime.
            hours: Hours to add.

        Returns:
            New datetime with hours added.
        """
        return dt + timedelta(hours=hours)

    def add_days(self, dt: datetime, days: int) -> datetime:
        """Add days to a datetime.

        Args:
            dt: Base datetime.
            days: Days to add.

        Returns:
            New datetime with days added.
        """
        return dt + timedelta(days=days)

    def diff_seconds(self, start: datetime, end: datetime) -> float:
        """Get the difference between two datetimes in seconds.

        Args:
            start: Start datetime.
            end: End datetime.

        Returns:
            Difference in seconds (positive if end > start).
        """
        return (end - start).total_seconds()

    def diff_minutes(self, start: datetime, end: datetime) -> float:
        """Get the difference between two datetimes in minutes.

        Args:
            start: Start datetime.
            end: End datetime.

        Returns:
            Difference in minutes.
        """
        return (end - start).total_seconds() / 60

    def diff_hours(self, start: datetime, end: datetime) -> float:
        """Get the difference between two datetimes in hours.

        Args:
            start: Start datetime.
            end: End datetime.

        Returns:
            Difference in hours.
        """
        return (end - start).total_seconds() / 3600

    def diff_days(self, start: datetime, end: datetime) -> float:
        """Get the difference between two datetimes in days.

        Args:
            start: Start datetime.
            end: End datetime.

        Returns:
            Difference in days.
        """
        return (end - start).total_seconds() / 86400


@dataclass
class MockTimeConfig:
    """Configuration for Mock Time adapter.

    Attributes:
        timezone: Default timezone name.
        auto_advance: Seconds to auto-advance on each now() call.
    """

    timezone: str = "UTC"
    auto_advance: float = 0.0


class MockTimeAdapter(TimePort):
    """Mock time adapter for testing with controllable time.

    This adapter provides fully controllable time for testing. Time can be
    frozen, advanced, or set to specific values. The sleep() method
    advances time instead of actually sleeping.

    Attributes:
        config: Configuration for time control.

    Example:
        >>> adapter = MockTimeAdapter()
        >>> adapter.freeze()
        >>> start = adapter.now()
        >>> adapter.advance(hours=24)
        >>> elapsed = adapter.diff_seconds(start, adapter.now())
        >>> print(elapsed)  # 86400.0
    """

    def __init__(
        self,
        initial_time: datetime | None = None,
        timezone: str = "UTC",
        auto_advance: float = 0.0,
    ) -> None:
        """Initialize the Mock Time adapter.

        Args:
            initial_time: Starting time. Defaults to current time.
            timezone: Default timezone name.
            auto_advance: Seconds to auto-advance on each now() call.
        """
        self.config = MockTimeConfig(timezone=timezone, auto_advance=auto_advance)
        self._current_time = initial_time or datetime.now()
        self._scheduled_tasks: dict[str, ScheduledTask] = {}
        self._is_frozen = False

    def now(self) -> datetime:
        """Get the current (mock) time.

        If auto_advance is set, advances time before returning.

        Returns:
            Current mock datetime.
        """
        if self.config.auto_advance > 0 and not self._is_frozen:
            self._current_time += timedelta(seconds=self.config.auto_advance)
        return self._current_time

    def now_utc(self) -> datetime:
        """Get the current (mock) UTC time.

        Returns:
            Current mock datetime (same as now() for mock).
        """
        return self._current_time

    def now_iso(self) -> str:
        """Get the current time in ISO format.

        Returns:
            ISO formatted time string.
        """
        return self._current_time.isoformat()

    def timestamp(self) -> float:
        """Get the current Unix timestamp.

        Returns:
            Unix timestamp of the mock time.
        """
        return self._current_time.timestamp()

    def sleep(self, seconds: float) -> None:
        """Sleep for a duration (advances mock time).

        This does not actually sleep; it advances the mock time.

        Args:
            seconds: Duration to "sleep" in seconds.
        """
        self._current_time += timedelta(seconds=seconds)
        self._process_scheduled_tasks()

    def set_time(self, dt: datetime) -> None:
        """Set the current mock time.

        Args:
            dt: Datetime to set as current time.
        """
        self._current_time = dt
        self._process_scheduled_tasks()

    def freeze(self) -> None:
        """Freeze time at the current moment.

        After freezing, now() will always return the same time until
        unfreeze() is called.
        """
        self._is_frozen = True

    def unfreeze(self) -> None:
        """Unfreeze time, allowing it to progress normally."""
        self._is_frozen = False

    def is_frozen(self) -> bool:
        """Check if time is currently frozen.

        Returns:
            True if frozen, False otherwise.
        """
        return self._is_frozen

    def advance(self, seconds: float) -> None:
        """Advance time by a number of seconds.

        Args:
            seconds: Seconds to advance.
        """
        self._current_time += timedelta(seconds=seconds)
        self._process_scheduled_tasks()

    def advance_minutes(self, minutes: int) -> None:
        """Advance time by a number of minutes.

        Args:
            minutes: Minutes to advance.
        """
        self._current_time += timedelta(minutes=minutes)
        self._process_scheduled_tasks()

    def advance_hours(self, hours: int) -> None:
        """Advance time by a number of hours.

        Args:
            hours: Hours to advance.
        """
        self._current_time += timedelta(hours=hours)
        self._process_scheduled_tasks()

    def advance_days(self, days: int) -> None:
        """Advance time by a number of days.

        Args:
            days: Days to advance.
        """
        self._current_time += timedelta(days=days)
        self._process_scheduled_tasks()

    def advance_to(self, dt: datetime) -> None:
        """Advance time to a specific datetime.

        Args:
            dt: Target datetime.

        Raises:
            ValueError: If dt is in the past.
        """
        if dt < self._current_time:
            raise ValueError("Cannot advance to a time in the past")
        self._current_time = dt
        self._process_scheduled_tasks()

    def _process_scheduled_tasks(self) -> None:
        """Process scheduled tasks that are due."""
        current = self._current_time
        for task_id, task in list(self._scheduled_tasks.items()):
            if not task.enabled or task.callback is None:
                continue
            if task.scheduled_at <= current:
                try:
                    task.callback()
                except Exception:
                    pass
                if task.recurring and task.interval_seconds:
                    task.scheduled_at = current + timedelta(seconds=task.interval_seconds)
                else:
                    del self._scheduled_tasks[task_id]

    def schedule(self, task: ScheduledTask) -> str:
        """Schedule a task to run at a specific time.

        Args:
            task: The scheduled task.

        Returns:
            Task ID.
        """
        task_id = task.id or str(uuid.uuid4())
        task.id = task_id
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_after(
        self,
        delay_seconds: float,
        callback: Callable[[], Any],
        name: str = "",
    ) -> str:
        """Schedule a callback to run after a delay.

        Args:
            delay_seconds: Delay before execution in seconds.
            callback: Function to call.
            name: Optional task name.

        Returns:
            Task ID.
        """
        task_id = f"sched-{uuid.uuid4()}"
        task = ScheduledTask(
            id=task_id,
            name=name or f"task_{task_id[:8]}",
            scheduled_at=self._current_time + timedelta(seconds=delay_seconds),
            callback=callback,
        )
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_every(
        self,
        interval_seconds: float,
        callback: Callable[[], Any],
        name: str = "",
    ) -> str:
        """Schedule a callback to run periodically.

        Args:
            interval_seconds: Time between executions in seconds.
            callback: Function to call.
            name: Optional task name.

        Returns:
            Task ID.
        """
        task_id = f"sched-{uuid.uuid4()}"
        task = ScheduledTask(
            id=task_id,
            name=name or f"task_{task_id[:8]}",
            scheduled_at=self._current_time + timedelta(seconds=interval_seconds),
            callback=callback,
            recurring=True,
            interval_seconds=int(interval_seconds),
        )
        self._scheduled_tasks[task_id] = task
        return task_id

    def cancel_schedule(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel.

        Returns:
            True if cancelled, False if not found.
        """
        if task_id in self._scheduled_tasks:
            del self._scheduled_tasks[task_id]
            return True
        return False

    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        """Get all scheduled tasks.

        Returns:
            List of all scheduled tasks.
        """
        return list(self._scheduled_tasks.values())

    def get_time_info(self) -> TimeInfo:
        """Get information about the current time.

        Returns:
            TimeInfo with current time and timezone.
        """
        return TimeInfo(
            now=self._current_time,
            timezone=self.config.timezone,
            utc_offset_seconds=0,
            is_dst=False,
        )

    def set_timezone(self, timezone: str) -> None:
        """Set the timezone for time operations.

        Args:
            timezone: Timezone name.
        """
        self.config.timezone = timezone

    def get_timezone(self) -> str:
        """Get the current timezone.

        Returns:
            Timezone name.
        """
        return self.config.timezone

    def parse(self, time_string: str, format: str | None = None) -> datetime:
        """Parse a time string into a datetime.

        Args:
            time_string: Time string to parse.
            format: Optional strptime format string.

        Returns:
            Parsed datetime.

        Raises:
            ValueError: If the string cannot be parsed.
        """
        if format:
            return datetime.strptime(time_string, format)
        return datetime.fromisoformat(time_string)

    def format(self, dt: datetime, format: str | None = None) -> str:
        """Format a datetime into a string.

        Args:
            dt: Datetime to format.
            format: Optional strftime format string.

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
        """Reset time to the current real time and clear scheduled tasks."""
        self._current_time = datetime.now()
        self._scheduled_tasks.clear()
        self._is_frozen = False
