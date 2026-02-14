# VenomQA CLI Output Features

VenomQA includes professional, live progress indicators and beautiful visualizations for your test journeys using the Rich library.

## Features

### 1. Live Progress Bar

Real-time progress tracking with:
- **Spinner animation** - Shows activity while tests are running
- **Progress bar** - Visual representation: `[=====>    ] 50%`
- **Step counter** - Current and total steps: `5/10`
- **Elapsed time** - How long the journey has been running
- **Estimated time remaining (ETA)** - Predicted completion time

Example output:
```
⠋ → Step 5/10: process_payment ━━━━━━━━━━━━━━━━━━━━━━━ 5/10 • 0:00:02 • 0:00:02
```

### 2. Current Step Indicator

Each step is displayed with:
- **Spinner** - Animated spinner (⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
- **Step number** - Current position in journey
- **Step name** - Descriptive name of the action
- **Status updates** - Updates in real-time without spamming the terminal

### 3. Timing Information

Comprehensive timing data:
- **Per-step duration** - Time taken for each step (shown after completion)
- **Elapsed time** - Total time since journey started
- **ETA calculation** - Smart prediction based on average step time
- **Summary timing** - Complete breakdown in the final summary

Example:
```
Step Timings:
  login            270ms
  browse_products  290ms
  add_to_cart      310ms
  ...
```

### 4. Branch Visualization

Tree-like visualization for branches and paths:

```
├─ Branch: before_payment (3 paths)
  │ ├─ Path: credit_card_payment
  │ └─ ✓ credit_card_payment (3 steps)
  │ ├─ Path: paypal_payment
  │ └─ ✓ paypal_payment (2 steps)
  │ ├─ Path: crypto_payment
  │ └─ ✗ crypto_payment (2 steps)
```

Features:
- **Tree characters** - Visual hierarchy (├─, └─, │)
- **Branch indicators** - Shows checkpoint name and path count
- **Path status** - Success (✓) or failure (✗) with step counts
- **Color coding** - Green for success, red for failure

### 5. Checkpoint & Rollback Indicators

Visual markers for state management:

```
◉ Checkpoint: before_payment
↩ Rollback to: before_payment
```

- **Checkpoints** - Shown in yellow with ◉ symbol
- **Rollbacks** - Shown in cyan with ↩ symbol
- **Integration** - Seamlessly displayed during live progress

### 6. Summary Panel

Beautiful summary boxes at journey completion:

```
╭──────────────────────── JOURNEY COMPLETE: checkout_flow ───────────────────────╮
│                                                                                │
│  Status:            ✓ PASSED                                                   │
│  Duration:          3.50s                                                      │
│  Steps:             10/10 passed                                               │
│  Paths:             3/3 passed                                                 │
│                                                                                │
│  Step Timings:                                                                 │
│    login            270ms                                                      │
│    browse_products  290ms                                                      │
│    add_to_cart      310ms                                                      │
│    ...                                                                         │
│                                                                                │
╰────────────────────────────────────────────────────────────────────────────────╯
```

Includes:
- **Status indicator** - Pass/fail with colored symbols
- **Duration** - Total execution time
- **Step statistics** - Passed vs total steps
- **Path statistics** - Passed vs total paths (if applicable)
- **Timing breakdown** - Top 10 slowest steps
- **Border styling** - Green for success, red for failure

### 7. Overall Summary

Multi-journey summary with aggregate statistics:

```
╭────────────────────── ✓ SUMMARY: ALL JOURNEYS PASSED ──────────────────────────╮
│                                                                                │
│  Total:     5                                                                  │
│  Passed:    5                                                                  │
│  Failed:    0                                                                  │
│  Duration:  15.00s                                                             │
│                                                                                │
╰────────────────────────────────────────────────────────────────────────────────╯
```

### 8. Issue Reporting

Failed steps are clearly highlighted:

```
✗ Issues:
  ✗ apply_discount: Discount code expired
  ✗ payment_gateway: Connection timeout
```

## Configuration

Control output features via `ProgressConfig`:

```python
from venomqa.cli.output import CLIOutput, ProgressConfig

config = ProgressConfig(
    show_progress=True,      # Enable progress bars
    show_checkpoints=True,   # Show checkpoint markers
    show_paths=True,         # Show branch paths
    show_timing=True,        # Show timing information
    use_colors=True,         # Enable colored output
    use_unicode=True,        # Use Unicode symbols (vs ASCII)
)

output = CLIOutput(config)
```

## Terminal Compatibility

### Unicode Support

The CLI automatically detects terminal capabilities:

**Unicode terminals** (default):
- Beautiful symbols: ✓ ✗ ⚙ ◉ ↩ → ├─ └─ │
- Smooth spinners: ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧

**ASCII-only terminals**:
- ASCII fallbacks: [OK] [FAIL] [*] <- -> |-- `-- |
- Text-based indicators

### Color Support

- **Color terminals**: Rich colors with ANSI codes
- **No-color terminals**: Plain text output
- **Auto-detection**: Automatically detects TTY capabilities

## Usage Examples

### Basic Journey

```python
from venomqa import Journey, Step
from venomqa.cli.output import CLIOutput, ProgressConfig

output = CLIOutput()

# Start journey
output.journey_start(
    name="user_registration",
    description="Complete user registration flow",
    total_steps=5
)

# Run steps (integrated with runner)
# Output automatically updates during execution

# Show summary
output.journey_summary(
    name="user_registration",
    success=True,
    step_count=5,
    passed_steps=5,
    duration_ms=1200
)
```

### With Branches

```python
# Branch starts automatically
output.branch_start("after_signup", 3)

# Paths run automatically
output.path_start("email_verification")
output.path_result("email_verification", True, 3)

output.path_start("phone_verification")
output.path_result("phone_verification", True, 2)
```

## Integration

The CLI output is automatically integrated with:
- **JourneyRunner** - Automatic progress updates during execution
- **Commands** - Built into `venomqa run` command
- **Reporters** - Works alongside all reporter formats

## Performance

- **Non-blocking** - Progress updates don't slow down tests
- **Efficient rendering** - Updates at 10 FPS (configurable)
- **Memory conscious** - Minimal overhead
- **Live updates** - In-place rendering without terminal spam

## Best Practices

1. **Always provide total_steps** for accurate progress bars
2. **Use descriptive step names** for clarity
3. **Enable timing** to identify slow steps
4. **Color support** improves readability in CI logs
5. **Unicode symbols** provide better visual hierarchy

## Troubleshooting

### Progress bar not showing
- Ensure `total_steps > 0` in `journey_start()`
- Check `show_progress=True` in config

### Symbols displaying incorrectly
- Terminal may not support Unicode
- Set `use_unicode=False` for ASCII fallback

### Colors not working
- Verify terminal supports ANSI colors
- Check TTY detection with `output._supports_color()`

## Future Enhancements

Planned features:
- Real-time request/response preview
- Interactive mode for step debugging
- Performance graphs and charts
- Export progress to file/stream
- WebSocket streaming for remote monitoring

## See Also

- [CLI Commands](cli.md) - Command-line interface
- [Journeys](journeys.md) - Journey structure
- [Reporters](../README.md#reporters) - Report formats
