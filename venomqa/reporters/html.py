"""Professional HTML reporter with interactive visualizations.

Generates beautiful, self-contained HTML reports featuring:
- Interactive journey tree view with expandable branches
- Request/response viewer with syntax highlighting
- Timing breakdown charts using Chart.js
- Responsive design with modern CSS
- Filter and search functionality
- Dark/light mode support

Example:
    >>> from venomqa.reporters import HTMLReporter
    >>> reporter = HTMLReporter(title="API Test Results")
    >>> reporter.save(results, path="report.html")
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.core.models import BranchResult, JourneyResult, Severity, StepResult
from venomqa.reporters.base import BaseReporter


class HTMLReporter(BaseReporter):
    """Generate professional HTML reports with interactive features.

    Produces self-contained HTML documents with:
    - Modern, responsive CSS design
    - Chart.js visualizations for results and timing
    - Interactive journey tree with collapsible branches
    - Tabbed request/response viewer
    - Timeline waterfall charts
    - Filter and search functionality

    Attributes:
        output_path: Optional default path for saving reports.
        title: Title displayed in the report header.
        include_charts: Whether to include Chart.js visualizations.
        dark_mode: Whether to use dark mode by default.

    Example:
        >>> reporter = HTMLReporter(
        ...     title="E2E Test Results",
        ...     include_charts=True,
        ... )
        >>> reporter.save(results, path="reports/test.html")
    """

    @property
    def file_extension(self) -> str:
        """Return the HTML file extension."""
        return ".html"

    def __init__(
        self,
        output_path: str | Path | None = None,
        title: str = "VenomQA Test Report",
        include_charts: bool = True,
        dark_mode: bool = False,
    ) -> None:
        """Initialize the HTML reporter.

        Args:
            output_path: Default path for saving reports.
            title: Title displayed in the report header and browser tab.
            include_charts: Whether to include Chart.js charts.
            dark_mode: Whether to use dark mode by default.
        """
        super().__init__(output_path)
        self.title = title
        self.include_charts = include_charts
        self.dark_mode = dark_mode

    def generate(self, results: list[JourneyResult]) -> str:
        """Generate a complete HTML report from journey results.

        Args:
            results: List of JourneyResult objects from test execution.

        Returns:
            Complete, self-contained HTML document string.
        """
        return self._build_html(results)

    def _build_html(self, results: list[JourneyResult]) -> str:
        """Build the complete HTML document."""
        summary = self._calculate_summary(results)
        theme_class = "dark" if self.dark_mode else ""

        return f"""<!DOCTYPE html>
<html lang="en" class="{theme_class}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(self.title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
{self._get_styles()}
    </style>
</head>
<body>
    <div class="container">
        {self._render_header(results, summary)}
        {self._render_dashboard(summary)}
        {self._render_charts(results, summary)}
        {self._render_journey_tree(results)}
        {self._render_timing_analysis(results)}
        {self._render_issues(results)}
    </div>
    <script>
{self._get_javascript()}
    </script>
</body>
</html>"""

    def _get_styles(self) -> str:
        """Generate CSS styles."""
        return """
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --primary-light: #818cf8;
            --success: #22c55e;
            --success-light: #dcfce7;
            --success-dark: #166534;
            --warning: #f59e0b;
            --warning-light: #fef08a;
            --danger: #ef4444;
            --danger-light: #fee2e2;
            --danger-dark: #991b1b;
            --info: #3b82f6;
            --info-light: #dbeafe;
            --dark: #1f2937;
            --light: #f3f4f6;
            --border: #e5e7eb;
            --bg: #ffffff;
            --bg-secondary: #f9fafb;
            --text: #1f2937;
            --text-secondary: #6b7280;
            --shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
        }

        html.dark {
            --bg: #111827;
            --bg-secondary: #1f2937;
            --text: #f9fafb;
            --text-secondary: #9ca3af;
            --border: #374151;
            --light: #1f2937;
            --dark: #f9fafb;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                'Helvetica Neue', Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            font-size: 14px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        /* Header */
        .header {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 2rem;
            margin-bottom: 2rem;
            border-radius: 1rem;
            box-shadow: var(--shadow-lg);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }

        .header-content h1 {
            font-size: 1.75rem;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .header-content .meta {
            opacity: 0.9;
            font-size: 0.875rem;
        }

        .header-actions {
            display: flex;
            gap: 0.5rem;
        }

        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-light {
            background: rgba(255,255,255,0.2);
            color: white;
        }

        .btn-light:hover {
            background: rgba(255,255,255,0.3);
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 1rem;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.875rem;
            gap: 0.5rem;
        }

        .status-passed { background: var(--success); }
        .status-failed { background: var(--danger); }

        /* Dashboard */
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            padding: 1.5rem;
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow);
        }

        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1.2;
        }

        .stat-label {
            color: var(--text-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }

        .stat-success .stat-value { color: var(--success); }
        .stat-danger .stat-value { color: var(--danger); }
        .stat-warning .stat-value { color: var(--warning); }
        .stat-info .stat-value { color: var(--info); }

        /* Cards */
        .card {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            box-shadow: var(--shadow);
            overflow: hidden;
            margin-bottom: 1.5rem;
        }

        .card-header {
            background: var(--bg-secondary);
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.5rem;
        }

        .card-header-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .card-body { padding: 1.5rem; }

        /* Charts */
        .chart-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .chart-container {
            position: relative;
            height: 280px;
        }

        /* Journey Tree */
        .journey-tree {
            font-family: inherit;
        }

        .journey-item {
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            overflow: hidden;
        }

        .journey-header {
            display: flex;
            align-items: center;
            padding: 1rem 1.5rem;
            background: var(--bg);
            cursor: pointer;
            transition: background 0.2s;
            gap: 1rem;
        }

        .journey-header:hover {
            background: var(--bg-secondary);
        }

        .journey-status-icon {
            width: 3rem;
            height: 3rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            flex-shrink: 0;
        }

        .journey-status-icon.success {
            background: var(--success-light);
            color: var(--success);
        }

        .journey-status-icon.failure {
            background: var(--danger-light);
            color: var(--danger);
        }

        .journey-info { flex: 1; }

        .journey-title {
            font-weight: 600;
            font-size: 1.1rem;
            margin-bottom: 0.25rem;
        }

        .journey-meta {
            display: flex;
            gap: 1.5rem;
            color: var(--text-secondary);
            font-size: 0.875rem;
            flex-wrap: wrap;
        }

        .journey-toggle {
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            background: var(--bg);
            border-radius: 0.5rem;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.875rem;
        }

        .journey-toggle:hover {
            background: var(--bg-secondary);
        }

        .journey-content {
            display: none;
            border-top: 1px solid var(--border);
            background: var(--bg-secondary);
        }

        .journey-content.active { display: block; }

        /* Step Tree */
        .step-tree {
            padding: 1rem 1.5rem;
        }

        .tree-node {
            position: relative;
            padding-left: 1.5rem;
        }

        .tree-node::before {
            content: '';
            position: absolute;
            left: 0.5rem;
            top: 0;
            bottom: 0;
            width: 1px;
            background: var(--border);
        }

        .tree-node:last-child::before {
            height: 1.25rem;
        }

        .tree-item {
            position: relative;
            padding: 0.5rem 0;
        }

        .tree-item::before {
            content: '';
            position: absolute;
            left: -1rem;
            top: 1rem;
            width: 0.75rem;
            height: 1px;
            background: var(--border);
        }

        .tree-item-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.5rem 0.75rem;
            border-radius: 0.375rem;
            cursor: pointer;
            transition: background 0.2s;
        }

        .tree-item-header:hover {
            background: var(--light);
        }

        .step-icon {
            width: 1.25rem;
            height: 1.25rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.75rem;
            flex-shrink: 0;
        }

        .step-icon.success { background: var(--success); color: white; }
        .step-icon.failure { background: var(--danger); color: white; }
        .step-icon.skipped { background: var(--text-secondary); color: white; }
        .step-icon.checkpoint { background: var(--warning); color: white; }
        .step-icon.branch { background: var(--info); color: white; }

        .step-name { font-weight: 500; }
        .step-duration {
            margin-left: auto;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }

        .step-details {
            display: none;
            margin-left: 2rem;
            padding: 1rem;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            margin-top: 0.5rem;
        }

        .step-details.active { display: block; }

        /* Request/Response Viewer */
        .request-response {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        @media (max-width: 768px) {
            .request-response {
                grid-template-columns: 1fr;
            }
        }

        .rr-section {
            background: var(--bg-secondary);
            border-radius: 0.5rem;
            overflow: hidden;
        }

        .rr-header {
            padding: 0.5rem 1rem;
            background: var(--dark);
            color: white;
            font-weight: 500;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .rr-content {
            padding: 1rem;
            max-height: 300px;
            overflow: auto;
        }

        .http-method {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 0.25rem;
            font-weight: 600;
            font-size: 0.75rem;
            font-family: monospace;
        }

        .method-get { background: #dbeafe; color: #1e40af; }
        .method-post { background: #dcfce7; color: #166534; }
        .method-put { background: #fef3c7; color: #92400e; }
        .method-delete { background: #fee2e2; color: #991b1b; }
        .method-patch { background: #e0e7ff; color: #3730a3; }

        .status-code {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 0.25rem;
            font-weight: 600;
            font-size: 0.75rem;
            font-family: monospace;
            margin-left: auto;
        }

        .status-2xx { background: var(--success-light); color: var(--success-dark); }
        .status-3xx { background: var(--info-light); color: #1e40af; }
        .status-4xx { background: var(--warning-light); color: #92400e; }
        .status-5xx { background: var(--danger-light); color: var(--danger-dark); }

        /* Code Block */
        .code-block {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 1rem;
            border-radius: 0.5rem;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 0.8125rem;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .json-key { color: #9cdcfe; }
        .json-string { color: #ce9178; }
        .json-number { color: #b5cea8; }
        .json-boolean { color: #569cd6; }
        .json-null { color: #569cd6; }

        /* Waterfall Chart */
        .waterfall {
            padding: 1rem 0;
        }

        .waterfall-row {
            display: flex;
            align-items: center;
            padding: 0.375rem 0;
            gap: 1rem;
        }

        .waterfall-label {
            width: 180px;
            font-size: 0.8125rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex-shrink: 0;
        }

        .waterfall-bar-container {
            flex: 1;
            height: 20px;
            background: var(--light);
            border-radius: 0.25rem;
            overflow: hidden;
            position: relative;
        }

        .waterfall-bar {
            height: 100%;
            border-radius: 0.25rem;
            transition: width 0.3s ease;
        }

        .waterfall-bar.success { background: var(--success); }
        .waterfall-bar.failure { background: var(--danger); }

        .waterfall-value {
            width: 60px;
            text-align: right;
            font-size: 0.8125rem;
            color: var(--text-secondary);
        }

        /* Timing Analysis */
        .timing-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
        }

        .timing-card {
            padding: 1rem;
            background: var(--bg-secondary);
            border-radius: 0.5rem;
            border-left: 4px solid var(--primary);
        }

        .timing-card-title {
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .timing-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.5rem;
            font-size: 0.8125rem;
        }

        .timing-stat-label {
            color: var(--text-secondary);
            text-transform: uppercase;
            font-size: 0.625rem;
            letter-spacing: 0.05em;
        }

        .timing-stat-value {
            font-weight: 600;
        }

        /* Issues */
        .issue-card {
            border-left: 4px solid var(--danger);
            padding: 1rem;
            margin-bottom: 1rem;
            background: var(--bg);
            border-radius: 0 0.5rem 0.5rem 0;
        }

        .issue-critical { border-left-color: #dc2626; }
        .issue-high { border-left-color: #ea580c; }
        .issue-medium { border-left-color: #d97706; }
        .issue-low { border-left-color: #2563eb; }
        .issue-info { border-left-color: #6b7280; }

        .issue-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.5rem;
            flex-wrap: wrap;
            gap: 0.5rem;
        }

        .issue-location {
            font-weight: 600;
        }

        .badge {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .badge-success { background: var(--success-light); color: var(--success-dark); }
        .badge-danger { background: var(--danger-light); color: var(--danger-dark); }
        .badge-critical { background: #fecaca; color: #7f1d1d; }
        .badge-high { background: #fed7aa; color: #9a3412; }
        .badge-medium { background: var(--warning-light); color: #854d0e; }
        .badge-low { background: #bfdbfe; color: #1e40af; }
        .badge-info { background: #e5e7eb; color: #374151; }

        .issue-message {
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }

        .issue-suggestion {
            background: var(--success-light);
            color: var(--success-dark);
            padding: 0.5rem 0.75rem;
            border-radius: 0.375rem;
            font-size: 0.875rem;
        }

        /* Filter Bar */
        .filter-bar {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 0.375rem 0.75rem;
            border: 1px solid var(--border);
            background: var(--bg);
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.8125rem;
            transition: all 0.2s;
        }

        .filter-btn:hover {
            background: var(--bg-secondary);
        }

        .filter-btn.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        /* Search */
        .search-input {
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            font-size: 0.875rem;
            background: var(--bg);
            color: var(--text);
            min-width: 200px;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }

        /* Utilities */
        .text-success { color: var(--success); }
        .text-danger { color: var(--danger); }
        .text-warning { color: var(--warning); }
        .text-info { color: var(--info); }
        .text-muted { color: var(--text-secondary); }

        .mt-1 { margin-top: 0.25rem; }
        .mt-2 { margin-top: 0.5rem; }
        .mt-4 { margin-top: 1rem; }
        .mb-2 { margin-bottom: 0.5rem; }
        .mb-4 { margin-bottom: 1rem; }

        @media (max-width: 768px) {
            .container { padding: 1rem; }
            .header { padding: 1.5rem; flex-direction: column; align-items: flex-start; }
            .header h1 { font-size: 1.25rem; }
            .stat-value { font-size: 2rem; }
            .journey-header { flex-direction: column; align-items: flex-start; }
            .journey-toggle { width: 100%; text-align: center; margin-top: 0.5rem; }
        }
        """

    def _get_javascript(self) -> str:
        """Generate JavaScript for interactivity."""
        return """
        // Toggle journey details
        function toggleJourney(journeyId) {
            const content = document.getElementById('journey-content-' + journeyId);
            const btn = document.getElementById('journey-toggle-' + journeyId);

            if (content.classList.contains('active')) {
                content.classList.remove('active');
                btn.textContent = 'Show Details';
            } else {
                content.classList.add('active');
                btn.textContent = 'Hide Details';
            }
        }

        // Toggle step details
        function toggleStep(stepId) {
            const details = document.getElementById('step-details-' + stepId);
            details.classList.toggle('active');
        }

        // Filter journeys
        function filterJourneys(status) {
            // Update active button
            document.querySelectorAll('.journey-filter .filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');

            // Filter items
            document.querySelectorAll('.journey-item').forEach(item => {
                if (status === 'all' || item.dataset.status === status) {
                    item.style.display = 'block';
                } else {
                    item.style.display = 'none';
                }
            });
        }

        // Filter issues
        function filterIssues(severity) {
            // Update active button
            document.querySelectorAll('.issue-filter .filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');

            // Filter items
            document.querySelectorAll('.issue-card').forEach(card => {
                if (severity === 'all' || card.dataset.severity === severity) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }

        // Search journeys
        function searchJourneys(query) {
            const lowerQuery = query.toLowerCase();
            document.querySelectorAll('.journey-item').forEach(item => {
                const name = item.dataset.name.toLowerCase();
                if (name.includes(lowerQuery) || query === '') {
                    item.style.display = 'block';
                } else {
                    item.style.display = 'none';
                }
            });
        }

        // Toggle dark mode
        function toggleDarkMode() {
            document.documentElement.classList.toggle('dark');
        }

        // Expand all journeys
        function expandAllJourneys() {
            document.querySelectorAll('.journey-content').forEach(content => {
                content.classList.add('active');
            });
            document.querySelectorAll('[id^="journey-toggle-"]').forEach(btn => {
                btn.textContent = 'Hide Details';
            });
        }

        // Collapse all journeys
        function collapseAllJourneys() {
            document.querySelectorAll('.journey-content').forEach(content => {
                content.classList.remove('active');
            });
            document.querySelectorAll('[id^="journey-toggle-"]').forEach(btn => {
                btn.textContent = 'Show Details';
            });
        }

        // Format JSON for display
        function formatJSON(obj) {
            if (typeof obj === 'string') {
                try {
                    obj = JSON.parse(obj);
                } catch (e) {
                    return obj;
                }
            }
            return JSON.stringify(obj, null, 2);
        }

        // Initialize tooltips and other interactive elements
        document.addEventListener('DOMContentLoaded', function() {
            // Auto-expand failed journeys
            document.querySelectorAll('.journey-item[data-status="failure"]').forEach(item => {
                const journeyId = item.id.replace('journey-', '');
                const content = document.getElementById('journey-content-' + journeyId);
                const btn = document.getElementById('journey-toggle-' + journeyId);
                if (content && btn) {
                    content.classList.add('active');
                    btn.textContent = 'Hide Details';
                }
            });
        });
        """

    def _calculate_summary(self, results: list[JourneyResult]) -> dict[str, Any]:
        """Calculate aggregate statistics from journey results."""
        total = len(results)
        passed = sum(1 for r in results if r.success)
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        total_paths = sum(r.total_paths for r in results)
        passed_paths = sum(r.passed_paths for r in results)
        total_issues = sum(len(r.issues) for r in results)
        total_duration_ms = sum(r.duration_ms for r in results)

        durations = [r.duration_ms for r in results]
        avg_duration = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0

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
            "avg_duration_ms": avg_duration,
            "min_duration_ms": min_duration,
            "max_duration_ms": max_duration,
            "success_rate": (passed / total * 100) if total > 0 else 100.0,
            "severity_counts": severity_counts,
        }

    def _render_header(self, results: list[JourneyResult], summary: dict[str, Any]) -> str:
        """Render the report header."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "passed" if summary["failed_journeys"] == 0 else "failed"
        status_text = "PASSED" if status == "passed" else "FAILED"
        status_icon = "&#10003;" if status == "passed" else "&#10007;"

        return f"""
        <div class="header">
            <div class="header-content">
                <h1>
                    <span>{html.escape(self.title)}</span>
                    <span class="status-badge status-{status}">{status_icon} {status_text}</span>
                </h1>
                <div class="meta">
                    Generated: {timestamp} |
                    Duration: {summary["total_duration_ms"] / 1000:.2f}s |
                    {summary["passed_journeys"]}/{summary["total_journeys"]} journeys passed
                </div>
            </div>
            <div class="header-actions">
                <button class="btn btn-light" onclick="expandAllJourneys()">Expand All</button>
                <button class="btn btn-light" onclick="collapseAllJourneys()">Collapse All</button>
                <button class="btn btn-light" onclick="toggleDarkMode()">Toggle Theme</button>
            </div>
        </div>"""

    def _render_dashboard(self, summary: dict[str, Any]) -> str:
        """Render the statistics dashboard."""
        pass_rate = summary["success_rate"]
        rate_class = "stat-success" if pass_rate >= 90 else "stat-warning" if pass_rate >= 70 else "stat-danger"

        return f"""
        <div class="dashboard">
            <div class="stat-card {rate_class}">
                <div class="stat-value">{pass_rate:.1f}%</div>
                <div class="stat-label">Pass Rate</div>
            </div>
            <div class="stat-card stat-info">
                <div class="stat-value">{summary["total_journeys"]}</div>
                <div class="stat-label">Total Journeys</div>
            </div>
            <div class="stat-card stat-success">
                <div class="stat-value">{summary["passed_journeys"]}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card stat-danger">
                <div class="stat-value">{summary["failed_journeys"]}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card stat-info">
                <div class="stat-value">{summary["total_steps"]}</div>
                <div class="stat-label">Total Steps</div>
            </div>
            <div class="stat-card stat-warning">
                <div class="stat-value">{summary["total_issues"]}</div>
                <div class="stat-label">Issues</div>
            </div>
        </div>"""

    def _render_charts(self, results: list[JourneyResult], summary: dict[str, Any]) -> str:
        """Render Chart.js visualizations."""
        if not self.include_charts:
            return ""

        severity_data = summary["severity_counts"]

        # Prepare journey duration data
        journey_names = [html.escape(r.journey_name[:20]) for r in results[:10]]
        journey_durations = [r.duration_ms for r in results[:10]]
        journey_colors = ['#22c55e' if r.success else '#ef4444' for r in results[:10]]

        return f"""
        <div class="chart-grid">
            <div class="card">
                <div class="card-header">
                    <span class="card-header-title">Journey Results</span>
                </div>
                <div class="card-body">
                    <div class="chart-container">
                        <canvas id="resultsChart"></canvas>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-header-title">Issues by Severity</span>
                </div>
                <div class="card-body">
                    <div class="chart-container">
                        <canvas id="severityChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-header-title">Journey Durations</span>
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="durationChart"></canvas>
                </div>
            </div>
        </div>

        <script>
            // Results Doughnut Chart
            new Chart(document.getElementById('resultsChart'), {{
                type: 'doughnut',
                data: {{
                    labels: ['Passed', 'Failed'],
                    datasets: [{{
                        data: [{summary["passed_journeys"]}, {summary["failed_journeys"]}],
                        backgroundColor: ['#22c55e', '#ef4444'],
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

            // Severity Bar Chart
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
                        backgroundColor: ['#dc2626', '#ea580c', '#d97706', '#2563eb', '#6b7280']
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
                            beginAtZero: true,
                            ticks: {{ stepSize: 1 }}
                        }}
                    }}
                }}
            }});

            // Duration Bar Chart
            new Chart(document.getElementById('durationChart'), {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(journey_names)},
                    datasets: [{{
                        label: 'Duration (ms)',
                        data: {json.dumps(journey_durations)},
                        backgroundColor: {json.dumps(journey_colors)}
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    plugins: {{
                        legend: {{ display: false }}
                    }},
                    scales: {{
                        x: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: 'Duration (ms)'
                            }}
                        }}
                    }}
                }}
            }});
        </script>"""

    def _render_journey_tree(self, results: list[JourneyResult]) -> str:
        """Render the interactive journey tree."""
        if not results:
            return ""

        journey_items = []
        for i, result in enumerate(results):
            journey_items.append(self._render_single_journey(result, i))

        return f"""
        <div class="card">
            <div class="card-header">
                <span class="card-header-title">
                    <span>Journey Details</span>
                </span>
                <div class="filter-bar journey-filter">
                    <input type="text" class="search-input" placeholder="Search journeys..."
                           oninput="searchJourneys(this.value)">
                    <button class="filter-btn active" onclick="filterJourneys('all')">All</button>
                    <button class="filter-btn" onclick="filterJourneys('success')">Passed</button>
                    <button class="filter-btn" onclick="filterJourneys('failure')">Failed</button>
                </div>
            </div>
            <div class="card-body journey-tree">
                {"".join(journey_items)}
            </div>
        </div>"""

    def _render_single_journey(self, result: JourneyResult, index: int) -> str:
        """Render a single journey with tree structure."""
        status_class = "success" if result.success else "failure"
        status_icon = "&#10003;" if result.success else "&#10007;"
        duration = result.duration_ms / 1000

        # Build step tree
        step_tree = self._render_step_tree(result, index)

        # Build waterfall chart
        waterfall = self._render_waterfall(result)

        return f"""
        <div class="journey-item" id="journey-{index}"
             data-status="{status_class}"
             data-name="{html.escape(result.journey_name)}">
            <div class="journey-header" onclick="toggleJourney({index})">
                <div class="journey-status-icon {status_class}">{status_icon}</div>
                <div class="journey-info">
                    <div class="journey-title">{html.escape(result.journey_name)}</div>
                    <div class="journey-meta">
                        <span><strong>Duration:</strong> {duration:.2f}s</span>
                        <span><strong>Steps:</strong> {result.passed_steps}/{result.total_steps} passed</span>
                        {"<span><strong>Paths:</strong> " + str(result.passed_paths) + "/" + str(result.total_paths) + " passed</span>" if result.total_paths > 0 else ""}
                        <span class="badge {"badge-success" if result.success else "badge-danger"}">
                            {"PASSED" if result.success else "FAILED"}
                        </span>
                    </div>
                </div>
                <button class="journey-toggle" id="journey-toggle-{index}"
                        onclick="event.stopPropagation(); toggleJourney({index})">
                    Show Details
                </button>
            </div>
            <div class="journey-content" id="journey-content-{index}">
                {waterfall}
                {step_tree}
            </div>
        </div>"""

    def _render_step_tree(self, result: JourneyResult, journey_index: int) -> str:
        """Render the step tree structure."""
        if not result.step_results and not result.branch_results:
            return "<div class='step-tree'><p class='text-muted'>No steps executed</p></div>"

        nodes = []
        step_counter = 0

        # Render main steps
        for step in result.step_results:
            nodes.append(self._render_step_node(step, journey_index, step_counter))
            step_counter += 1

        # Render branches
        for branch in result.branch_results:
            nodes.append(self._render_branch_node(branch, journey_index, step_counter))
            step_counter += 1

        return f"""
        <div class="step-tree">
            <div class="tree-node">
                {"".join(nodes)}
            </div>
        </div>"""

    def _render_step_node(self, step: StepResult, journey_index: int, step_index: int) -> str:
        """Render a step node in the tree."""
        status_class = "success" if step.success else "failure"
        status_icon = "&#10003;" if step.success else "&#10007;"
        step_id = f"{journey_index}-{step_index}"

        # Build request/response viewer if available
        rr_viewer = self._render_request_response(step)

        error_html = ""
        if step.error:
            error_html = f"""
            <div class="mt-2">
                <strong class="text-danger">Error:</strong>
                <div class="code-block mt-1">{html.escape(step.error)}</div>
            </div>"""

        return f"""
        <div class="tree-item">
            <div class="tree-item-header" onclick="toggleStep('{step_id}')">
                <div class="step-icon {status_class}">{status_icon}</div>
                <span class="step-name">{html.escape(step.step_name)}</span>
                <span class="step-duration">{step.duration_ms:.0f}ms</span>
            </div>
            <div class="step-details" id="step-details-{step_id}">
                {rr_viewer}
                {error_html}
            </div>
        </div>"""

    def _render_branch_node(self, branch: BranchResult, journey_index: int, step_index: int) -> str:
        """Render a branch node with paths."""
        status_class = "success" if branch.all_passed else "failure"
        branch_id = f"{journey_index}-branch-{step_index}"

        path_nodes = []
        for path in branch.path_results:
            path_status = "success" if path.success else "failure"
            path_icon = "&#10003;" if path.success else "&#10007;"
            path_nodes.append(f"""
            <div class="tree-item">
                <div class="tree-item-header">
                    <div class="step-icon {path_status}">{path_icon}</div>
                    <span class="step-name">{html.escape(path.path_name)}</span>
                    <span class="step-duration">{len(path.step_results)} steps</span>
                </div>
            </div>""")

        return f"""
        <div class="tree-item">
            <div class="tree-item-header" onclick="toggleStep('{branch_id}')">
                <div class="step-icon branch">&#8618;</div>
                <span class="step-name">Branch: {html.escape(branch.checkpoint_name)}</span>
                <span class="step-duration">{branch.passed_paths}/{len(branch.path_results)} paths</span>
            </div>
            <div class="step-details" id="step-details-{branch_id}">
                <div class="tree-node">
                    {"".join(path_nodes)}
                </div>
            </div>
        </div>"""

    def _render_request_response(self, step: StepResult) -> str:
        """Render the request/response viewer for a step."""
        if not step.request and not step.response:
            return ""

        request_html = ""
        if step.request:
            method = step.request.get("method", "GET").upper()
            method_class = f"method-{method.lower()}"
            url = step.request.get("url", "")
            body = step.request.get("body", {})

            request_html = f"""
            <div class="rr-section">
                <div class="rr-header">
                    <span class="http-method {method_class}">{method}</span>
                    <span>{html.escape(str(url))}</span>
                </div>
                <div class="rr-content">
                    {self._format_code_block(body)}
                </div>
            </div>"""

        response_html = ""
        if step.response:
            status_code = step.response.get("status_code", 0)
            status_class = self._get_status_class(status_code)
            body = step.response.get("body", step.response)

            response_html = f"""
            <div class="rr-section">
                <div class="rr-header">
                    <span>Response</span>
                    <span class="status-code {status_class}">{status_code}</span>
                </div>
                <div class="rr-content">
                    {self._format_code_block(body)}
                </div>
            </div>"""

        return f"""
        <div class="request-response">
            {request_html}
            {response_html}
        </div>"""

    def _render_waterfall(self, result: JourneyResult) -> str:
        """Render the waterfall timing chart."""
        if not result.step_results:
            return ""

        total_duration = result.duration_ms
        if total_duration == 0:
            total_duration = 1

        rows = []
        for step in result.step_results:
            status_class = "success" if step.success else "failure"
            width_pct = (step.duration_ms / total_duration) * 100

            rows.append(f"""
            <div class="waterfall-row">
                <div class="waterfall-label" title="{html.escape(step.step_name)}">
                    {html.escape(step.step_name[:25])}
                </div>
                <div class="waterfall-bar-container">
                    <div class="waterfall-bar {status_class}" style="width: {width_pct}%"></div>
                </div>
                <div class="waterfall-value">{step.duration_ms:.0f}ms</div>
            </div>""")

        return f"""
        <div class="card-body" style="border-bottom: 1px solid var(--border);">
            <h4 class="mb-2">Timeline</h4>
            <div class="waterfall">
                {"".join(rows)}
            </div>
        </div>"""

    def _render_timing_analysis(self, results: list[JourneyResult]) -> str:
        """Render timing analysis section."""
        if not results:
            return ""

        # Calculate step timing stats
        step_stats: dict[str, list[float]] = {}
        for result in results:
            for step in result.step_results:
                if step.step_name not in step_stats:
                    step_stats[step.step_name] = []
                step_stats[step.step_name].append(step.duration_ms)

        if not step_stats:
            return ""

        # Get slowest steps
        avg_durations = {
            name: sum(durations) / len(durations)
            for name, durations in step_stats.items()
        }
        slowest = sorted(avg_durations.items(), key=lambda x: x[1], reverse=True)[:5]

        timing_cards = []
        for name, avg in slowest:
            durations = step_stats[name]
            timing_cards.append(f"""
            <div class="timing-card">
                <div class="timing-card-title">{html.escape(name[:30])}</div>
                <div class="timing-stats">
                    <div>
                        <div class="timing-stat-label">Avg</div>
                        <div class="timing-stat-value">{avg:.0f}ms</div>
                    </div>
                    <div>
                        <div class="timing-stat-label">Min</div>
                        <div class="timing-stat-value">{min(durations):.0f}ms</div>
                    </div>
                    <div>
                        <div class="timing-stat-label">Max</div>
                        <div class="timing-stat-value">{max(durations):.0f}ms</div>
                    </div>
                </div>
            </div>""")

        return f"""
        <div class="card">
            <div class="card-header">
                <span class="card-header-title">Slowest Steps</span>
            </div>
            <div class="card-body">
                <div class="timing-grid">
                    {"".join(timing_cards)}
                </div>
            </div>
        </div>"""

    def _render_issues(self, results: list[JourneyResult]) -> str:
        """Render the issues section."""
        all_issues = []
        for r in results:
            for issue in r.issues:
                all_issues.append((r.journey_name, issue))

        if not all_issues:
            return """
            <div class="card">
                <div class="card-header">
                    <span class="card-header-title">Issues</span>
                </div>
                <div class="card-body" style="text-align: center;">
                    <span class="text-success">&#10003; No issues found</span>
                </div>
            </div>"""

        issues_html = []
        for journey_name, issue in all_issues:
            severity_class = f"issue-{issue.severity.value}"
            badge_class = f"badge-{issue.severity.value}"

            suggestion_html = ""
            if issue.suggestion:
                suggestion_html = f"""
                <div class="issue-suggestion mt-2">
                    <strong>Suggestion:</strong> {html.escape(issue.suggestion)}
                </div>"""

            issues_html.append(f"""
            <div class="issue-card {severity_class}" data-severity="{issue.severity.value}">
                <div class="issue-header">
                    <div class="issue-location">
                        {html.escape(issue.journey)} / {html.escape(issue.step)}
                    </div>
                    <span class="badge {badge_class}">{issue.severity.value.upper()}</span>
                </div>
                <div class="issue-message">{html.escape(issue.error)}</div>
                {suggestion_html}
            </div>""")

        return f"""
        <div class="card">
            <div class="card-header">
                <span class="card-header-title">Issues ({len(all_issues)})</span>
                <div class="filter-bar issue-filter">
                    <button class="filter-btn active" onclick="filterIssues('all')">All</button>
                    <button class="filter-btn" onclick="filterIssues('critical')">Critical</button>
                    <button class="filter-btn" onclick="filterIssues('high')">High</button>
                    <button class="filter-btn" onclick="filterIssues('medium')">Medium</button>
                    <button class="filter-btn" onclick="filterIssues('low')">Low</button>
                </div>
            </div>
            <div class="card-body">
                {"".join(issues_html)}
            </div>
        </div>"""

    def _format_code_block(self, content: Any) -> str:
        """Format content as a syntax-highlighted code block."""
        if isinstance(content, (dict, list)):
            try:
                formatted = json.dumps(content, indent=2)
                highlighted = self._highlight_json(formatted)
                return f'<div class="code-block">{highlighted}</div>'
            except (TypeError, ValueError):
                pass

        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                formatted = json.dumps(parsed, indent=2)
                highlighted = self._highlight_json(formatted)
                return f'<div class="code-block">{highlighted}</div>'
            except (json.JSONDecodeError, TypeError):
                pass

        return f'<div class="code-block">{html.escape(str(content))}</div>'

    def _highlight_json(self, json_str: str) -> str:
        """Apply syntax highlighting to JSON string."""
        import re

        result = html.escape(json_str)

        # Highlight keys
        result = re.sub(
            r'"([^"]*)"(\s*:)',
            r'<span class="json-key">"\1"</span>\2',
            result
        )

        # Highlight string values
        result = re.sub(
            r':\s*"([^"]*)"',
            r': <span class="json-string">"\1"</span>',
            result
        )

        # Highlight numbers
        result = re.sub(
            r':\s*(-?\d+\.?\d*)',
            r': <span class="json-number">\1</span>',
            result
        )

        # Highlight booleans
        result = re.sub(
            r'\b(true|false)\b',
            r'<span class="json-boolean">\1</span>',
            result
        )

        # Highlight null
        result = re.sub(
            r'\bnull\b',
            r'<span class="json-null">null</span>',
            result
        )

        return result

    def _get_status_class(self, status_code: int) -> str:
        """Get CSS class for HTTP status code."""
        if 200 <= status_code < 300:
            return "status-2xx"
        elif 300 <= status_code < 400:
            return "status-3xx"
        elif 400 <= status_code < 500:
            return "status-4xx"
        elif 500 <= status_code < 600:
            return "status-5xx"
        return ""
