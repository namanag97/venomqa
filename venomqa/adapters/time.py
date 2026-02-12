"""Time adapters for testing.

This module provides time-related adapters for testing purposes.
"""

from __future__ import annotations

import time as time_module
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from venomqa.ports.time import ScheduledTask, TimeInfo, TimePort


class SystemTimeAdapter(TimePort):
    """System time adapter using real system time."""

    def __init__(self) -> None:
        self._timezone = "UTC"
        self._scheduled_tasks: dict[str, ScheduledTask] = {}

    def now(self) -> datetime:
        return datetime.now()

    def now_utc(self) -> datetime:
        return datetime.utcnow()

    def now_iso(self) -> str:
        return datetime.now().isoformat()

    def timestamp(self) -> float:
        return time_module.time()

    def sleep(self, seconds: float) -> None:
        time_module.sleep(seconds)

    def schedule(self, task: ScheduledTask) -> str:
        task_id = task.id or str(uuid.uuid4())
        task.id = task_id
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_after(
        self, delay_seconds: float, callback: Callable[[], Any], name: str = ""
    ) -> str:
        task_id = str(uuid.uuid4())
        task = ScheduledTask(
            id=task_id,
            name=name or f"task_{task_id[:8]}",
            scheduled_at=datetime.now() + timedelta(seconds=delay_seconds),
            callback=callback,
        )
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_every(
        self, interval_seconds: float, callback: Callable[[], Any], name: str = ""
    ) -> str:
        task_id = str(uuid.uuid4())
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
        if task_id in self._scheduled_tasks:
            del self._scheduled_tasks[task_id]
            return True
        return False

    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        return list(self._scheduled_tasks.values())

    def get_time_info(self) -> TimeInfo:
        now = datetime.now()
        return TimeInfo(
            now=now,
            timezone=self._timezone,
            utc_offset_seconds=0,
            is_dst=False,
        )

    def set_timezone(self, timezone: str) -> None:
        self._timezone = timezone

    def get_timezone(self) -> str:
        return self._timezone

    def parse(self, time_string: str, format: str | None = None) -> datetime:
        if format:
            return datetime.strptime(time_string, format)
        return datetime.fromisoformat(time_string)

    def format(self, dt: datetime, format: str | None = None) -> str:
        if format:
            return dt.strftime(format)
        return dt.isoformat()

    def add_seconds(self, dt: datetime, seconds: float) -> datetime:
        return dt + timedelta(seconds=seconds)

    def add_minutes(self, dt: datetime, minutes: int) -> datetime:
        return dt + timedelta(minutes=minutes)

    def add_hours(self, dt: datetime, hours: int) -> datetime:
        return dt + timedelta(hours=hours)

    def add_days(self, dt: datetime, days: int) -> datetime:
        return dt + timedelta(days=days)

    def diff_seconds(self, start: datetime, end: datetime) -> float:
        return (end - start).total_seconds()


class MockTimeAdapter(TimePort):
    """Mock time adapter for testing with controllable time."""

    def __init__(self, initial_time: datetime | None = None) -> None:
        self._current_time = initial_time or datetime.now()
        self._timezone = "UTC"
        self._scheduled_tasks: dict[str, ScheduledTask] = {}

    def now(self) -> datetime:
        return self._current_time

    def now_utc(self) -> datetime:
        return self._current_time

    def now_iso(self) -> str:
        return self._current_time.isoformat()

    def timestamp(self) -> float:
        return self._current_time.timestamp()

    def sleep(self, seconds: float) -> None:
        self._current_time += timedelta(seconds=seconds)

    def set_time(self, dt: datetime) -> None:
        self._current_time = dt

    def advance(self, seconds: float) -> None:
        self._current_time += timedelta(seconds=seconds)

    def schedule(self, task: ScheduledTask) -> str:
        task_id = task.id or str(uuid.uuid4())
        task.id = task_id
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_after(
        self, delay_seconds: float, callback: Callable[[], Any], name: str = ""
    ) -> str:
        task_id = str(uuid.uuid4())
        task = ScheduledTask(
            id=task_id,
            name=name or f"task_{task_id[:8]}",
            scheduled_at=self._current_time + timedelta(seconds=delay_seconds),
            callback=callback,
        )
        self._scheduled_tasks[task_id] = task
        return task_id

    def schedule_every(
        self, interval_seconds: float, callback: Callable[[], Any], name: str = ""
    ) -> str:
        task_id = str(uuid.uuid4())
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
        if task_id in self._scheduled_tasks:
            del self._scheduled_tasks[task_id]
            return True
        return False

    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        return list(self._scheduled_tasks.values())

    def get_time_info(self) -> TimeInfo:
        return TimeInfo(
            now=self._current_time,
            timezone=self._timezone,
            utc_offset_seconds=0,
            is_dst=False,
        )

    def set_timezone(self, timezone: str) -> None:
        self._timezone = timezone

    def get_timezone(self) -> str:
        return self._timezone

    def parse(self, time_string: str, format: str | None = None) -> datetime:
        if format:
            return datetime.strptime(time_string, format)
        return datetime.fromisoformat(time_string)

    def format(self, dt: datetime, format: str | None = None) -> str:
        if format:
            return dt.strftime(format)
        return dt.isoformat()

    def add_seconds(self, dt: datetime, seconds: float) -> datetime:
        return dt + timedelta(seconds=seconds)

    def add_minutes(self, dt: datetime, minutes: int) -> datetime:
        return dt + timedelta(minutes=minutes)

    def add_hours(self, dt: datetime, hours: int) -> datetime:
        return dt + timedelta(hours=hours)

    def add_days(self, dt: datetime, days: int) -> datetime:
        return dt + timedelta(days=days)

    def diff_seconds(self, start: datetime, end: datetime) -> float:
        return (end - start).total_seconds()
