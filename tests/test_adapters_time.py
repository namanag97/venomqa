"""Tests for time adapters in VenomQA."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from venomqa.adapters.time import SystemTimeAdapter, MockTimeAdapter
from venomqa.ports.time import ScheduledTask


class TestSystemTimeAdapter:
    """Tests for SystemTimeAdapter."""

    @pytest.fixture
    def adapter(self) -> SystemTimeAdapter:
        return SystemTimeAdapter()

    def test_adapter_initialization(self, adapter: SystemTimeAdapter) -> None:
        assert adapter.get_timezone() == "UTC"

    def test_now_returns_datetime(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.now()
        assert isinstance(result, datetime)

    def test_now_utc_returns_datetime(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.now_utc()
        assert isinstance(result, datetime)

    def test_now_iso_returns_string(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.now_iso()
        assert isinstance(result, str)
        assert "T" in result

    def test_timestamp_returns_float(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.timestamp()
        assert isinstance(result, float)
        assert result > 0

    def test_set_timezone(self, adapter: SystemTimeAdapter) -> None:
        adapter.set_timezone("America/New_York")
        assert adapter.get_timezone() == "America/New_York"

    def test_parse_iso_format(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.parse("2024-01-15T10:30:00")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_custom_format(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.parse("2024-01-15", format="%Y-%m-%d")
        assert result.year == 2024
        assert result.month == 1

    def test_format_default(self, adapter: SystemTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = adapter.format(dt)
        assert "2024-01-15" in result

    def test_format_custom(self, adapter: SystemTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = adapter.format(dt, format="%Y/%m/%d")
        assert result == "2024/01/15"

    def test_add_seconds(self, adapter: SystemTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.add_seconds(dt, 30)
        assert result.second == 30

    def test_add_minutes(self, adapter: SystemTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.add_minutes(dt, 30)
        assert result.minute == 30

    def test_add_hours(self, adapter: SystemTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.add_hours(dt, 5)
        assert result.hour == 15

    def test_add_days(self, adapter: SystemTimeAdapter) -> None:
        dt = datetime(2024, 1, 15)
        result = adapter.add_days(dt, 10)
        assert result.day == 25

    def test_diff_seconds(self, adapter: SystemTimeAdapter) -> None:
        start = datetime(2024, 1, 15, 10, 0, 0)
        end = datetime(2024, 1, 15, 10, 0, 30)
        result = adapter.diff_seconds(start, end)
        assert result == 30.0

    def test_diff_seconds_negative(self, adapter: SystemTimeAdapter) -> None:
        start = datetime(2024, 1, 15, 10, 0, 30)
        end = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.diff_seconds(start, end)
        assert result == -30.0

    def test_get_time_info(self, adapter: SystemTimeAdapter) -> None:
        info = adapter.get_time_info()
        assert info.timezone == "UTC"
        assert isinstance(info.now, datetime)

    def test_schedule(self, adapter: SystemTimeAdapter) -> None:
        task = ScheduledTask(
            id="task-1",
            name="test_task",
            scheduled_at=adapter.now(),
        )
        task_id = adapter.schedule(task)
        assert task_id == "task-1"

    def test_schedule_auto_generates_id(self, adapter: SystemTimeAdapter) -> None:
        task = ScheduledTask(
            id="",
            name="test_task",
            scheduled_at=adapter.now(),
        )
        task_id = adapter.schedule(task)
        assert task_id.startswith("sched-")

    def test_cancel_schedule(self, adapter: SystemTimeAdapter) -> None:
        task_id = adapter.schedule_after(60.0, lambda: None)
        result = adapter.cancel_schedule(task_id)
        assert result is True

    def test_cancel_nonexistent_schedule(self, adapter: SystemTimeAdapter) -> None:
        result = adapter.cancel_schedule("nonexistent")
        assert result is False

    def test_get_scheduled_tasks(self, adapter: SystemTimeAdapter) -> None:
        adapter.schedule_after(60.0, lambda: None, name="task1")
        adapter.schedule_after(120.0, lambda: None, name="task2")
        tasks = adapter.get_scheduled_tasks()
        assert len(tasks) == 2

    def test_schedule_every(self, adapter: SystemTimeAdapter) -> None:
        task_id = adapter.schedule_every(60.0, lambda: None, name="recurring")
        assert task_id.startswith("sched-")


class TestMockTimeAdapter:
    """Tests for MockTimeAdapter."""

    @pytest.fixture
    def adapter(self) -> MockTimeAdapter:
        return MockTimeAdapter()

    def test_adapter_initialization(self, adapter: MockTimeAdapter) -> None:
        assert adapter.now() is not None

    def test_adapter_with_initial_time(self) -> None:
        initial = datetime(2024, 1, 15, 10, 0, 0)
        adapter = MockTimeAdapter(initial_time=initial)
        assert adapter.now() == initial

    def test_set_time(self, adapter: MockTimeAdapter) -> None:
        new_time = datetime(2024, 6, 15, 14, 30, 0)
        adapter.set_time(new_time)
        assert adapter.now() == new_time

    def test_advance_seconds(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.advance(30)
        assert adapter.now() == initial + timedelta(seconds=30)

    def test_advance_minutes(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.advance_minutes(15)
        assert adapter.now() == initial + timedelta(minutes=15)

    def test_advance_hours(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.advance_hours(3)
        assert adapter.now() == initial + timedelta(hours=3)

    def test_advance_days(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.advance_days(5)
        assert adapter.now() == initial + timedelta(days=5)

    def test_sleep_advances_time(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.sleep(10)
        assert adapter.now() == initial + timedelta(seconds=10)

    def test_now_utc_same_as_now(self, adapter: MockTimeAdapter) -> None:
        assert adapter.now_utc() == adapter.now()

    def test_now_iso(self, adapter: MockTimeAdapter) -> None:
        adapter.set_time(datetime(2024, 1, 15, 10, 30, 0))
        result = adapter.now_iso()
        assert "2024-01-15" in result

    def test_timestamp(self, adapter: MockTimeAdapter) -> None:
        adapter.set_time(datetime(2024, 1, 15, 0, 0, 0))
        result = adapter.timestamp()
        assert isinstance(result, float)

    def test_set_timezone(self, adapter: MockTimeAdapter) -> None:
        adapter.set_timezone("America/Los_Angeles")
        assert adapter.get_timezone() == "America/Los_Angeles"

    def test_parse_iso_format(self, adapter: MockTimeAdapter) -> None:
        result = adapter.parse("2024-01-15T10:30:00")
        assert result.year == 2024

    def test_parse_custom_format(self, adapter: MockTimeAdapter) -> None:
        result = adapter.parse("15/01/2024", format="%d/%m/%Y")
        assert result.day == 15
        assert result.month == 1

    def test_format_default(self, adapter: MockTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = adapter.format(dt)
        assert "2024-01-15" in result

    def test_format_custom(self, adapter: MockTimeAdapter) -> None:
        dt = datetime(2024, 1, 15)
        result = adapter.format(dt, format="%d-%m-%Y")
        assert result == "15-01-2024"

    def test_add_seconds(self, adapter: MockTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.add_seconds(dt, 45)
        assert result.second == 45

    def test_add_minutes(self, adapter: MockTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.add_minutes(dt, 45)
        assert result.minute == 45

    def test_add_hours(self, adapter: MockTimeAdapter) -> None:
        dt = datetime(2024, 1, 15, 10, 0, 0)
        result = adapter.add_hours(dt, 8)
        assert result.hour == 18

    def test_add_days(self, adapter: MockTimeAdapter) -> None:
        dt = datetime(2024, 1, 15)
        result = adapter.add_days(dt, 20)
        assert result.day == 4
        assert result.month == 2

    def test_diff_seconds(self, adapter: MockTimeAdapter) -> None:
        start = datetime(2024, 1, 15, 10, 0, 0)
        end = datetime(2024, 1, 15, 10, 5, 30)
        result = adapter.diff_seconds(start, end)
        assert result == 330.0

    def test_get_time_info(self, adapter: MockTimeAdapter) -> None:
        adapter.set_timezone("UTC")
        info = adapter.get_time_info()
        assert info.timezone == "UTC"
        assert info.utc_offset_seconds == 0

    def test_schedule(self, adapter: MockTimeAdapter) -> None:
        task = ScheduledTask(
            id="mock-task-1",
            name="test",
            scheduled_at=adapter.now(),
        )
        task_id = adapter.schedule(task)
        assert task_id == "mock-task-1"

    def test_schedule_after(self, adapter: MockTimeAdapter) -> None:
        task_id = adapter.schedule_after(60.0, lambda: "result")
        tasks = adapter.get_scheduled_tasks()
        assert len(tasks) == 1

    def test_schedule_every(self, adapter: MockTimeAdapter) -> None:
        task_id = adapter.schedule_every(30.0, lambda: None)
        tasks = adapter.get_scheduled_tasks()
        recurring = [t for t in tasks if t.recurring]
        assert len(recurring) == 1

    def test_cancel_schedule(self, adapter: MockTimeAdapter) -> None:
        task_id = adapter.schedule_after(60.0, lambda: None)
        result = adapter.cancel_schedule(task_id)
        assert result is True
        assert len(adapter.get_scheduled_tasks()) == 0

    def test_cancel_nonexistent(self, adapter: MockTimeAdapter) -> None:
        result = adapter.cancel_schedule("nonexistent")
        assert result is False

    def test_multiple_advances(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.advance(10)
        adapter.advance_minutes(5)
        adapter.advance_hours(2)
        expected = initial + timedelta(seconds=10, minutes=5, hours=2)
        assert adapter.now() == expected

    def test_sleep_zero(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.sleep(0)
        assert adapter.now() == initial

    def test_negative_advance(self, adapter: MockTimeAdapter) -> None:
        initial = adapter.now()
        adapter.advance(-30)
        assert adapter.now() == initial - timedelta(seconds=30)

    def test_scheduled_task_has_correct_time(self, adapter: MockTimeAdapter) -> None:
        adapter.set_time(datetime(2024, 1, 15, 10, 0, 0))
        adapter.schedule_after(60.0, lambda: None)
        tasks = adapter.get_scheduled_tasks()
        assert tasks[0].scheduled_at == datetime(2024, 1, 15, 10, 1, 0)
