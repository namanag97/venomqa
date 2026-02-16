"""JUnit XML reporter for CI/CD integration."""

from __future__ import annotations

from xml.etree import ElementTree as ET
from io import StringIO

from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.invariant import Severity


class JUnitReporter:
    """Formats ExplorationResult as JUnit XML."""

    def report(self, result: ExplorationResult, suite_name: str = "venomqa") -> str:
        """Generate JUnit XML report."""
        testsuite = ET.Element("testsuite")
        testsuite.set("name", suite_name)
        testsuite.set("tests", str(len(result.graph.actions) + len(result.violations)))
        testsuite.set("failures", str(len(result.violations)))
        testsuite.set("errors", "0")
        testsuite.set("time", str(result.duration_ms / 1000))

        # Add a test case for each invariant violation
        for v in result.violations:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", f"invariant:{v.invariant_name}")
            testcase.set("classname", f"venomqa.invariants.{v.invariant_name}")

            failure = ET.SubElement(testcase, "failure")
            failure.set("type", v.severity.value)
            failure.set("message", v.message)

            # Add reproduction path as failure text
            if v.reproduction_path:
                path_text = "Reproduction path:\n"
                for t in v.reproduction_path:
                    path_text += f"  -> {t.action_name}\n"
                failure.text = path_text

        # Add a passing test case for explored actions
        explored_pairs = set()
        for t in result.graph.transitions:
            explored_pairs.add((t.from_state_id, t.action_name))

        for state_id, action_name in explored_pairs:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", f"action:{action_name}")
            testcase.set("classname", f"venomqa.actions.{action_name}")

        # Generate XML string
        tree = ET.ElementTree(testsuite)
        out = StringIO()
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(out, encoding="unicode")
        return out.getvalue()
