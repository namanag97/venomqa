# Custom Reporters

Create custom output formats for Slack, Discord, or your own dashboards.

## Overview

Reporters receive the `ExplorationResult` after exploration completes and format it for output. VenomQA includes several built-in reporters, and you can create your own.

## Built-in Reporters

| Reporter | Output | Use Case |
|----------|--------|----------|
| `ConsoleReporter` | Terminal | Local development |
| `JSONReporter` | JSON file | CI/CD, programmatic access |
| `HTMLTraceReporter` | HTML with D3 graph | Visual debugging |
| `JUnitReporter` | JUnit XML | CI/CD integration |
| `MarkdownReporter` | Markdown | Documentation |

## Reporter Protocol

A reporter is any callable that accepts an `ExplorationResult`:

```python
from venomqa import ExplorationResult

def my_reporter(result: ExplorationResult) -> str:
    """Format exploration result as string."""
    return f"Found {len(result.violations)} violations"
```

For more complex reporters, use a class:

```python
from venomqa import ExplorationResult

class MyReporter:
    def __init__(self, output_file: str = "report.txt"):
        self.output_file = output_file
    
    def __call__(self, result: ExplorationResult) -> str:
        output = self._format(result)
        with open(self.output_file, "w") as f:
            f.write(output)
        return output
    
    def _format(self, result: ExplorationResult) -> str:
        lines = [
            f"States: {result.states_visited}",
            f"Violations: {len(result.violations)}",
        ]
        for v in result.violations:
            lines.append(f"  - {v.invariant_name}: {v.message}")
        return "\n".join(lines)
```

## Using Custom Reporters

Pass your reporter to `explore()`:

```python
from venomqa import Agent, World, Action, Invariant, Severity
from myapp.reporters import MyReporter

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
)

result = agent.explore()

reporter = MyReporter("report.txt")
reporter(result)
```

Or use multiple reporters:

```python
reporters = [
    ConsoleReporter(),
    JSONReporter("results.json"),
    MyReporter("custom.txt"),
]

for reporter in reporters:
    reporter(result)
```

## Example: Slack Reporter

Send violations to a Slack channel:

```python
import json
import urllib.request
from venomqa import ExplorationResult

class SlackReporter:
    """Post exploration results to Slack."""
    
    def __init__(
        self,
        webhook_url: str,
        channel: str = "#qa-alerts",
        only_violations: bool = True,
    ):
        self.webhook_url = webhook_url
        self.channel = channel
        self.only_violations = only_violations
    
    def __call__(self, result: ExplorationResult) -> str:
        if self.only_violations and result.success:
            return "Skipped (no violations)"
        
        payload = self._build_payload(result)
        self._send(payload)
        return f"Posted to {self.channel}"
    
    def _build_payload(self, result: ExplorationResult) -> dict:
        if result.success:
            return {
                "channel": self.channel,
                "attachments": [{
                    "color": "good",
                    "title": "VenomQA: All Invariants Passed",
                    "fields": [
                        {"title": "States Visited", "value": str(result.states_visited), "short": True},
                        {"title": "Duration", "value": f"{result.duration_ms}ms", "short": True},
                    ],
                }],
            }
        
        critical = len(result.critical_violations)
        high = len(result.high_violations)
        
        fields = [
            {"title": "Critical", "value": str(critical), "short": True},
            {"title": "High", "value": str(high), "short": True},
            {"title": "States", "value": str(result.states_visited), "short": True},
            {"title": "Duration", "value": f"{result.duration_ms}ms", "short": True},
        ]
        
        violations_text = []
        for v in result.violations[:5]:
            path = " → ".join(t.action_name for t in v.reproduction_path)
            violations_text.append(f"• *{v.invariant_name}*: {v.message}")
            violations_text.append(f"  Path: `{path}`")
        
        return {
            "channel": self.channel,
            "attachments": [{
                "color": "danger",
                "title": f"VenomQA: {len(result.violations)} Violations Found",
                "fields": fields,
                "text": "\n".join(violations_text),
                "mrkdwn_in": ["text"],
            }],
        }
    
    def _send(self, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)
```

Usage:

```python
reporter = SlackReporter(
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    channel="#qa-alerts",
)
reporter(result)
```

## Example: Discord Reporter

Send results to a Discord channel via webhook:

```python
import json
import urllib.request
from venomqa import ExplorationResult

class DiscordReporter:
    """Post exploration results to Discord."""
    
    def __init__(
        self,
        webhook_url: str,
        only_violations: bool = True,
    ):
        self.webhook_url = webhook_url
        self.only_violations = only_violations
    
    def __call__(self, result: ExplorationResult) -> str:
        if self.only_violations and result.success:
            return "Skipped (no violations)"
        
        payload = self._build_payload(result)
        self._send(payload)
        return "Posted to Discord"
    
    def _build_payload(self, result: ExplorationResult) -> dict:
        color = 5763719 if result.success else 15548997
        
        fields = [
            {"name": "States Visited", "value": str(result.states_visited), "inline": True},
            {"name": "Transitions", "value": str(result.transitions_taken), "inline": True},
            {"name": "Coverage", "value": f"{result.action_coverage_percent:.0f}%", "inline": True},
            {"name": "Duration", "value": f"{result.duration_ms}ms", "inline": True},
        ]
        
        if not result.success:
            fields.append({
                "name": f"Violations ({len(result.violations)})",
                "value": self._format_violations(result.violations[:5]),
                "inline": False,
            })
        
        return {
            "embeds": [{
                "title": "VenomQA Exploration Results",
                "color": color,
                "fields": fields,
                "footer": {"text": "VenomQA"},
            }],
        }
    
    def _format_violations(self, violations) -> str:
        lines = []
        for v in violations:
            severity = v.severity.value.upper()
            lines.append(f"**[{severity}]** {v.invariant_name}")
            if v.message:
                lines.append(f"> {v.message[:100]}")
        return "\n".join(lines) or "None"
    
    def _send(self, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)
```

## Example: Custom JSON Format

Generate a custom JSON structure:

```python
import json
from datetime import datetime
from venomqa import ExplorationResult

class CustomJSONReporter:
    """Export results in a custom JSON schema."""
    
    def __init__(self, output_path: str, include_traces: bool = True):
        self.output_path = output_path
        self.include_traces = include_traces
    
    def __call__(self, result: ExplorationResult) -> str:
        data = {
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "duration_ms": result.duration_ms,
                "success": result.success,
            },
            "statistics": {
                "states_visited": result.states_visited,
                "transitions_taken": result.transitions_taken,
                "action_coverage_percent": result.action_coverage_percent,
                "truncated": result.truncated_by_max_steps,
            },
            "violations": [
                self._format_violation(v)
                for v in result.violations
            ],
        }
        
        if self.include_traces:
            data["trace"] = self._extract_trace(result)
        
        with open(self.output_path, "w") as f:
            json.dump(data, f, indent=2)
        
        return f"Wrote {self.output_path}"
    
    def _format_violation(self, violation) -> dict:
        return {
            "id": violation.id,
            "invariant": violation.invariant_name,
            "severity": violation.severity.value,
            "message": violation.message,
            "path": [t.action_name for t in violation.reproduction_path],
            "action": violation.action.name if violation.action else None,
            "request": self._format_request(violation.action_result),
            "response": self._format_response(violation.action_result),
        }
    
    def _format_request(self, action_result) -> dict | None:
        if not action_result:
            return None
        req = action_result.request
        return {
            "method": req.method,
            "url": req.url,
        }
    
    def _format_response(self, action_result) -> dict | None:
        if not action_result or not action_result.response:
            return None
        resp = action_result.response
        return {
            "status_code": resp.status_code,
            "ok": resp.ok,
        }
    
    def _extract_trace(self, result: ExplorationResult) -> list[dict]:
        trace = []
        for transition in result.graph.iter_transitions():
            trace.append({
                "from_state": transition.from_state_id[:8],
                "action": transition.action_name,
                "to_state": transition.to_state_id[:8],
            })
        return trace
```

## Example: Prometheus Metrics

Export metrics for monitoring:

```python
from venomqa import ExplorationResult

class PrometheusMetricsReporter:
    """Export Prometheus-compatible metrics."""
    
    def __init__(self, output_path: str = "metrics.prom"):
        self.output_path = output_path
    
    def __call__(self, result: ExplorationResult) -> str:
        metrics = [
            f"venomqa_states_visited {result.states_visited}",
            f"venomqa_transitions_taken {result.transitions_taken}",
            f"venomqa_action_coverage_percent {result.action_coverage_percent}",
            f"venomqa_duration_ms {result.duration_ms}",
            f"venomqa_violations_total {len(result.violations)}",
            f"venomqa_violations_critical {len(result.critical_violations)}",
            f"venomqa_violations_high {len(result.high_violations)}",
            f"venomqa_success {1 if result.success else 0}",
        ]
        
        output = "\n".join(metrics) + "\n"
        
        with open(self.output_path, "w") as f:
            f.write(output)
        
        return f"Wrote {self.output_path}"
```

## Accessing Result Data

The `ExplorationResult` provides:

```python
result.success              # bool - all invariants passed
result.states_visited       # int - unique states explored
result.transitions_taken    # int - total transitions
result.violations           # list[Violation] - all violations
result.critical_violations  # list[Violation] - CRITICAL severity
result.high_violations      # list[Violation] - HIGH severity
result.duration_ms          # float - exploration time
result.graph                # Graph - full state graph
result.truncated_by_max_steps  # bool - hit step limit

# Violation properties
violation.invariant_name    # str - which invariant failed
violation.severity          # Severity - CRITICAL/HIGH/MEDIUM/LOW
violation.message           # str - description
violation.reproduction_path # list[Transition] - how to reproduce
violation.action            # Action | None - triggering action
violation.action_result     # ActionResult | None - HTTP details
```

## Best Practices

1. **Fail gracefully** - Network issues shouldn't crash your tests
2. **Rate limit** - Don't spam channels on large violation counts
3. **Include context** - Path, severity, and message help debugging
4. **Filter noise** - Only post what's actionable
5. **Test locally** - Verify reporter output before CI

```python
class RobustSlackReporter:
    def __call__(self, result: ExplorationResult) -> str:
        try:
            if result.success:
                return "Skipped (success)"
            return self._send_report(result)
        except Exception as e:
            return f"Failed to send: {e}"
```
