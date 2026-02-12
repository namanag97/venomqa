"""HTML reporter with charts and interactive features."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.core.models import BranchResult, JourneyResult, Severity, StepResult
from venomqa.reporters.base import BaseReporter


class HTMLReporter(BaseReporter):
    """Generate beautiful HTML reports with charts and interactivity."""

    @property
    def file_extension(self) -> str:
        return ".html"

    def __init__(
        self,
        output_path: str | Path | None = None,
        title: str = "VenomQA Test Report",
        include_charts: bool = True,
    ):
        super().__init__(output_path)
        self.title = title
        self.include_charts = include_charts

    def generate(self, results: list[JourneyResult]) -> str:
        return self._build_html(results)

    def _build_html(self, results: list[JourneyResult]) -> str:
        summary = self._calculate_summary(results)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(self.title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --primary: #6366f1;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
            --dark: #1f2937;
            --light: #f3f4f6;
            --border: #e5e7eb;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                'Helvetica Neue', Arial, sans-serif;
            background: var(--light);
            color: var(--dark);
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem; }}
        .header {{
            background: linear-gradient(135deg, var(--primary), #4f46e5);
            color: white;
            padding: 2rem;
            margin-bottom: 2rem;
            border-radius: 1rem;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }}
        .header h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        .header .meta {{ opacity: 0.9; font-size: 0.9rem; }}
        .status-badge {{
            display: inline-block;
            padding: 0.25rem 1rem;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.875rem;
            margin-left: 1rem;
        }}
        .status-passed {{ background: var(--success); }}
        .status-failed {{ background: var(--danger); }}
        .grid {{ display: grid; gap: 1.5rem; }}
        .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
        .grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }}
        .card {{
            background: white;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .card-header {{
            background: var(--light);
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
        }}
        .card-body {{ padding: 1.5rem; }}
        .stat-card {{
            text-align: center;
            padding: 1.5rem;
        }}
        .stat-value {{ font-size: 2.5rem; font-weight: 700; }}
        .stat-label {{ color: #6b7280; font-size: 0.875rem; text-transform: uppercase; }}
        .stat-success .stat-value {{ color: var(--success); }}
        .stat-danger .stat-value {{ color: var(--danger); }}
        .stat-warning .stat-value {{ color: var(--warning); }}
        .stat-info .stat-value {{ color: var(--info); }}
        .chart-container {{ position: relative; height: 250px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{ background: var(--light); font-weight: 600; cursor: pointer; }}
        th:hover {{ background: var(--border); }}
        tr:hover {{ background: #f9fafb; }}
        .badge {{
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-success {{ background: #dcfce7; color: #166534; }}
        .badge-danger {{ background: #fee2e2; color: #991b1b; }}
        .badge-critical {{ background: #fecaca; color: #7f1d1d; }}
        .badge-high {{ background: #fed7aa; color: #9a3412; }}
        .badge-medium {{ background: #fef08a; color: #854d0e; }}
        .badge-low {{ background: #bfdbfe; color: #1e40af; }}
        .badge-info {{ background: #e0e7ff; color: #3730a3; }}
        .journey-item {{ margin-bottom: 1rem; }}
        .journey-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem;
            background: var(--light);
            border-radius: 0.5rem;
            cursor: pointer;
        }}
        .journey-header:hover {{ background: var(--border); }}
        .journey-content {{ padding: 1rem; display: none; }}
        .journey-content.active {{ display: block; }}
        .timeline {{ position: relative; padding-left: 2rem; }}
        .timeline::before {{
            content: '';
            position: absolute;
            left: 0.5rem;
            top: 0;
            bottom: 0;
            width: 2px;
            background: var(--border);
        }}
        .timeline-item {{ position: relative; padding-bottom: 1rem; }}
        .timeline-item::before {{
            content: '';
            position: absolute;
            left: -1.5rem;
            top: 0.5rem;
            width: 0.75rem;
            height: 0.75rem;
            border-radius: 50%;
            background: var(--primary);
        }}
        .timeline-item.success::before {{ background: var(--success); }}
        .timeline-item.failure::before {{ background: var(--danger); }}
        .filter-bar {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}
        .filter-bar input, .filter-bar select {{
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            font-size: 0.875rem;
        }}
        .filter-bar input {{ flex: 1; min-width: 200px; }}
        .issue-card {{
            border-left: 4px solid var(--danger);
            padding: 1rem;
            margin-bottom: 1rem;
            background: #fff;
            border-radius: 0 0.5rem 0.5rem 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .issue-critical {{ border-left-color: #dc2626; }}
        .issue-high {{ border-left-color: #ea580c; }}
        .issue-medium {{ border-left-color: #d97706; }}
        .issue-low {{ border-left-color: #2563eb; }}
        .code-block {{
            background: var(--dark);
            color: #e5e7eb;
            padding: 1rem;
            border-radius: 0.5rem;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }}
        .filter-btn {{
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            background: white;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 0.875rem;
        }}
        .filter-btn.active {{
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }}
        @media (max-width: 768px) {{
            .container {{ padding: 1rem; }}
            .header {{ padding: 1.5rem; border-radius: 0.5rem; }}
            .header h1 {{ font-size: 1.5rem; }}
            .stat-value {{ font-size: 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {self._render_header(results, summary)}
        {self._render_stats(summary)}
        {self._render_charts(results, summary)}
        {self._render_journeys(results)}
        {self._render_issues(results)}
    </div>
    <script>
        {self._render_javascript()}
    </script>
</body>
</html>"""

    def _calculate_summary(self, results: list[JourneyResult]) -> dict[str, Any]:
        total = len(results)
        passed = sum(1 for r in results if r.success)
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        total_paths = sum(r.total_paths for r in results)
        passed_paths = sum(r.passed_paths for r in results)
        total_issues = sum(len(r.issues) for r in results)
        total_duration_ms = sum(r.duration_ms for r in results)

        severity_counts = {s.value: 0 for s in Severity}
        for r in results:
            for issue in r.issues:
                severity_counts[issue.severity.value] += 1

        return {
            "total_journeys": total,
            "passed_journeys": passed,
            "failed_journeys": total - passed,
            "total_steps": total_steps,
            "passed_steps": passed_steps,
            "failed_steps": total_steps - passed_steps,
            "total_paths": total_paths,
            "passed_paths": passed_paths,
            "failed_paths": total_paths - passed_paths,
            "total_issues": total_issues,
            "total_duration_ms": total_duration_ms,
            "success_rate": (passed / total * 100) if total > 0 else 100.0,
            "severity_counts": severity_counts,
        }

    def _render_header(self, results: list[JourneyResult], summary: dict[str, Any]) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "passed" if summary["failed_journeys"] == 0 else "failed"
        status_text = "PASSED" if status == "passed" else "FAILED"
        return f"""
        <div class="header">
            <h1>
                {html.escape(self.title)}
                <span class="status-badge status-{status}">{status_text}</span>
            </h1>
            <div class="meta">
                Generated: {timestamp} |
                Duration: {summary["total_duration_ms"] / 1000:.2f}s |
                {summary["passed_journeys"]}/{summary["total_journeys"]} journeys passed
            </div>
        </div>"""

    def _render_stats(self, summary: dict[str, Any]) -> str:
        journeys_class = "stat-success" if summary["failed_journeys"] == 0 else "stat-danger"
        paths_class = "stat-success" if summary["failed_paths"] == 0 else "stat-warning"
        issues_class = "stat-success" if summary["total_issues"] == 0 else "stat-danger"
        return f"""
        <div class="grid grid-4" style="margin-bottom: 1.5rem;">
            <div class="card stat-card {journeys_class}">
                <div class="stat-value">
                    {summary["passed_journeys"]}/{summary["total_journeys"]}
                </div>
                <div class="stat-label">Journeys</div>
            </div>
            <div class="card stat-card stat-info">
                <div class="stat-value">{summary["passed_steps"]}/{summary["total_steps"]}</div>
                <div class="stat-label">Steps</div>
            </div>
            <div class="card stat-card {paths_class}">
                <div class="stat-value">{summary["passed_paths"]}/{summary["total_paths"]}</div>
                <div class="stat-label">Paths</div>
            </div>
            <div class="card stat-card {issues_class}">
                <div class="stat-value">{summary["total_issues"]}</div>
                <div class="stat-label">Issues</div>
            </div>
        </div>"""

    def _render_charts(self, results: list[JourneyResult], summary: dict[str, Any]) -> str:
        if not self.include_charts:
            return ""

        severity_data = summary["severity_counts"]
        return f"""
        <div class="grid grid-2" style="margin-bottom: 1.5rem;">
            <div class="card">
                <div class="card-header">Journey Results</div>
                <div class="card-body">
                    <div class="chart-container">
                        <canvas id="journeyChart"></canvas>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">Issues by Severity</div>
                <div class="card-body">
                    <div class="chart-container">
                        <canvas id="severityChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
        <script>
            new Chart(document.getElementById('journeyChart'), {{
                type: 'doughnut',
                data: {{
                    labels: ['Passed', 'Failed'],
                    datasets: [{{
                        data: [{summary["passed_journeys"]}, {summary["failed_journeys"]}],
                        backgroundColor: ['#22c55e', '#ef4444']
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ position: 'bottom' }} }}
                }}
            }});
            new Chart(document.getElementById('severityChart'), {{
                type: 'bar',
                data: {{
                    labels: ['Critical', 'High', 'Medium', 'Low', 'Info'],
                    datasets: [{{
                        label: 'Issues',
                        data: [
                            {severity_data.get("critical", 0)},
                            {severity_data.get("high", 0)},
                            {severity_data.get("medium", 0)},
                            {severity_data.get("low", 0)},
                            {severity_data.get("info", 0)}
                        ],
                        backgroundColor: ['#dc2626', '#ea580c', '#d97706', '#2563eb', '#6366f1']
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{ y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }} }}
                }}
            }});
        </script>"""

    def _render_journeys(self, results: list[JourneyResult]) -> str:
        if not results:
            return ""

        journey_items = []
        for i, result in enumerate(results):
            status_class = "success" if result.success else "failure"
            status_icon = "✓" if result.success else "✗"
            duration = result.duration_ms / 1000

            timeline = self._render_timeline(result)

            journey_items.append(f"""
            <div class="journey-item" data-journey="{html.escape(result.journey_name)}"
                 data-status="{status_class}">
                <div class="journey-header" onclick="toggleJourney({i})">
                    <span>
                        <strong>{status_icon} {html.escape(result.journey_name)}</strong>
                        <span style="margin-left: 1rem; color: #6b7280; font-weight: normal;">
                            {result.passed_steps}/{result.total_steps} steps | {duration:.2f}s
                        </span>
                    </span>
                    <span class="badge {"badge-success" if result.success else "badge-danger"}">
                        {"PASSED" if result.success else "FAILED"}
                    </span>
                </div>
                <div class="journey-content" id="journey-{i}">
                    {timeline}
                </div>
            </div>""")

        return f"""
        <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-header">
                Journey Timeline
                <span style="float: right; font-weight: normal;">
                    <button class="filter-btn active" onclick="filterJourneys('all')">All</button>
                    <button class="filter-btn" onclick="filterJourneys('success')">Passed</button>
                    <button class="filter-btn" onclick="filterJourneys('failure')">Failed</button>
                </span>
            </div>
            <div class="card-body">
                {"".join(journey_items)}
            </div>
        </div>"""

    def _render_timeline(self, result: JourneyResult) -> str:
        items = []

        for step in result.step_results:
            items.append(self._render_step_timeline(step))

        for branch in result.branch_results:
            items.append(self._render_branch_timeline(branch))

        if not items:
            return "<p style='color: #6b7280;'>No steps executed</p>"

        return f"<div class='timeline'>{chr(10).join(items)}</div>"

    def _render_step_timeline(self, step: StepResult) -> str:
        status_class = "success" if step.success else "failure"
        duration = f"{step.duration_ms:.0f}ms"
        error_html = ""
        if step.error:
            error_html = f"<div class='code-block'>{html.escape(step.error)}</div>"

        return f"""
        <div class="timeline-item {status_class}">
            <strong>{html.escape(step.step_name)}</strong>
            <span style="float: right; color: #6b7280;">{duration}</span>
            {error_html}
        </div>"""

    def _render_branch_timeline(self, branch: BranchResult) -> str:
        paths_html = []
        for path in branch.path_results:
            status = "✓" if path.success else "✗"
            paths_html.append(f"<li>{status} {html.escape(path.path_name)}</li>")

        return f"""
        <div class="timeline-item {"success" if branch.all_passed else "failure"}">
            <strong>Branch: {html.escape(branch.checkpoint_name)}</strong>
            <ul style="margin-top: 0.5rem; margin-left: 1rem;">
                {chr(10).join(paths_html)}
            </ul>
        </div>"""

    def _render_issues(self, results: list[JourneyResult]) -> str:
        all_issues = []
        for r in results:
            for issue in r.issues:
                all_issues.append((r.journey_name, issue))

        if not all_issues:
            return """
            <div class="card">
                <div class="card-header">Issues</div>
                <div class="card-body" style="text-align: center; color: #22c55e;">
                    ✓ No issues found
                </div>
            </div>"""

        issues_html = []
        for _journey_name, issue in all_issues:
            severity_class = f"issue-{issue.severity.value}"
            severity_badge = f"badge-{issue.severity.value}"

            request_html = ""
            if issue.request:
                request_html = f"""
                <div style="margin-top: 0.5rem;">
                    <strong>Request:</strong>
                    <div class="code-block">{html.escape(str(issue.request))}</div>
                </div>"""

            response_html = ""
            if issue.response:
                response_html = f"""
                <div style="margin-top: 0.5rem;">
                    <strong>Response:</strong>
                    <div class="code-block">{html.escape(str(issue.response))}</div>
                </div>"""

            suggestion_html = ""
            if issue.suggestion:
                suggestion_html = f"""
                <div style="margin-top: 0.5rem; padding: 0.5rem;
                     background: #f0fdf4; border-radius: 0.25rem;">
                    <strong>Suggestion:</strong> {html.escape(issue.suggestion)}
                </div>"""

            issues_html.append(f"""
            <div class="issue-card {severity_class}" data-severity="{issue.severity.value}">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <strong>{html.escape(issue.journey)} / {html.escape(issue.step)}</strong>
                    <span class="badge {severity_badge}">{issue.severity.value.upper()}</span>
                </div>
                <div style="margin-top: 0.5rem; color: #6b7280;">
                    Path: {html.escape(issue.path)}
                </div>
                <div class="code-block">{html.escape(issue.error)}</div>
                {request_html}
                {response_html}
                {suggestion_html}
            </div>""")

        return f"""
        <div class="card">
            <div class="card-header">
                Issues ({len(all_issues)})
                <span style="float: right; font-weight: normal;">
                    <button class="filter-btn active" onclick="filterIssues('all')">All</button>
                    <button class="filter-btn" onclick="filterIssues('critical')">Critical</button>
                    <button class="filter-btn" onclick="filterIssues('high')">High</button>
                    <button class="filter-btn" onclick="filterIssues('medium')">Medium</button>
                    <button class="filter-btn" onclick="filterIssues('low')">Low</button>
                </span>
            </div>
            <div class="card-body">
                {chr(10).join(issues_html)}
            </div>
        </div>"""

    def _render_javascript(self) -> str:
        return """
        function toggleJourney(index) {
            const content = document.getElementById('journey-' + index);
            content.classList.toggle('active');
        }

        function filterJourneys(status) {
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            document.querySelectorAll('.journey-item').forEach(item => {
                if (status === 'all' || item.dataset.status === status) {
                    item.style.display = 'block';
                } else {
                    item.style.display = 'none';
                }
            });
        }

        function filterIssues(severity) {
            document.querySelectorAll(
                '.card-header .filter-btn'
            ).forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            document.querySelectorAll('.issue-card').forEach(card => {
                if (severity === 'all' || card.dataset.severity === severity) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }

        document.querySelectorAll('th').forEach((th, index) => {
            th.addEventListener('click', () => {
                const table = th.closest('table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const asc = th.dataset.asc !== 'true';

                rows.sort((a, b) => {
                    const aVal = a.cells[index]?.textContent || '';
                    const bVal = b.cells[index]?.textContent || '';
                    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                });

                th.dataset.asc = asc;
                rows.forEach(row => tbody.appendChild(row));
            });
        });"""
