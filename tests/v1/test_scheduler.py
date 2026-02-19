"""Unit tests for the Scheduler class."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from venomqa.agent.scheduler import RunResult, Scheduler
from venomqa.core.result import ExplorationResult


def _make_agent_factory(success: bool = True, violations: int = 0, states: int = 3):
    """Create an agent factory that returns a mock agent."""
    def factory():
        agent = MagicMock()
        result = MagicMock(spec=ExplorationResult)
        result.success = success
        result.violations = [MagicMock()] * violations
        result.states_visited = states
        result.duration_ms = 100.0
        agent.explore.return_value = result
        return agent
    return factory


class TestSchedulerRegister:
    def test_register_run(self):
        scheduler = Scheduler()
        scheduler.register("run1", "My Run", _make_agent_factory())
        assert "run1" in scheduler._runs

    def test_register_multiple(self):
        scheduler = Scheduler()
        scheduler.register("r1", "Run 1", _make_agent_factory())
        scheduler.register("r2", "Run 2", _make_agent_factory())
        assert len(scheduler._runs) == 2


class TestSchedulerRun:
    def test_run_single(self):
        scheduler = Scheduler()
        scheduler.register("run1", "My Run", _make_agent_factory(success=True, states=5))

        result = scheduler.run("run1")

        assert result.run_id == "run1"
        assert result.name == "My Run"
        assert result.success is True
        assert result.states_visited == 5

    def test_run_unknown_raises(self):
        scheduler = Scheduler()
        with pytest.raises(ValueError, match="Unknown run"):
            scheduler.run("nonexistent")

    def test_run_records_result(self):
        scheduler = Scheduler()
        scheduler.register("r1", "R1", _make_agent_factory())
        scheduler.run("r1")
        assert len(scheduler.get_results()) == 1

    def test_run_with_violations(self):
        scheduler = Scheduler()
        scheduler.register("r1", "R1", _make_agent_factory(success=False, violations=2))
        result = scheduler.run("r1")
        assert result.violations_count == 2
        assert result.success is False

    def test_run_agent_exception(self):
        def bad_factory():
            agent = MagicMock()
            agent.explore.side_effect = RuntimeError("API down")
            return agent

        scheduler = Scheduler()
        scheduler.register("r1", "R1", bad_factory)
        result = scheduler.run("r1")
        assert result.success is False
        assert "API down" in result.error


class TestSchedulerRunAll:
    def test_run_all_sequential(self):
        scheduler = Scheduler()
        scheduler.register("r1", "R1", _make_agent_factory(success=True))
        scheduler.register("r2", "R2", _make_agent_factory(success=False))

        results = scheduler.run_all(parallel=False)

        assert len(results) == 2
        run_ids = {r.run_id for r in results}
        assert run_ids == {"r1", "r2"}

    def test_run_all_parallel(self):
        scheduler = Scheduler(max_workers=2)
        scheduler.register("r1", "R1", _make_agent_factory(success=True))
        scheduler.register("r2", "R2", _make_agent_factory(success=True))

        results = scheduler.run_all(parallel=True)

        assert len(results) == 2

    def test_run_all_skips_disabled(self):
        scheduler = Scheduler()
        scheduler.register("r1", "R1", _make_agent_factory())
        scheduler.register("r2", "R2", _make_agent_factory())
        scheduler._runs["r2"].enabled = False

        results = scheduler.run_all(parallel=False)

        assert len(results) == 1
        assert results[0].run_id == "r1"


class TestSchedulerSaveResults:
    def test_saves_to_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = Scheduler(results_dir=tmp)
            scheduler.register("r1", "R1", _make_agent_factory())
            scheduler.run("r1")

            files = list(Path(tmp).glob("r1_*.json"))
            assert len(files) == 1

    def test_json_content(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = Scheduler(results_dir=tmp)
            scheduler.register("r1", "R1", _make_agent_factory(success=True, states=7))
            scheduler.run("r1")

            files = list(Path(tmp).glob("r1_*.json"))
            data = json.loads(files[0].read_text())
            assert data["run_id"] == "r1"
            assert data["states_visited"] == 7
            assert data["success"] is True


class TestSchedulerExportJunit:
    def test_export_junit_xml(self):
        scheduler = Scheduler()
        results = [
            RunResult(
                run_id="r1", name="Pass", success=True,
                violations_count=0, states_visited=5, duration_ms=100,
                started_at=__import__("datetime").datetime.now(),
                finished_at=__import__("datetime").datetime.now(),
            ),
            RunResult(
                run_id="r2", name="Fail", success=False,
                violations_count=3, states_visited=2, duration_ms=200,
                started_at=__import__("datetime").datetime.now(),
                finished_at=__import__("datetime").datetime.now(),
            ),
        ]
        xml = scheduler.export_junit(results)
        assert "testsuite" in xml
        assert "Pass" in xml
        assert "Fail" in xml
        assert "failure" in xml

    def test_clear_results(self):
        scheduler = Scheduler()
        scheduler.register("r1", "R1", _make_agent_factory())
        scheduler.run("r1")
        assert len(scheduler.get_results()) == 1
        scheduler.clear_results()
        assert len(scheduler.get_results()) == 0
