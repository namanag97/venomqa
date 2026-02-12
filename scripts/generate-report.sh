#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

REPORT_FORMAT="${1:-html}"
OUTPUT_DIR="${2:-reports}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$OUTPUT_DIR"

log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

generate_coverage_report() {
    log_info "Generating coverage report..."
    
    if command -v coverage &>/dev/null; then
        coverage html -d "$OUTPUT_DIR/coverage_html"
        coverage xml -o "$OUTPUT_DIR/coverage.xml"
        coverage json -o "$OUTPUT_DIR/coverage.json"
        log_info "Coverage reports generated in $OUTPUT_DIR"
    else
        python -m pytest tests/ \
            --cov=venomqa \
            --cov-report=html:"$OUTPUT_DIR/coverage_html" \
            --cov-report=xml:"$OUTPUT_DIR/coverage.xml" \
            --cov-report=json:"$OUTPUT_DIR/coverage.json" \
            --collect-only -q 2>/dev/null || true
    fi
}

generate_test_report() {
    log_info "Generating test report..."
    
    python -m pytest tests/ \
        --html="$OUTPUT_DIR/test_report_$TIMESTAMP.html" \
        --self-contained-html \
        --junit-xml="$OUTPUT_DIR/junit_$TIMESTAMP.xml" \
        -v \
        --tb=short || true
}

generate_journey_report() {
    log_info "Generating journey report..."
    
    local report_file="$OUTPUT_DIR/journey_report_$TIMESTAMP.$REPORT_FORMAT"
    
    if command -v venomqa &>/dev/null; then
        venomqa report --format "$REPORT_FORMAT" --output "$report_file" 2>/dev/null || {
            log_info "No journey results found, skipping journey report"
        }
    else
        log_info "venomqa not installed, skipping journey report"
    fi
}

generate_allure_report() {
    log_info "Generating Allure report..."
    
    if command -v allure &>/dev/null; then
        python -m pytest tests/ --alluredir="$OUTPUT_DIR/allure-results" || true
        allure generate "$OUTPUT_DIR/allure-results" -o "$OUTPUT_DIR/allure-report" --clean
        log_info "Allure report generated in $OUTPUT_DIR/allure-report"
    else
        log_info "Allure not installed, skipping Allure report"
    fi
}

generate_summary() {
    local summary_file="$OUTPUT_DIR/summary_$TIMESTAMP.md"
    
    log_info "Generating summary report..."
    
    cat > "$summary_file" << EOF
# VenomQA Test Report Summary

**Generated:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Format:** $REPORT_FORMAT

## Reports Generated

| Report Type | Location |
|------------|----------|
| Coverage (HTML) | $OUTPUT_DIR/coverage_html/ |
| Coverage (XML) | $OUTPUT_DIR/coverage.xml |
| Coverage (JSON) | $OUTPUT_DIR/coverage.json |
| Test Report (HTML) | $OUTPUT_DIR/test_report_$TIMESTAMP.html |
| JUnit XML | $OUTPUT_DIR/junit_$TIMESTAMP.xml |
| Journey Report | $OUTPUT_DIR/journey_report_$TIMESTAMP.$REPORT_FORMAT |

## Quick Links

- [Coverage Report](coverage_html/index.html)
- [Test Report](test_report_$TIMESTAMP.html)

EOF
    
    log_info "Summary written to $summary_file"
}

main() {
    log_info "VenomQA Report Generator"
    log_info "Output directory: $OUTPUT_DIR"
    log_info "Report format: $REPORT_FORMAT"
    
    generate_coverage_report
    generate_test_report
    generate_journey_report
    generate_allure_report
    generate_summary
    
    log_info "All reports generated in $OUTPUT_DIR"
}

main
