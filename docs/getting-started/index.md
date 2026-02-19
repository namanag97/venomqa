# Getting Started

VenomQA tests what other tools miss: the bugs that appear in **sequences** of API calls, not individual endpoints.

## The 30-Second Pitch

Your API has state. A user creates an order, requests a refund, then requests another refund. Each call looks valid in isolation. The bug only appears in the sequence.

**VenomQA explores every sequence automatically.**

```
pytest         → Tests functions in isolation
Schemathesis   → Fuzzes individual endpoints  
VenomQA        → Explores all call sequences
```

## Quick Navigation

| If you want to... | Go to |
|-------------------|-------|
| See it work in 30 seconds | [Quickstart](quickstart.md) |
| Install and configure | [Installation](installation.md) |
| Tune settings for your app | [Configuration](configuration.md) |

## What You'll Need

- **Python 3.10+**
- **An API to test** (local or remote)
- **Optional**: PostgreSQL, MySQL, or SQLite for database rollback

## Installation

```bash
pip install venomqa
```

## Verify Installation

```bash
venomqa --version
venomqa doctor
```

The `doctor` command checks your environment and reports any issues.

## Next Steps

<div class="grid cards" markdown>

-   :material-play:{ .lg .middle } __Quickstart__

    ---

    Run `venomqa demo` and find your first bug in 30 seconds.

    [:octicons-arrow-right-24: Get started](quickstart.md)

-   :material-download:{ .lg .middle } __Installation__

    ---

    Full installation guide including database adapters.

    [:octicons-arrow-right-24: Install](installation.md)

-   :material-cog:{ .lg .middle } __Configuration__

    ---

    Authentication, timeouts, and environment setup.

    [:octicons-arrow-right-24: Configure](configuration.md)

</div>
