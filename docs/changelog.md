# Changelog

All notable changes to VenomQA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MkDocs documentation site with Material theme
- Comprehensive API documentation
- Tutorial guides for common scenarios
- Advanced usage documentation

## [0.2.0] - 2024-01-15

### Added

- Ports and Adapters architecture
- Multiple cache adapters (Redis, Memory)
- Email testing adapters (Mailhog, Mailpit)
- Queue adapters (Redis Queue, Celery)
- Time control adapter for testing
- Mock server adapter (WireMock)
- SARIF report format
- Slack and Discord reporters
- Performance optimizations (connection pooling, caching)
- Security features (input validation, secrets management)
- File handling utilities

### Changed

- Improved error messages with fix suggestions
- Enhanced CLI output formatting
- Better parallel execution support

### Fixed

- Checkpoint rollback in nested branches
- Context restoration edge cases
- Connection handling in long-running journeys

## [0.1.0] - 2024-01-01

### Added

- Initial release
- Core journey DSL (Journey, Step, Checkpoint, Branch, Path)
- PostgreSQL state management
- HTTP client with retry logic
- Basic reporters (Markdown, JSON, JUnit)
- Docker Compose integration
- CLI tool (venomqa run, venomqa list, venomqa report)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 0.2.0 | 2024-01-15 | Ports & Adapters, Performance |
| 0.1.0 | 2024-01-01 | Initial release |

## Upgrade Guide

### 0.1.x to 0.2.x

No breaking changes. New features are additive.

To use new adapters:

```bash
pip install "venomqa[redis,s3]"  # Install adapter dependencies
```

## Roadmap

### v0.3.0 - Enhanced Reporting

- Interactive HTML reports with charts
- Slack/Teams webhook notifications
- Test trend analysis
- Flaky test detection

### v0.4.0 - Parallel Execution

- Distributed journey execution
- Shared state cache for checkpoints
- Resource-aware scheduling

### v0.5.0 - AI-Powered Features

- Journey generation from OpenAPI specs
- Intelligent failure analysis
- Anomaly detection

See [GitHub Projects](https://github.com/venomqa/venomqa/projects) for detailed tracking.
