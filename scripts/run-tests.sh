#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    log_info "Cleaning up..."
    docker-compose -f docker/docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
}

trap cleanup EXIT

run_unit_tests() {
    log_info "Running unit tests..."
    python -m pytest tests/ \
        -v \
        --tb=short \
        --cov=venomqa \
        --cov-report=term-missing \
        --cov-report=xml:coverage.xml \
        --cov-fail-under=80 \
        -x
}

run_integration_tests() {
    log_info "Running integration tests..."
    python -m pytest tests/test_integration.py \
        -v \
        --tb=short \
        --timeout=60
}

run_stress_tests() {
    log_info "Running stress tests..."
    python -m pytest tests/stress/ \
        -v \
        --tb=short \
        --timeout=300
}

run_docker_tests() {
    log_info "Running tests in Docker..."
    docker-compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit
}

run_all_tests() {
    log_info "Running all tests..."
    run_unit_tests
    run_integration_tests
    run_stress_tests
}

main() {
    local test_type="${1:-all}"
    
    log_info "VenomQA Test Runner"
    log_info "Test type: $test_type"
    
    case "$test_type" in
        unit)
            run_unit_tests
            ;;
        integration)
            run_integration_tests
            ;;
        stress)
            run_stress_tests
            ;;
        docker)
            run_docker_tests
            ;;
        all)
            run_all_tests
            ;;
        *)
            log_error "Unknown test type: $test_type"
            echo "Usage: $0 {unit|integration|stress|docker|all}"
            exit 1
            ;;
    esac
    
    log_info "Tests completed successfully!"
}

main "$@"
