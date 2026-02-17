"""Dashboard reporter for comprehensive summary visualization.

Generates an HTML dashboard with aggregate statistics, trends,
and performance metrics across multiple test runs.

Example:
    >>> from venomqa.reporters import DashboardReporter
    >>> from venomqa.storage import ResultsRepository
    >>>
    >>> repo = ResultsRepository()
    >>> stats = repo.get_dashboard_stats(days=30)
    >>> trend = repo.get_trend_data(days=30)
    >>>
    >>> reporter = DashboardReporter()
    >>> reporter.save_dashboard(stats, trend, path="dashboard.html")
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.reporters.base import BaseReporter


class DashboardReporter(BaseReporter):
    """Generate comprehensive dashboard reports.

    Creates a standalone HTML dashboard showing:
    - Overall pass rate and statistics
    - Trend charts over time
    - Top failing journeys
    - Slowest journeys
    - Issue breakdown by severity
    - Recent run history

    Attributes:
        output_path: Default output path for the dashboard.
        title: Dashboard title.

    Example:
        >>> reporter = DashboardReporter(title="QA Dashboard")
        >>> reporter.save_dashboard(stats, trend_data)
    """

    @property
    def file_extension(self) -> str:
        """Return the HTML file extension."""
        return ".html"

    def __init__(
        self,
        output_path: str | Path | None = None,
        title: str = "VenomQA Dashboard",
    ) -> None:
        """Initialize the dashboard reporter.

        Args:
            output_path: Default path for saving the dashboard.
            title: Title displayed in the dashboard header.
        """
        super().__init__(output_path)
        self.title = title

    def generate(self, results: list[Any]) -> str:
        """Generate dashboard from journey results.

        For compatibility with BaseReporter. For full dashboard features,
        use generate_dashboard() with stats and trend data.

        Args:
            results: List of JourneyResult objects.

        Returns:
            HTML dashboard string.
        """
        # Calculate basic stats from results
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed

        stats = {
            "total_journeys": len({r.journey_name for r in results}),
            "total_runs": total,
            "total_passed": passed,
            "total_failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 100.0,
            "avg_duration_ms": sum(r.duration_ms for r in results) / total if total > 0 else 0,
            "total_issues": sum(len(r.issues) for r in results),
            "critical_issues": sum(
                sum(1 for i in r.issues if i.severity.value == "critical")
                for r in results
            ),
            "high_issues": sum(
                sum(1 for i in r.issues if i.severity.value == "high")
                for r in results
            ),
            "medium_issues": sum(
                sum(1 for i in r.issues if i.severity.value == "medium")
                for r in results
            ),
            "low_issues": sum(
                sum(1 for i in r.issues if i.severity.value == "low")
                for r in results
            ),
            "top_failing_journeys": [],
            "slowest_journeys": [],
        }

        return self.generate_dashboard(stats, [])

    def generate_dashboard(
        self,
        stats: dict[str, Any],
        trend_data: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a comprehensive dashboard.

        Args:
            stats: Dashboard statistics dictionary containing:
                - total_journeys: Number of unique journeys
                - total_runs: Total test runs
                - total_passed: Passed runs
                - total_failed: Failed runs
                - pass_rate: Pass rate percentage
                - avg_duration_ms: Average duration
                - total_issues: Total issues
                - critical_issues, high_issues, etc.
                - top_failing_journeys: List of (name, count) tuples
                - slowest_journeys: List of (name, duration) tuples
            trend_data: List of daily trend data points with:
                - date: Date string
                - total_runs: Runs on that day
                - passed_runs: Passed runs
                - failed_runs: Failed runs
                - pass_rate: Pass rate for the day
                - avg_duration_ms: Average duration

        Returns:
            Complete HTML dashboard string.
        """
        return self._build_dashboard(stats, trend_data or [])

    def save_dashboard(
        self,
        stats: dict[str, Any],
        trend_data: list[dict[str, Any]] | None = None,
        path: str | Path | None = None,
    ) -> Path:
        """Save the dashboard to a file.

        Args:
            stats: Dashboard statistics dictionary.
            trend_data: Optional trend data.
            path: Output path, or uses default output_path.

        Returns:
            Path to the saved file.
        """
        content = self.generate_dashboard(stats, trend_data)

        output_path = Path(path) if path else self.output_path
        if not output_path:
            raise ValueError("Output path required")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def _build_dashboard(
        self,
        stats: dict[str, Any],
        trend_data: list[dict[str, Any]],
    ) -> str:
        """Build the complete dashboard HTML."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>{html.escape(self.title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
{self._get_styles()}
    </style>
</head>
<body>
    <div class="dashboard">
        {self._render_header(stats, timestamp)}
        {self._render_stats_grid(stats)}
        {self._render_charts(stats, trend_data)}
        {self._render_details(stats)}
    </div>
    <script>
{self._get_chart_scripts(stats, trend_data)}
    </script>
</body>
</html>"""

    def _get_styles(self) -> str:
        """Generate dashboard CSS styles."""
        return """
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --success: #22c55e;
            --success-bg: #dcfce7;
            --warning: #f59e0b;
            --warning-bg: #fef3c7;
            --danger: #ef4444;
            --danger-bg: #fee2e2;
            --info: #3b82f6;
            --info-bg: #dbeafe;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --text: #1e293b;
            --text-muted: #64748b;
            --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            min-height: 100vh;
        }

        .dashboard {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        /* Header */
        .header {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 2rem;
            border-radius: 1rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow-lg);
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }

        .header-meta {
            opacity: 0.9;
            font-size: 0.875rem;
        }

        .header-status {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1.5rem;
            border-radius: 9999px;
            font-weight: 600;
            margin-top: 1rem;
        }

        .status-healthy {
            background: var(--success);
        }

        .status-warning {
            background: var(--warning);
        }

        .status-critical {
            background: var(--danger);
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--card-bg);
            border-radius: 0.75rem;
            padding: 1.5rem;
            box-shadow: var(--shadow);
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-lg);
        }

        .stat-icon {
            width: 3rem;
            height: 3rem;
            border-radius: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            margin: 0 auto 1rem;
        }

        .stat-icon.success { background: var(--success-bg); color: var(--success); }
        .stat-icon.danger { background: var(--danger-bg); color: var(--danger); }
        .stat-icon.warning { background: var(--warning-bg); color: var(--warning); }
        .stat-icon.info { background: var(--info-bg); color: var(--info); }

        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1.2;
        }

        .stat-label {
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }

        .stat-trend {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            font-size: 0.75rem;
            margin-top: 0.5rem;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
        }

        .trend-up { background: var(--success-bg); color: var(--success); }
        .trend-down { background: var(--danger-bg); color: var(--danger); }

        /* Charts */
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .card {
            background: var(--card-bg);
            border-radius: 0.75rem;
            box-shadow: var(--shadow);
            overflow: hidden;
        }

        .card-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .card-body {
            padding: 1.5rem;
        }

        .chart-container {
            position: relative;
            height: 300px;
        }

        /* Details Grid */
        .details-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
        }

        /* Tables */
        .table {
            width: 100%;
            border-collapse: collapse;
        }

        .table th,
        .table td {
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }

        .table th {
            font-weight: 600;
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .table tr:hover td {
            background: var(--bg);
        }

        .table tr:last-child td {
            border-bottom: none;
        }

        /* Progress Bar */
        .progress {
            height: 0.5rem;
            background: var(--border);
            border-radius: 9999px;
            overflow: hidden;
        }

        .progress-bar {
            height: 100%;
            border-radius: 9999px;
            transition: width 0.3s ease;
        }

        .progress-bar.success { background: var(--success); }
        .progress-bar.danger { background: var(--danger); }
        .progress-bar.warning { background: var(--warning); }

        /* Issue badges */
        .issue-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.25rem 0.75rem;
            border-radius: 0.375rem;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .issue-critical { background: #fecaca; color: #991b1b; }
        .issue-high { background: #fed7aa; color: #9a3412; }
        .issue-medium { background: #fef08a; color: #854d0e; }
        .issue-low { background: #bfdbfe; color: #1e40af; }

        /* Responsive */
        @media (max-width: 768px) {
            .dashboard { padding: 1rem; }
            .header { padding: 1.5rem; }
            .header h1 { font-size: 1.5rem; }
            .stat-value { font-size: 2rem; }
            .charts-grid { grid-template-columns: 1fr; }
            .details-grid { grid-template-columns: 1fr; }
        }
        """

    def _render_header(self, stats: dict[str, Any], timestamp: str) -> str:
        """Render the dashboard header."""
        pass_rate = stats.get("pass_rate", 100)

        if pass_rate >= 95:
            status_class = "status-healthy"
            status_text = "Healthy"
            status_icon = "&#10003;"
        elif pass_rate >= 80:
            status_class = "status-warning"
            status_text = "Needs Attention"
            status_icon = "&#9888;"
        else:
            status_class = "status-critical"
            status_text = "Critical"
            status_icon = "&#10007;"

        return f"""
        <div class="header">
            <h1>{html.escape(self.title)}</h1>
            <div class="header-meta">
                Last updated: {timestamp} | Auto-refreshes every 5 minutes
            </div>
            <div class="header-status {status_class}">
                {status_icon} System Status: {status_text}
            </div>
        </div>"""

    def _render_stats_grid(self, stats: dict[str, Any]) -> str:
        """Render the statistics cards grid."""
        pass_rate = stats.get("pass_rate", 100)
        rate_color = "success" if pass_rate >= 90 else "warning" if pass_rate >= 70 else "danger"

        avg_duration_ms = stats.get("avg_duration_ms", 0)
        if avg_duration_ms < 1000:
            duration_str = f"{avg_duration_ms:.0f}ms"
        else:
            duration_str = f"{avg_duration_ms / 1000:.1f}s"

        return f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon {rate_color}">%</div>
                <div class="stat-value" style="color: var(--{rate_color})">{pass_rate:.1f}%</div>
                <div class="stat-label">Pass Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon info">&#9776;</div>
                <div class="stat-value">{stats.get("total_runs", 0)}</div>
                <div class="stat-label">Total Runs</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon success">&#10003;</div>
                <div class="stat-value">{stats.get("total_passed", 0)}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon danger">&#10007;</div>
                <div class="stat-value">{stats.get("total_failed", 0)}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon info">&#9201;</div>
                <div class="stat-value">{duration_str}</div>
                <div class="stat-label">Avg Duration</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon warning">&#9888;</div>
                <div class="stat-value">{stats.get("total_issues", 0)}</div>
                <div class="stat-label">Total Issues</div>
            </div>
        </div>"""

    def _render_charts(
        self,
        stats: dict[str, Any],
        trend_data: list[dict[str, Any]],
    ) -> str:
        """Render the charts section."""
        return """
        <div class="charts-grid">
            <div class="card">
                <div class="card-header">Pass Rate Trend</div>
                <div class="card-body">
                    <div class="chart-container">
                        <canvas id="trendChart"></canvas>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">Issues by Severity</div>
                <div class="card-body">
                    <div class="chart-container">
                        <canvas id="issuesChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
        <div class="card" style="margin-bottom: 2rem;">
            <div class="card-header">Daily Runs</div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="runsChart"></canvas>
                </div>
            </div>
        </div>"""

    def _render_details(self, stats: dict[str, Any]) -> str:
        """Render the details tables."""
        # Top failing journeys
        failing_rows = ""
        for name, count in stats.get("top_failing_journeys", [])[:5]:
            failing_rows += f"""
            <tr>
                <td>{html.escape(name)}</td>
                <td><span class="issue-badge issue-high">{count} failures</span></td>
            </tr>"""

        if not failing_rows:
            failing_rows = "<tr><td colspan='2' style='text-align: center; color: var(--text-muted);'>No failing journeys</td></tr>"

        # Slowest journeys
        slow_rows = ""
        for name, duration in stats.get("slowest_journeys", [])[:5]:
            if duration < 1000:
                duration_str = f"{duration:.0f}ms"
            else:
                duration_str = f"{duration / 1000:.1f}s"

            slow_rows += f"""
            <tr>
                <td>{html.escape(name)}</td>
                <td>{duration_str}</td>
            </tr>"""

        if not slow_rows:
            slow_rows = "<tr><td colspan='2' style='text-align: center; color: var(--text-muted);'>No data available</td></tr>"

        # Issue breakdown
        issue_breakdown = f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">
            <div style="display: flex; justify-content: space-between; padding: 0.75rem; background: var(--bg); border-radius: 0.5rem;">
                <span>Critical</span>
                <span class="issue-badge issue-critical">{stats.get("critical_issues", 0)}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 0.75rem; background: var(--bg); border-radius: 0.5rem;">
                <span>High</span>
                <span class="issue-badge issue-high">{stats.get("high_issues", 0)}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 0.75rem; background: var(--bg); border-radius: 0.5rem;">
                <span>Medium</span>
                <span class="issue-badge issue-medium">{stats.get("medium_issues", 0)}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 0.75rem; background: var(--bg); border-radius: 0.5rem;">
                <span>Low</span>
                <span class="issue-badge issue-low">{stats.get("low_issues", 0)}</span>
            </div>
        </div>"""

        return f"""
        <div class="details-grid">
            <div class="card">
                <div class="card-header">Top Failing Journeys</div>
                <div class="card-body" style="padding: 0;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Journey</th>
                                <th>Failures</th>
                            </tr>
                        </thead>
                        <tbody>
                            {failing_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="card">
                <div class="card-header">Slowest Journeys</div>
                <div class="card-body" style="padding: 0;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Journey</th>
                                <th>Avg Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {slow_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="card">
                <div class="card-header">Issue Breakdown</div>
                <div class="card-body">
                    {issue_breakdown}
                </div>
            </div>
        </div>"""

    def _get_chart_scripts(
        self,
        stats: dict[str, Any],
        trend_data: list[dict[str, Any]],
    ) -> str:
        """Generate Chart.js initialization scripts."""
        # Prepare trend data
        dates = [d.get("date", "") for d in trend_data]
        pass_rates = [d.get("pass_rate", 100) for d in trend_data]
        [d.get("total_runs", 0) for d in trend_data]
        passed_runs = [d.get("passed_runs", 0) for d in trend_data]
        failed_runs = [d.get("failed_runs", 0) for d in trend_data]

        return f"""
        // Pass Rate Trend Chart
        new Chart(document.getElementById('trendChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(dates)},
                datasets: [{{
                    label: 'Pass Rate',
                    data: {json.dumps(pass_rates)},
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        min: 0,
                        max: 100,
                        title: {{
                            display: true,
                            text: 'Pass Rate (%)'
                        }}
                    }}
                }}
            }}
        }});

        // Issues Doughnut Chart
        new Chart(document.getElementById('issuesChart'), {{
            type: 'doughnut',
            data: {{
                labels: ['Critical', 'High', 'Medium', 'Low'],
                datasets: [{{
                    data: [
                        {stats.get("critical_issues", 0)},
                        {stats.get("high_issues", 0)},
                        {stats.get("medium_issues", 0)},
                        {stats.get("low_issues", 0)}
                    ],
                    backgroundColor: ['#dc2626', '#ea580c', '#d97706', '#2563eb'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ padding: 20 }}
                    }}
                }}
            }}
        }});

        // Daily Runs Stacked Bar Chart
        new Chart(document.getElementById('runsChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(dates)},
                datasets: [
                    {{
                        label: 'Passed',
                        data: {json.dumps(passed_runs)},
                        backgroundColor: '#22c55e'
                    }},
                    {{
                        label: 'Failed',
                        data: {json.dumps(failed_runs)},
                        backgroundColor: '#ef4444'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }},
                scales: {{
                    x: {{ stacked: true }},
                    y: {{
                        stacked: true,
                        title: {{
                            display: true,
                            text: 'Number of Runs'
                        }}
                    }}
                }}
            }}
        }});
        """
