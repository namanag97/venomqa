# Reporters Reference

VenomQA supports multiple report formats for different use cases.

## Available Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| `markdown` | `.md` | Human-readable reports |
| `json` | `.json` | Programmatic processing |
| `junit` | `.xml` | CI/CD integration |
| `html` | `.html` | Standalone web reports |
| `sarif` | `.sarif` | Security tools integration |
| `slack` | - | Slack notifications |
| `discord` | - | Discord notifications |

## Using Reporters

### CLI

```bash
# Generate single format
venomqa report --format markdown --output reports/test.md

# Generate multiple formats
venomqa report --format junit --output reports/junit.xml
venomqa report --format html --output reports/test.html
```

### Configuration

```yaml
# venomqa.yaml
report_dir: "reports"
report_formats:
  - markdown
  - junit
  - html
```

### Programmatic

```python
from venomqa.reporters import (
    MarkdownReporter,
    JSONReporter,
    JUnitReporter,
    HTMLReporter,
)

# Generate markdown
reporter = MarkdownReporter(output_path="reports/test.md")
reporter.save([journey_result])

# Generate JSON
reporter = JSONReporter(output_path="reports/test.json", indent=2)
reporter.save([journey_result])

# Generate JUnit XML
reporter = JUnitReporter(output_path="reports/junit.xml")
reporter.save([journey_result])

# Generate HTML
reporter = HTMLReporter(output_path="reports/test.html")
reporter.save([journey_result])
```

## Format Details

### Markdown Reporter

Human-readable Markdown format.

```python
from venomqa.reporters import MarkdownReporter

reporter = MarkdownReporter(
    output_path="reports/test.md",
    include_request_details=True,   # Include request/response
    include_timing=True,            # Include timing info
)
```

**Example output:**

```markdown
# VenomQA Test Report

**Generated:** 2024-01-15 10:30:00
**Total Journeys:** 2
**Passed:** 2
**Failed:** 0

## Journey: checkout_flow

**Status:** PASSED
**Duration:** 1.23s

### Steps

| Step | Status | Duration |
|------|--------|----------|
| login | PASS | 89ms |
| add_to_cart | PASS | 45ms |
| checkout | PASS | 67ms |

### Branches

#### Branch: order_ready

| Path | Status | Steps |
|------|--------|-------|
| credit_card | PASS | 2/2 |
| wallet | PASS | 2/2 |
```

### JSON Reporter

Structured JSON for programmatic processing.

```python
from venomqa.reporters import JSONReporter

reporter = JSONReporter(
    output_path="reports/test.json",
    indent=2,                       # Pretty print
    include_request_details=True,   # Include full request/response
)
```

**Example output:**

```json
{
  "generated_at": "2024-01-15T10:30:00Z",
  "summary": {
    "total_journeys": 2,
    "passed": 2,
    "failed": 0,
    "total_duration_ms": 2456
  },
  "journeys": [
    {
      "name": "checkout_flow",
      "success": true,
      "duration_ms": 1234,
      "steps": [
        {
          "name": "login",
          "success": true,
          "duration_ms": 89
        }
      ],
      "branches": [...]
    }
  ]
}
```

### JUnit Reporter

JUnit XML format for CI/CD integration.

```python
from venomqa.reporters import JUnitReporter

reporter = JUnitReporter(
    output_path="reports/junit.xml",
    suite_name="VenomQA Tests",     # Test suite name
)
```

**Example output:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="VenomQA Tests" tests="6" failures="0" time="1.234">
  <testsuite name="checkout_flow" tests="6" failures="0" time="1.234">
    <testcase name="login" classname="checkout_flow" time="0.089"/>
    <testcase name="add_to_cart" classname="checkout_flow" time="0.045"/>
    <testcase name="checkout" classname="checkout_flow" time="0.067"/>
    <testcase name="credit_card.pay_card" classname="checkout_flow" time="0.156"/>
    <testcase name="credit_card.verify" classname="checkout_flow" time="0.023"/>
  </testsuite>
</testsuites>
```

### HTML Reporter

Standalone HTML report with styling.

```python
from venomqa.reporters import HTMLReporter

reporter = HTMLReporter(
    output_path="reports/test.html",
    title="QA Test Results",        # Page title
    include_charts=True,            # Include charts
)
```

### SARIF Reporter

SARIF format for security tools.

```python
from venomqa.reporters import SARIFReporter

reporter = SARIFReporter(
    output_path="reports/test.sarif",
    tool_name="VenomQA",
    tool_version="0.2.0",
)
```

### Slack Reporter

Send results to Slack.

```python
from venomqa.reporters import SlackReporter

reporter = SlackReporter(
    webhook_url="https://hooks.slack.com/services/...",
    channel="#qa-results",          # Optional channel override
    mention_on_failure="@channel",  # Mention on failures
)

reporter.send([journey_result])
```

### Discord Reporter

Send results to Discord.

```python
from venomqa.reporters import DiscordReporter

reporter = DiscordReporter(
    webhook_url="https://discord.com/api/webhooks/...",
    mention_on_failure="@here",
)

reporter.send([journey_result])
```

## Custom Reporters

Create custom reporters by extending `BaseReporter`:

```python
from pathlib import Path
from typing import Any
from venomqa.reporters.base import BaseReporter
from venomqa.core.models import JourneyResult


class CSVReporter(BaseReporter):
    """Generate CSV reports for spreadsheet analysis."""

    @property
    def file_extension(self) -> str:
        return ".csv"

    def generate(self, results: list[JourneyResult]) -> str:
        lines = [
            "journey_name,success,duration_ms,total_steps,passed_steps,issue_count"
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

### BaseReporter Interface

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
        """Return the file extension for this reporter."""
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

## Reporter Registration

Register custom reporters:

```python
from venomqa.reporters import register_reporter

@register_reporter("csv")
class CSVReporter(BaseReporter):
    ...

# Or register directly
from venomqa.reporters import register_reporter_class
register_reporter_class("csv", CSVReporter)
```

Add to `pyproject.toml` for plugin discovery:

```toml
[project.entry-points."venomqa.reporters"]
csv = "my_package.reporters:CSVReporter"
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Generate JUnit report
  if: always()
  run: venomqa report --format junit --output reports/junit.xml

- name: Publish test results
  if: always()
  uses: dorny/test-reporter@v1
  with:
    name: QA Tests
    path: reports/junit.xml
    reporter: java-junit
```

### GitLab CI

```yaml
qa-tests:
  artifacts:
    reports:
      junit: reports/junit.xml
```

### Jenkins

```groovy
post {
    always {
        junit 'reports/junit.xml'
    }
}
```

## Best Practices

### 1. Generate Multiple Formats

```yaml
report_formats:
  - junit      # For CI/CD
  - html       # For humans
  - json       # For processing
```

### 2. Use JUnit for CI/CD

JUnit XML is universally supported:

```bash
venomqa report --format junit --output reports/junit.xml
```

### 3. Include Request Details for Debugging

```python
reporter = MarkdownReporter(
    output_path="reports/debug.md",
    include_request_details=True,
)
```

### 4. Send Notifications on Failure

```python
if not all(r.success for r in results):
    slack_reporter.send(results)
```
