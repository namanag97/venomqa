"""Tests for all reporter formats in VenomQA."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import pytest

from venomqa.core.models import (
    BranchResult,
    Issue,
    JourneyResult,
    PathResult,
    Severity,
    StepResult,
)
from venomqa.reporters.base import BaseReporter
from venomqa.reporters.json_report import JSONReporter
from venomqa.reporters.junit import JUnitReporter
from venomqa.reporters.markdown import MarkdownReporter


class TestBaseReporter:
    """Tests for base reporter functionality."""

    def test_file_extension_property_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseReporter()

    def test_save_requires_output_path(self) -> None:
        class ConcreteReporter(BaseReporter):
            @property
            def file_extension(self):
                return ".test"

            def generate(self, results):
                return "test content"

        reporter = ConcreteReporter()

        with pytest.raises(ValueError, match="Output path required"):
            reporter.save([])

    def test_save_creates_parent_directories(self) -> None:
        class ConcreteReporter(BaseReporter):
            @property
            def file_extension(self):
                return ".test"

            def generate(self, results):
                return "test content"

        reporter = ConcreteReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "report.test"
            result_path = reporter.save([], path=output_path)

            assert result_path.exists()
            assert result_path.read_text() == "test content"


class TestMarkdownReporter:
    """Tests for Markdown reporter."""

    @pytest.fixture
    def sample_results(self) -> list[JourneyResult]:
        now = datetime.now()
        return [
            JourneyResult(
                journey_name="test_journey",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="step1",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=100.0,
                    ),
                ],
                issues=[],
                duration_ms=100.0,
            ),
        ]

    @pytest.fixture
    def failed_results(self) -> list[JourneyResult]:
        now = datetime.now()
        return [
            JourneyResult(
                journey_name="failed_journey",
                success=False,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="step1",
                        success=False,
                        started_at=now,
                        finished_at=now,
                        error="HTTP 500",
                        duration_ms=50.0,
                    ),
                ],
                issues=[
                    Issue(
                        journey="failed_journey",
                        path="main",
                        step="step1",
                        error="HTTP 500",
                        severity=Severity.HIGH,
                    ),
                ],
                duration_ms=50.0,
            ),
        ]

    def test_file_extension(self) -> None:
        reporter = MarkdownReporter()
        assert reporter.file_extension == ".md"

    def test_generate_header(self, sample_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate(sample_results)

        assert "# VenomQA Test Report" in report
        assert "**Status:** PASSED" in report
        assert "**Journeys:** 1/1 passed" in report

    def test_generate_header_with_failures(self, failed_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate(failed_results)

        assert "**Status:** FAILED" in report

    def test_generate_summary(self, sample_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate(sample_results)

        assert "## Summary" in report
        assert "| Total Duration |" in report
        assert "| Steps |" in report

    def test_generate_journey_details(self, sample_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate(sample_results)

        assert "## Journey Results" in report
        assert "test_journey" in report
        assert "step1" in report

    def test_generate_issues_section(self, failed_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate(failed_results)

        assert "## Issues" in report
        assert "failed_journey" in report
        assert "HTTP 500" in report

    def test_generate_suggestions_section(self, failed_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate(failed_results)

        assert "## Suggestions" in report

    def test_empty_results(self) -> None:
        reporter = MarkdownReporter()
        report = reporter.generate([])

        assert "# VenomQA Test Report" in report

    def test_save_to_file(self, sample_results: list[JourneyResult]) -> None:
        reporter = MarkdownReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            result_path = reporter.save(sample_results, path=output_path)

            assert result_path.exists()
            content = result_path.read_text()
            assert "# VenomQA Test Report" in content

    def test_branch_results_in_report(self) -> None:
        now = datetime.now()
        results = [
            JourneyResult(
                journey_name="branch_journey",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[],
                branch_results=[
                    BranchResult(
                        checkpoint_name="cp1",
                        path_results=[
                            PathResult(path_name="path1", success=True),
                            PathResult(path_name="path2", success=True),
                        ],
                    ),
                ],
                issues=[],
                duration_ms=100.0,
            ),
        ]

        reporter = MarkdownReporter()
        report = reporter.generate(results)

        assert "Branch: cp1" in report
        assert "path1" in report
        assert "path2" in report


class TestJSONReporter:
    """Tests for JSON reporter."""

    @pytest.fixture
    def sample_results(self) -> list[JourneyResult]:
        now = datetime.now()
        return [
            JourneyResult(
                journey_name="json_journey",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="json_step",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=100.0,
                    ),
                ],
                issues=[],
                duration_ms=100.0,
            ),
        ]

    def test_file_extension(self) -> None:
        reporter = JSONReporter()
        assert reporter.file_extension == ".json"

    def test_generate_valid_json(self, sample_results: list[JourneyResult]) -> None:
        reporter = JSONReporter()
        report = reporter.generate(sample_results)

        parsed = json.loads(report)
        assert "report" in parsed
        assert "summary" in parsed
        assert "journeys" in parsed

    def test_generate_report_metadata(self, sample_results: list[JourneyResult]) -> None:
        reporter = JSONReporter()
        report = reporter.generate(sample_results)

        parsed = json.loads(report)
        assert "generated_at" in parsed["report"]
        assert parsed["report"]["version"] == "1.0"

    def test_generate_summary_statistics(self, sample_results: list[JourneyResult]) -> None:
        reporter = JSONReporter()
        report = reporter.generate(sample_results)

        parsed = json.loads(report)
        summary = parsed["summary"]

        assert summary["total_journeys"] == 1
        assert summary["passed_journeys"] == 1
        assert summary["failed_journeys"] == 0
        assert summary["total_steps"] == 1
        assert summary["passed_steps"] == 1

    def test_generate_journey_data(self, sample_results: list[JourneyResult]) -> None:
        reporter = JSONReporter()
        report = reporter.generate(sample_results)

        parsed = json.loads(report)
        journey = parsed["journeys"][0]

        assert journey["journey_name"] == "json_journey"
        assert journey["success"] is True
        assert len(journey["step_results"]) == 1

    def test_serialize_issue(self) -> None:
        now = datetime.now()
        results = [
            JourneyResult(
                journey_name="issue_journey",
                success=False,
                started_at=now,
                finished_at=now,
                step_results=[],
                issues=[
                    Issue(
                        journey="issue_journey",
                        path="main",
                        step="step1",
                        error="Test error",
                        severity=Severity.HIGH,
                    ),
                ],
                duration_ms=0.0,
            ),
        ]

        reporter = JSONReporter()
        report = reporter.generate(results)

        parsed = json.loads(report)
        issue = parsed["journeys"][0]["issues"][0]

        assert issue["journey"] == "issue_journey"
        assert issue["step"] == "step1"
        assert issue["error"] == "Test error"
        assert issue["severity"] == "high"

    def test_custom_indent(self, sample_results: list[JourneyResult]) -> None:
        reporter = JSONReporter(indent=4)
        report = reporter.generate(sample_results)

        assert "    " in report

    def test_save_to_file(self, sample_results: list[JourneyResult]) -> None:
        reporter = JSONReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            result_path = reporter.save(sample_results, path=output_path)

            assert result_path.exists()
            content = result_path.read_text()
            parsed = json.loads(content)
            assert "report" in parsed

    def test_empty_results(self) -> None:
        reporter = JSONReporter()
        report = reporter.generate([])

        parsed = json.loads(report)
        assert parsed["summary"]["total_journeys"] == 0
        assert parsed["journeys"] == []


class TestJUnitReporter:
    """Tests for JUnit XML reporter."""

    @pytest.fixture
    def sample_results(self) -> list[JourneyResult]:
        now = datetime.now()
        return [
            JourneyResult(
                journey_name="junit_journey",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="junit_step",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=100.0,
                    ),
                ],
                issues=[],
                duration_ms=100.0,
            ),
        ]

    def test_file_extension(self) -> None:
        reporter = JUnitReporter()
        assert reporter.file_extension == ".xml"

    def test_generate_valid_xml(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        root = ElementTree.fromstring(report)
        assert root.tag == "testsuites"

    def test_generate_xml_declaration(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        assert report.startswith("<?xml")

    def test_generate_testsuites_attributes(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        root = ElementTree.fromstring(report)
        assert root.get("name") == "VenomQA"
        assert root.get("tests") == "1"
        assert root.get("failures") == "0"

    def test_generate_testsuite_per_journey(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        root = ElementTree.fromstring(report)
        testsuite = root.find("testsuite")

        assert testsuite is not None
        assert testsuite.get("name") == "junit_journey"

    def test_generate_testcase_per_step(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        root = ElementTree.fromstring(report)
        testcase = root.find(".//testcase")

        assert testcase is not None
        assert testcase.get("name") == "junit_step"
        assert testcase.get("classname") == "junit_journey.steps"

    def test_generate_failure_element(self) -> None:
        now = datetime.now()
        results = [
            JourneyResult(
                journey_name="failed_journey",
                success=False,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="failed_step",
                        success=False,
                        started_at=now,
                        finished_at=now,
                        error="Assertion failed",
                        duration_ms=50.0,
                    ),
                ],
                issues=[],
                duration_ms=50.0,
            ),
        ]

        reporter = JUnitReporter()
        report = reporter.generate(results)

        root = ElementTree.fromstring(report)
        failure = root.find(".//failure")

        assert failure is not None
        assert failure.get("message") == "Assertion failed"

    def test_generate_properties(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        root = ElementTree.fromstring(report)
        properties = root.findall(".//property")

        assert len(properties) >= 2

    def test_generate_branch_testcases(self) -> None:
        now = datetime.now()
        results = [
            JourneyResult(
                journey_name="branch_journey",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[],
                branch_results=[
                    BranchResult(
                        checkpoint_name="cp1",
                        path_results=[
                            PathResult(path_name="path1", success=True),
                        ],
                    ),
                ],
                issues=[],
                duration_ms=100.0,
            ),
        ]

        reporter = JUnitReporter()
        report = reporter.generate(results)

        root = ElementTree.fromstring(report)
        testcase = root.find(".//testcase")

        assert testcase is not None
        assert "branches" in testcase.get("classname", "")

    def test_save_to_file(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "junit.xml"
            result_path = reporter.save(sample_results, path=output_path)

            assert result_path.exists()
            content = result_path.read_text()
            assert "<?xml" in content

    def test_multiple_journeys(self) -> None:
        now = datetime.now()
        results = [
            JourneyResult(
                journey_name=f"journey_{i}",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="step",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=10.0,
                    ),
                ],
                issues=[],
                duration_ms=10.0,
            )
            for i in range(3)
        ]

        reporter = JUnitReporter()
        report = reporter.generate(results)

        root = ElementTree.fromstring(report)
        testsuites = root.findall("testsuite")

        assert len(testsuites) == 3

    def test_system_out_element(self, sample_results: list[JourneyResult]) -> None:
        reporter = JUnitReporter()
        report = reporter.generate(sample_results)

        root = ElementTree.fromstring(report)
        system_out = root.find(".//system-out")

        assert system_out is not None
        assert system_out.text is not None
        assert "Duration" in system_out.text


class TestReporterComparison:
    """Tests comparing different reporter outputs."""

    @pytest.fixture
    def mixed_results(self) -> list[JourneyResult]:
        now = datetime.now()
        return [
            JourneyResult(
                journey_name="mixed_journey",
                success=False,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="success_step",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=50.0,
                    ),
                    StepResult(
                        step_name="failed_step",
                        success=False,
                        started_at=now,
                        finished_at=now,
                        error="HTTP 500",
                        duration_ms=30.0,
                    ),
                ],
                branch_results=[
                    BranchResult(
                        checkpoint_name="cp1",
                        path_results=[
                            PathResult(path_name="path1", success=True),
                            PathResult(path_name="path2", success=False, error="Path failed"),
                        ],
                    ),
                ],
                issues=[
                    Issue(
                        journey="mixed_journey",
                        path="main",
                        step="failed_step",
                        error="HTTP 500",
                        severity=Severity.HIGH,
                    ),
                ],
                duration_ms=80.0,
            ),
        ]

    def test_all_reporters_generate_content(self, mixed_results: list[JourneyResult]) -> None:
        reporters = [
            MarkdownReporter(),
            JSONReporter(),
            JUnitReporter(),
        ]

        for reporter in reporters:
            output = reporter.generate(mixed_results)
            assert len(output) > 0

    def test_all_reporters_handle_empty_results(self) -> None:
        reporters = [
            MarkdownReporter(),
            JSONReporter(),
            JUnitReporter(),
        ]

        for reporter in reporters:
            output = reporter.generate([])
            assert len(output) > 0

    def test_all_reporters_save_to_file(self, mixed_results: list[JourneyResult]) -> None:
        reporters = [
            (MarkdownReporter(), "report.md"),
            (JSONReporter(), "report.json"),
            (JUnitReporter(), "junit.xml"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            for reporter, filename in reporters:
                output_path = Path(tmpdir) / filename
                result_path = reporter.save(mixed_results, path=output_path)

                assert result_path.exists()
                assert result_path.stat().st_size > 0
