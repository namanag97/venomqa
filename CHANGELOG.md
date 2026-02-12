# Changelog

All notable changes to VenomQA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial public release

## [0.1.0] - 2024-01-15

### Added

- Core journey DSL with Journey, Step, Checkpoint, Branch, and Path models
- JourneyRunner for executing journeys with branching and rollback
- HTTP Client with retry logic and request history tracking
- AsyncClient for async HTTP operations
- ExecutionContext for sharing state between steps
- PostgreSQL state manager with SAVEPOINT support
- Docker Compose infrastructure manager
- Multiple reporter formats:
  - MarkdownReporter for human-readable reports
  - JSONReporter for structured output
  - JUnitReporter for CI/CD integration
- CLI commands:
  - `venomqa run` - Execute journeys
  - `venomqa list` - List available journeys
  - `venomqa report` - Generate reports
- Configuration via YAML file and environment variables
- Automatic issue capture with suggestions
- Parallel path execution support
- Request/response logging

### Documentation

- API reference documentation
- CLI usage guide
- Journey writing guide
- Database backend configuration
- Advanced usage patterns
- Real-world examples

### Dependencies

- httpx>=0.25.0 for HTTP client
- pydantic>=2.0.0 for data validation
- pydantic-settings>=2.0.0 for configuration
- click>=8.0.0 for CLI
- rich>=13.0.0 for output formatting
- pyyaml>=6.0 for configuration
- psycopg[binary]>=3.1.0 for PostgreSQL

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.1.0 | 2024-01-15 | Initial release |

---

## Future Roadmap

### Planned for 0.2.0

- MySQL state backend support
- SQLite state backend for local testing
- WebSocket client for real-time testing
- Improved parallel execution with process pools
- Watch mode for re-running on file changes

### Planned for 0.3.0

- OpenAPI spec journey generation
- Hypothesis integration for property-based testing
- Failure clustering and analysis
- Distributed execution support

### Planned for 1.0.0

- Stable API guarantee
- Complete documentation
- Full test coverage
- Performance benchmarks
