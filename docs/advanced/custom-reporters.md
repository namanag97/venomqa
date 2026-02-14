# Custom Reporters

Create custom reporters to output test results in any format.

## Creating a Custom Reporter

Extend `BaseReporter` and implement the required methods:

```python
from pathlib import Path
from venomqa.reporters.base import BaseReporter
from venomqa.core.models import JourneyResult


class CSVReporter(BaseReporter):
    """Generate CSV reports for spreadsheet analysis."""

    @property
    def file_extension(self) -> str:
        return ".csv"

    def generate(self, results: list[JourneyResult]) -> str:
        lines = [
            "journey_name,success,duration_ms,total_steps,passed_steps,issues"
        ]

        for result in results:
            lines.append(
                f"{result.journey_name},"
                f"{result.success},"
                f"{result.duration_ms:.0f},"
                f"{result.total_steps},"
                f"{result.passed_steps},"
                f"{len(result.issues)}"
            )

        return "\n".join(lines)


# Usage
reporter = CSVReporter(output_path="reports/results.csv")
reporter.save([journey_result])
```

## BaseReporter Interface

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseReporter(ABC):
    """Base class for all reporters."""

    def __init__(self, output_path: str | Path | None = None):
        self.output_path = Path(output_path) if output_path else None

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension (e.g., '.csv')."""
        ...

    @abstractmethod
    def generate(self, results: list[JourneyResult]) -> str | dict | bytes:
        """Generate report content from results."""
        ...

    def save(self, results: list[JourneyResult], path: Path | None = None) -> Path:
        """Save report to file."""
        output_path = path or self.output_path
        if output_path is None:
            output_path = Path(f"report{self.file_extension}")

        content = self.generate(results)

        if isinstance(content, bytes):
            output_path.write_bytes(content)
        elif isinstance(content, dict):
            import json
            output_path.write_text(json.dumps(content, indent=2))
        else:
            output_path.write_text(content)

        return output_path
```

## Example: Slack Reporter

```python
import httpx
from venomqa.reporters.base import BaseReporter
from venomqa.core.models import JourneyResult


class SlackReporter(BaseReporter):
    """Send test results to Slack."""

    def __init__(
        self,
        webhook_url: str,
        channel: str | None = None,
        mention_on_failure: str | None = None,
        output_path: str | None = None,
    ):
        super().__init__(output_path)
        self.webhook_url = webhook_url
        self.channel = channel
        self.mention_on_failure = mention_on_failure

    @property
    def file_extension(self) -> str:
        return ".json"

    def generate(self, results: list[JourneyResult]) -> dict:
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        total_duration = sum(r.duration_ms for r in results) / 1000

        color = "good" if failed == 0 else "danger"
        status = "All tests passed!" if failed == 0 else f"{failed} test(s) failed"

        mention = ""
        if failed > 0 and self.mention_on_failure:
            mention = f"{self.mention_on_failure} "

        return {
            "channel": self.channel,
            "attachments": [{
                "color": color,
                "title": "VenomQA Test Results",
                "text": f"{mention}{status}",
                "fields": [
                    {"title": "Passed", "value": str(passed), "short": True},
                    {"title": "Failed", "value": str(failed), "short": True},
                    {"title": "Duration", "value": f"{total_duration:.1f}s", "short": True},
                ],
                "footer": "VenomQA",
            }]
        }

    def send(self, results: list[JourneyResult]) -> None:
        """Send results to Slack."""
        payload = self.generate(results)
        httpx.post(self.webhook_url, json=payload)


# Usage
reporter = SlackReporter(
    webhook_url="https://hooks.slack.com/services/...",
    channel="#qa-results",
    mention_on_failure="@channel",
)
reporter.send([journey_result])
```

## Example: HTML Dashboard Reporter

```python
from venomqa.reporters.base import BaseReporter
from venomqa.core.models import JourneyResult


class HTMLDashboardReporter(BaseReporter):
    """Generate interactive HTML dashboard."""

    def __init__(self, output_path: str | None = None, title: str = "QA Dashboard"):
        super().__init__(output_path)
        self.title = title

    @property
    def file_extension(self) -> str:
        return ".html"

    def generate(self, results: list[JourneyResult]) -> str:
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        total_duration = sum(r.duration_ms for r in results)

        rows = "\n".join(
            f"""<tr class="{'passed' if r.success else 'failed'}">
                <td>{r.journey_name}</td>
                <td>{'PASS' if r.success else 'FAIL'}</td>
                <td>{r.duration_ms:.0f}ms</td>
                <td>{r.passed_steps}/{r.total_steps}</td>
                <td>{len(r.issues)}</td>
            </tr>"""
            for r in results
        )

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{self.title}</title>
    <style>
        body {{ font-family: system-ui; margin: 40px; }}
        .summary {{ display: flex; gap: 20px; margin-bottom: 30px; }}
        .metric {{ text-align: center; padding: 20px; background: #f5f5f5; border-radius: 8px; }}
        .metric-value {{ font-size: 2em; font-weight: bold; }}
        .passed {{ color: #22c55e; }}
        .failed {{ color: #ef4444; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        tr.passed td:nth-child(2) {{ color: #22c55e; }}
        tr.failed td:nth-child(2) {{ color: #ef4444; }}
    </style>
</head>
<body>
    <h1>{self.title}</h1>

    <div class="summary">
        <div class="metric">
            <div class="metric-value passed">{passed}</div>
            <div>Passed</div>
        </div>
        <div class="metric">
            <div class="metric-value failed">{failed}</div>
            <div>Failed</div>
        </div>
        <div class="metric">
            <div class="metric-value">{total_duration/1000:.1f}s</div>
            <div>Duration</div>
        </div>
    </div>

    <table>
        <tr>
            <th>Journey</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Steps</th>
            <th>Issues</th>
        </tr>
        {rows}
    </table>
</body>
</html>"""
```

## Example: XML Reporter

```python
import xml.etree.ElementTree as ET
from venomqa.reporters.base import BaseReporter


class XMLReporter(BaseReporter):
    """Generate XML reports."""

    @property
    def file_extension(self) -> str:
        return ".xml"

    def generate(self, results: list[JourneyResult]) -> str:
        root = ET.Element("testResults")
        root.set("total", str(len(results)))
        root.set("passed", str(sum(1 for r in results if r.success)))

        for result in results:
            journey = ET.SubElement(root, "journey")
            journey.set("name", result.journey_name)
            journey.set("success", str(result.success).lower())
            journey.set("duration", str(result.duration_ms))

            for step_result in result.step_results:
                step = ET.SubElement(journey, "step")
                step.set("name", step_result.step_name)
                step.set("success", str(step_result.success).lower())

        return ET.tostring(root, encoding="unicode")
```

## Registering Custom Reporters

### Using Decorator

```python
from venomqa.reporters import register_reporter

@register_reporter("csv")
class CSVReporter(BaseReporter):
    ...
```

### Using Function

```python
from venomqa.reporters import register_reporter_class

register_reporter_class("csv", CSVReporter)
```

### Using Entry Points

Add to `pyproject.toml`:

```toml
[project.entry-points."venomqa.reporters"]
csv = "my_package.reporters:CSVReporter"
slack = "my_package.reporters:SlackReporter"
```

## Using Custom Reporters

### CLI

After registering:

```bash
venomqa report --format csv --output results.csv
```

### Programmatic

```python
from my_reporters import CSVReporter, SlackReporter

# Generate CSV
csv_reporter = CSVReporter(output_path="results.csv")
csv_reporter.save(results)

# Send to Slack
slack_reporter = SlackReporter(webhook_url="...")
slack_reporter.send(results)
```

## Best Practices

### 1. Handle Missing Data

```python
def generate(self, results):
    for result in results:
        name = result.journey_name or "unknown"
        duration = result.duration_ms or 0
        # ...
```

### 2. Include Timestamps

```python
from datetime import datetime

def generate(self, results):
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "results": [...]
    }
```

### 3. Support Filtering

```python
class FilterableReporter(BaseReporter):
    def __init__(self, output_path=None, include_passed=True, include_failed=True):
        super().__init__(output_path)
        self.include_passed = include_passed
        self.include_failed = include_failed

    def generate(self, results):
        filtered = [
            r for r in results
            if (r.success and self.include_passed) or
               (not r.success and self.include_failed)
        ]
        # Generate from filtered results
```

### 4. Add Configuration Options

```python
class ConfigurableReporter(BaseReporter):
    def __init__(
        self,
        output_path=None,
        include_request_details=False,
        include_timing=True,
        verbose=False,
    ):
        super().__init__(output_path)
        self.include_request_details = include_request_details
        self.include_timing = include_timing
        self.verbose = verbose
```
