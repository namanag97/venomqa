#!/bin/bash
#
# Run VenomQA journeys with proper exit code handling
#
# This script wraps venomqa run with additional functionality:
# - Waits for services to be ready
# - Generates reports in multiple formats
# - Returns proper exit codes for CI/CD
#
# Environment variables:
#   VENOMQA_CONFIG       - Path to config file (default: qa/venomqa.yaml)
#   VENOMQA_REPORT_DIR   - Report output directory (default: /app/reports)
#   VENOMQA_BASE_URL     - API base URL
#   VENOMQA_TIMEOUT      - Request timeout in seconds
#   WAIT_FOR_POSTGRES    - PostgreSQL host:port to wait for
#   WAIT_FOR_REDIS       - Redis host:port to wait for
#   WAIT_FOR_HTTP        - HTTP URL to wait for
#   WAIT_TIMEOUT         - Maximum wait time (default: 60)
#   FAIL_FAST            - Stop on first failure (true/false)
#   JOURNEY_FILTER       - Space-separated list of journeys to run
#
# Exit codes:
#   0 - All journeys passed
#   1 - Some journeys failed
#   2 - Configuration error

set -e

# Configuration
CONFIG_FILE=${VENOMQA_CONFIG:-qa/venomqa.yaml}
REPORT_DIR=${VENOMQA_REPORT_DIR:-/app/reports}
FAIL_FAST_FLAG=""
JOURNEYS="${JOURNEY_FILTER:-}"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    log "ERROR: $*" >&2
}

# Create report directory
mkdir -p "$REPORT_DIR"

# Validate configuration
if [ -f "$CONFIG_FILE" ]; then
    log "Using configuration: $CONFIG_FILE"
    python -c "import yaml; yaml.safe_load(open('$CONFIG_FILE'))" 2>/dev/null || {
        error "Invalid YAML configuration: $CONFIG_FILE"
        exit 2
    }
else
    log "Warning: Configuration file not found: $CONFIG_FILE"
fi

# Wait for services if specified
WAIT_ARGS=""

if [ -n "$WAIT_FOR_POSTGRES" ]; then
    WAIT_ARGS="$WAIT_ARGS --postgres $WAIT_FOR_POSTGRES"
fi

if [ -n "$WAIT_FOR_REDIS" ]; then
    WAIT_ARGS="$WAIT_ARGS --redis $WAIT_FOR_REDIS"
fi

if [ -n "$WAIT_FOR_HTTP" ]; then
    WAIT_ARGS="$WAIT_ARGS --http $WAIT_FOR_HTTP"
fi

if [ -n "$WAIT_ARGS" ]; then
    log "Waiting for services..."
    wait-for-services.sh $WAIT_ARGS || {
        error "Services did not become ready"
        exit 2
    }
fi

# Set fail-fast flag
if [ "${FAIL_FAST,,}" = "true" ]; then
    FAIL_FAST_FLAG="--fail-fast"
fi

# Run journeys
log "Running VenomQA journeys..."
log "  Config: $CONFIG_FILE"
log "  Journeys: ${JOURNEYS:-all}"
log "  Report directory: $REPORT_DIR"

# Capture exit code
set +e
venomqa run $JOURNEYS \
    --config "$CONFIG_FILE" \
    --format text \
    $FAIL_FAST_FLAG

JOURNEY_EXIT_CODE=$?
set -e

log "Journey execution completed with exit code: $JOURNEY_EXIT_CODE"

# Generate reports
log "Generating reports..."

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# JUnit report (for CI/CD integration)
venomqa report --format junit --output "$REPORT_DIR/junit-$TIMESTAMP.xml" 2>/dev/null || true
# Also create a non-timestamped version for easy CI pickup
cp "$REPORT_DIR/junit-$TIMESTAMP.xml" "$REPORT_DIR/junit.xml" 2>/dev/null || true

# HTML report (for human review)
venomqa report --format html --output "$REPORT_DIR/report-$TIMESTAMP.html" 2>/dev/null || true
cp "$REPORT_DIR/report-$TIMESTAMP.html" "$REPORT_DIR/report.html" 2>/dev/null || true

# JSON report (for programmatic access)
venomqa report --format json --output "$REPORT_DIR/results-$TIMESTAMP.json" 2>/dev/null || true
cp "$REPORT_DIR/results-$TIMESTAMP.json" "$REPORT_DIR/results.json" 2>/dev/null || true

# Markdown report
venomqa report --format markdown --output "$REPORT_DIR/report-$TIMESTAMP.md" 2>/dev/null || true

log "Reports generated in $REPORT_DIR"

# Print summary
if [ $JOURNEY_EXIT_CODE -eq 0 ]; then
    log "SUCCESS: All journeys passed"
else
    error "FAILURE: Some journeys failed"
fi

# Return the journey exit code
exit $JOURNEY_EXIT_CODE
