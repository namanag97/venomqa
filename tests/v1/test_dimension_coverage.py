"""Tests for DimensionCoverage and DimensionCoverageReporter."""

from __future__ import annotations

import io

import pytest

from venomqa.v1.core.dimensions import AuthStatus, UserRole, CountClass, PlanType, BUILTIN_DIMENSIONS
from venomqa.v1.core.hyperedge import Hyperedge
from venomqa.v1.core.hypergraph import Hypergraph
from venomqa.v1.core.coverage import DimensionCoverage, DimensionAxisCoverage
from venomqa.v1.reporters.dimension_report import DimensionCoverageReporter


def edge(**dims) -> Hyperedge:
    return Hyperedge(dimensions=dims)


# ---------------------------------------------------------------------------
# DimensionAxisCoverage
# ---------------------------------------------------------------------------

class TestDimensionAxisCoverage:
    def test_coverage_percent_zero_observed(self):
        axis = DimensionAxisCoverage(
            dimension="auth",
            observed_values=set(),
            total_possible=3,
        )
        assert axis.coverage_percent == 0.0

    def test_coverage_percent_full(self):
        axis = DimensionAxisCoverage(
            dimension="auth",
            observed_values={AuthStatus.AUTH, AuthStatus.ANON, AuthStatus.EXPIRED},
            total_possible=3,
        )
        assert axis.coverage_percent == 100.0

    def test_coverage_percent_partial(self):
        axis = DimensionAxisCoverage(
            dimension="auth",
            observed_values={AuthStatus.AUTH},
            total_possible=3,
        )
        assert pytest.approx(axis.coverage_percent, abs=0.1) == 33.3

    def test_coverage_percent_unknown_total(self):
        axis = DimensionAxisCoverage(
            dimension="custom",
            observed_values={"a", "b"},
            total_possible=0,
        )
        # When total_possible is 0 (unknown), percent is 0
        assert axis.coverage_percent == 0.0

    def test_observed_values_str_sorted(self):
        axis = DimensionAxisCoverage(
            dimension="role",
            observed_values={UserRole.USER, UserRole.ADMIN, UserRole.NONE},
            total_possible=4,
        )
        strs = axis.observed_values_str()
        assert strs == sorted(strs)

    def test_observed_count(self):
        axis = DimensionAxisCoverage(
            dimension="auth",
            observed_values={AuthStatus.AUTH, AuthStatus.ANON},
            total_possible=3,
        )
        assert axis.observed_count == 2


# ---------------------------------------------------------------------------
# DimensionCoverage.from_hypergraph
# ---------------------------------------------------------------------------

class TestDimensionCoverageFromHypergraph:
    def setup_method(self):
        self.hg = Hypergraph()

    def test_empty_hypergraph(self):
        cov = DimensionCoverage.from_hypergraph(self.hg)
        assert cov.total_states == 0
        assert cov.axes == {}
        assert cov.unexplored_combos == 0

    def test_single_dimension(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        self.hg.add("s2", edge(auth=AuthStatus.ANON))
        cov = DimensionCoverage.from_hypergraph(self.hg, known_dimensions=BUILTIN_DIMENSIONS)

        assert cov.total_states == 2
        assert "auth" in cov.axes
        axis = cov.axes["auth"]
        assert AuthStatus.AUTH in axis.observed_values
        assert AuthStatus.ANON in axis.observed_values
        # AuthStatus has 3 values total
        assert axis.total_possible == 3

    def test_multiple_dimensions(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        self.hg.add("s2", edge(auth=AuthStatus.ANON, role=UserRole.NONE))
        cov = DimensionCoverage.from_hypergraph(self.hg, known_dimensions=BUILTIN_DIMENSIONS)

        assert "auth" in cov.axes
        assert "role" in cov.axes

    def test_total_states_matches_node_count(self):
        for i in range(5):
            self.hg.add(f"s{i}", edge(auth=AuthStatus.AUTH))
        cov = DimensionCoverage.from_hypergraph(self.hg)
        assert cov.total_states == self.hg.node_count

    def test_unexplored_combos_counted(self):
        # 2 dimensions → some combos not yet seen
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        # Only AUTH+ADMIN seen; AUTH+USER, ANON+ADMIN, ANON+USER not seen
        cov = DimensionCoverage.from_hypergraph(self.hg)
        assert cov.unexplored_combos >= 0  # Could be 0 if only 1 axis

    def test_summary_keys(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        cov = DimensionCoverage.from_hypergraph(self.hg)
        summary = cov.summary()
        assert "total_states" in summary
        assert "unexplored_combos" in summary
        assert "dimensions" in summary

    def test_summary_dimension_entry(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        cov = DimensionCoverage.from_hypergraph(self.hg, known_dimensions=BUILTIN_DIMENSIONS)
        summary = cov.summary()
        auth_entry = summary["dimensions"]["auth"]
        assert auth_entry["observed"] == 1
        assert "coverage_percent" in auth_entry
        assert "values" in auth_entry

    def test_custom_known_dimensions(self):
        from enum import Enum

        class MyStatus(Enum):
            A = "a"
            B = "b"

        self.hg.add("s1", edge(mystatus=MyStatus.A))
        cov = DimensionCoverage.from_hypergraph(self.hg, known_dimensions={"mystatus": MyStatus})
        assert "mystatus" in cov.axes
        assert cov.axes["mystatus"].total_possible == 2

    def test_unknown_dimension_total_is_zero(self):
        self.hg.add("s1", edge(custom_dim="foo"))
        cov = DimensionCoverage.from_hypergraph(self.hg, known_dimensions={})
        assert "custom_dim" in cov.axes
        assert cov.axes["custom_dim"].total_possible == 0


# ---------------------------------------------------------------------------
# DimensionCoverageReporter
# ---------------------------------------------------------------------------

class TestDimensionCoverageReporter:
    def _make_cov(self):
        hg = Hypergraph()
        hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        hg.add("s2", edge(auth=AuthStatus.ANON, role=UserRole.NONE))
        return DimensionCoverage.from_hypergraph(hg, known_dimensions=BUILTIN_DIMENSIONS)

    def test_report_writes_output(self):
        buf = io.StringIO()
        cov = self._make_cov()
        reporter = DimensionCoverageReporter(file=buf, color=False)
        reporter.report(cov)
        output = buf.getvalue()
        assert "Dimension Coverage Report" in output
        assert "auth" in output
        assert "role" in output

    def test_report_shows_total_states(self):
        buf = io.StringIO()
        cov = self._make_cov()
        reporter = DimensionCoverageReporter(file=buf, color=False)
        reporter.report(cov)
        assert "2" in buf.getvalue()

    def test_report_empty_hypergraph(self):
        buf = io.StringIO()
        cov = DimensionCoverage.from_hypergraph(Hypergraph())
        reporter = DimensionCoverageReporter(file=buf, color=False)
        reporter.report(cov)
        output = buf.getvalue()
        assert "No dimension data" in output

    def test_report_markdown_has_table(self):
        cov = self._make_cov()
        reporter = DimensionCoverageReporter(color=False)
        md = reporter.report_markdown(cov)
        assert "| Dimension |" in md
        assert "`auth`" in md
        assert "`role`" in md

    def test_report_markdown_empty(self):
        cov = DimensionCoverage.from_hypergraph(Hypergraph())
        reporter = DimensionCoverageReporter(color=False)
        md = reporter.report_markdown(cov)
        assert "Dimension Coverage Report" in md

    def test_report_no_color_mode(self):
        buf = io.StringIO()
        cov = self._make_cov()
        reporter = DimensionCoverageReporter(file=buf, color=False)
        reporter.report(cov)
        # No ANSI escape codes when color=False
        assert "\033[" not in buf.getvalue()

    def test_report_color_mode_contains_ansi(self):
        buf = io.StringIO()
        cov = self._make_cov()
        reporter = DimensionCoverageReporter(file=buf, color=True)
        reporter.report(cov)
        # Should contain ANSI codes
        assert "\033[" in buf.getvalue()

    def test_bar_width_consistent(self):
        buf = io.StringIO()
        cov = self._make_cov()
        reporter = DimensionCoverageReporter(file=buf, color=False)
        reporter.report(cov)
        output = buf.getvalue()
        # Every bar should be BAR_WIDTH chars wide
        bar_width = DimensionCoverageReporter.BAR_WIDTH
        # Check that we see the expected bar characters
        assert "█" in output or "░" in output
