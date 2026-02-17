"""JUnit XML reporter for CI/CD integration.

Generates JUnit XML reports compatible with CI systems like Jenkins,
GitHub Actions, GitLab CI, CircleCI, and others. Reports follow the
standard JUnit XML schema for test results.

Example:
    >>> from venomqa.reporters import JUnitReporter
    >>> reporter = JUnitReporter()
    >>> xml_output = reporter.generate(journey_results)
    >>> print(xml_output)  # JUnit XML format
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from venomqa.core.models import (
    JourneyResult,
    PathResult,
    StepResult,
)
from venomqa.reporters.base import BaseReporter


class JUnitReporter(BaseReporter):
    """Generate JUnit XML reports for CI integration.

    Produces JUnit XML documents with:
    - Testsuites container with aggregate statistics
    - Individual testsuites per journey
    - Testcases for each step and branch path
    - Failure elements with error details
    - Properties for journey metadata

    Attributes:
        output_path: Optional default path for saving reports.

    Example:
        >>> reporter = JUnitReporter(output_path="reports/junit.xml")
        >>> reporter.save(results)
        PosixPath('reports/junit.xml')
    """

    @property
    def file_extension(self) -> str:
        """Return the XML file extension."""
        return ".xml"

    def generate(self, results: list[JourneyResult]) -> str:
        """Generate a JUnit XML report from journey results.

        Args:
            results: List of JourneyResult objects from test execution.

        Returns:
            JUnit XML-formatted report string with XML declaration.
        """
        root = self._build_xml(results)
        self._indent_xml(root)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _build_xml(self, results: list[JourneyResult]) -> ET.Element:
        """Build the complete JUnit XML structure.

        Creates a testsuites element containing individual testsuite
        elements for each journey.

        Args:
            results: List of JourneyResult objects.

        Returns:
            Root Element containing the complete JUnit XML structure.
        """
        test_suites = ET.Element("testsuites")

        total_tests = sum(r.total_steps + r.total_paths for r in results)
        total_failures = sum(
            (r.total_steps - r.passed_steps) + (r.total_paths - r.passed_paths) for r in results
        )
        total_time = sum(r.duration_ms for r in results) / 1000

        test_suites.set("name", "VenomQA")
        test_suites.set("tests", str(total_tests))
        test_suites.set("failures", str(total_failures))
        test_suites.set("time", f"{total_time:.3f}")

        for result in results:
            test_suite = self._build_test_suite(result)
            test_suites.append(test_suite)

        return test_suites

    def _build_test_suite(self, result: JourneyResult) -> ET.Element:
        """Build a testsuite element for a single journey.

        Creates a testsuite containing testcases for each step
        and branch path, with properties for metadata.

        Args:
            result: JourneyResult object to convert to testsuite.

        Returns:
            Element representing the testsuite.
        """
        test_suite = ET.Element("testsuite")

        total_tests = result.total_steps + result.total_paths
        failures = (result.total_steps - result.passed_steps) + (
            result.total_paths - result.passed_paths
        )
        time = result.duration_ms / 1000

        test_suite.set("name", result.journey_name)
        test_suite.set("tests", str(total_tests))
        test_suite.set("failures", str(failures))
        test_suite.set("errors", "0")
        test_suite.set("skipped", "0")
        test_suite.set("time", f"{time:.3f}")
        test_suite.set("timestamp", result.started_at.isoformat())

        properties = ET.SubElement(test_suite, "properties")
        self._add_property(properties, "journey.success", str(result.success))
        self._add_property(properties, "journey.issues", str(len(result.issues)))

        for step in result.step_results:
            test_case = self._build_step_test_case(result.journey_name, step)
            test_suite.append(test_case)

        for branch in result.branch_results:
            for path in branch.path_results:
                test_case = self._build_path_test_case(
                    result.journey_name, branch.checkpoint_name, path
                )
                test_suite.append(test_case)

        return test_suite

    def _build_step_test_case(self, journey_name: str, step: StepResult) -> ET.Element:
        """Build a testcase element for a step result.

        Creates a testcase with timing information and failure
        details if the step failed.

        Args:
            journey_name: Name of the parent journey.
            step: StepResult object to convert to testcase.

        Returns:
            Element representing the testcase.
        """
        test_case = ET.Element("testcase")

        test_case.set("classname", f"{journey_name}.steps")
        test_case.set("name", step.step_name)
        test_case.set("time", f"{step.duration_ms / 1000:.3f}")

        if not step.success:
            failure = ET.SubElement(test_case, "failure")
            failure.set("message", step.error or "Step failed")
            failure.text = self._format_step_failure(step)

        system_out = ET.SubElement(test_case, "system-out")
        system_out.text = self._format_step_output(step)

        return test_case

    def _build_path_test_case(
        self, journey_name: str, checkpoint: str, path: PathResult
    ) -> ET.Element:
        """Build a testcase element for a branch path result.

        Creates a testcase representing a branch path execution,
        with failure details if the path failed.

        Args:
            journey_name: Name of the parent journey.
            checkpoint: Name of the checkpoint for this branch.
            path: PathResult object to convert to testcase.

        Returns:
            Element representing the testcase.
        """
        test_case = ET.Element("testcase")

        test_case.set("classname", f"{journey_name}.branches.{checkpoint}")
        test_case.set("name", path.path_name)
        test_case.set("time", "0.000")

        if not path.success:
            failure = ET.SubElement(test_case, "failure")
            failure.set("message", path.error or "Path failed")
            failure.text = self._format_path_failure(path)

        return test_case

    def _format_step_failure(self, step: StepResult) -> str:
        """Format step failure details for the failure element text.

        Args:
            step: Failed StepResult object.

        Returns:
            Formatted string with error details and request/response if available.
        """
        lines = [f"Step: {step.step_name}", f"Error: {step.error or 'Unknown error'}"]

        if step.request:
            lines.append(f"Request: {step.request}")
        if step.response:
            lines.append(f"Response: {step.response}")

        return "\n".join(lines)

    def _format_path_failure(self, path: PathResult) -> str:
        """Format path failure details for the failure element text.

        Args:
            path: Failed PathResult object.

        Returns:
            Formatted string with error details and failed steps.
        """
        lines = [f"Path: {path.path_name}", f"Error: {path.error or 'Unknown error'}"]

        failed_steps = [s for s in path.step_results if not s.success]
        if failed_steps:
            lines.append("Failed steps:")
            for step in failed_steps:
                lines.append(f"  - {step.step_name}: {step.error}")

        return "\n".join(lines)

    def _format_step_output(self, step: StepResult) -> str:
        """Format step output for the system-out element.

        Args:
            step: StepResult object.

        Returns:
            Formatted string with duration and request/response details.
        """
        parts = [f"Duration: {step.duration_ms}ms"]
        if step.request:
            parts.append(f"Request: {step.request}")
        if step.response:
            parts.append(f"Response: {step.response}")
        return " | ".join(parts)

    def _add_property(self, parent: ET.Element, name: str, value: str) -> None:
        """Add a property element to a properties container.

        Args:
            parent: Parent properties element.
            name: Property name.
            value: Property value.
        """
        prop = ET.SubElement(parent, "property")
        prop.set("name", name)
        prop.set("value", value)

    def _indent_xml(self, elem: ET.Element, level: int = 0) -> None:
        """Add indentation to XML for pretty-printing.

        Recursively adds newlines and indentation to make the XML
        human-readable.

        Note:
            Uses len(elem) instead of truthiness check to avoid
            DeprecationWarning about element truth value testing.

        Args:
            elem: Element to indent.
            level: Current indentation level (for recursion).
        """
        indent = "\n" + "  " * level
        if len(elem) > 0:
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
