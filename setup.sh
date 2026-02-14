#!/bin/bash
# VenomQA One-Click Setup
# Usage: curl -sSL https://venomqa.dev/install.sh | bash
#    or: ./setup.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Symbols
CHECK="${GREEN}[OK]${NC}"
CROSS="${RED}[X]${NC}"
WARN="${YELLOW}[!]${NC}"
INFO="${BLUE}[i]${NC}"

echo ""
echo -e "${CYAN}${BOLD}VenomQA - Stateful Journey QA Framework${NC}"
echo "============================================"
echo ""

# Minimum versions
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

# Track installation status
INSTALL_SUCCESS=true
WARNINGS=()

# ============================================================================
# Helper Functions
# ============================================================================

log_check() {
    echo -e "  ${CHECK} $1"
}

log_cross() {
    echo -e "  ${CROSS} $1"
    INSTALL_SUCCESS=false
}

log_warn() {
    echo -e "  ${WARN} $1"
    WARNINGS+=("$1")
}

log_info() {
    echo -e "  ${INFO} $1"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

version_gte() {
    # Compare versions: returns 0 if $1 >= $2
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# ============================================================================
# Preflight Checks
# ============================================================================

echo -e "${BOLD}Preflight Checks${NC}"
echo "----------------"

# Check Python
check_python() {
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        log_cross "Python not found. Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+"
        return 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -lt "$MIN_PYTHON_MAJOR" ] || \
       ([ "$PYTHON_MAJOR" -eq "$MIN_PYTHON_MAJOR" ] && [ "$PYTHON_MINOR" -lt "$MIN_PYTHON_MINOR" ]); then
        log_cross "Python $PYTHON_VERSION found, but ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ required"
        return 1
    fi

    log_check "Python $PYTHON_VERSION"
    return 0
}

# Check pip
check_pip() {
    if command_exists pip3; then
        PIP_CMD="pip3"
    elif command_exists pip; then
        PIP_CMD="pip"
    else
        log_cross "pip not found. Please install pip"
        return 1
    fi

    PIP_VERSION=$($PIP_CMD --version 2>&1 | cut -d' ' -f2)
    log_check "pip $PIP_VERSION"
    return 0
}

# Check uv (optional, preferred)
check_uv() {
    if command_exists uv; then
        UV_VERSION=$(uv --version 2>&1 | cut -d' ' -f2)
        log_check "uv $UV_VERSION (fast package manager detected)"
        USE_UV=true
        return 0
    else
        log_info "uv not found (optional - will use pip)"
        USE_UV=false
        return 0
    fi
}

# Check Docker
check_docker() {
    if ! command_exists docker; then
        log_warn "Docker not installed (optional, needed for stateful testing)"
        return 0
    fi

    # Check if Docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        log_warn "Docker installed but not running"
        return 0
    fi

    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | tr -d ',')
    log_check "Docker $DOCKER_VERSION"
    return 0
}

# Check Docker Compose
check_docker_compose() {
    # Check for docker compose (v2) or docker-compose (v1)
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || docker compose version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        log_check "Docker Compose $COMPOSE_VERSION (v2)"
        COMPOSE_CMD="docker compose"
        return 0
    elif command_exists docker-compose; then
        COMPOSE_VERSION=$(docker-compose --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        log_check "docker-compose $COMPOSE_VERSION (v1)"
        COMPOSE_CMD="docker-compose"
        return 0
    else
        log_warn "Docker Compose not found (optional, needed for local environments)"
        return 0
    fi
}

# Check Git (optional)
check_git() {
    if command_exists git; then
        GIT_VERSION=$(git --version | cut -d' ' -f3)
        log_check "Git $GIT_VERSION"
    else
        log_info "Git not found (optional)"
    fi
    return 0
}

# Run all preflight checks
check_python
check_pip
check_uv
check_docker
check_docker_compose
check_git

echo ""

if [ "$INSTALL_SUCCESS" = false ]; then
    echo -e "${RED}${BOLD}Preflight checks failed. Please fix the issues above and try again.${NC}"
    exit 1
fi

# ============================================================================
# Installation
# ============================================================================

echo -e "${BOLD}Installing VenomQA${NC}"
echo "------------------"

install_venomqa() {
    if [ "$USE_UV" = true ]; then
        log_info "Using uv for installation (faster)"
        if uv pip install venomqa 2>/dev/null; then
            log_check "VenomQA installed via uv"
            return 0
        else
            log_info "uv install failed, falling back to pip"
        fi
    fi

    log_info "Using pip for installation"
    if $PIP_CMD install venomqa 2>/dev/null; then
        log_check "VenomQA installed via pip"
        return 0
    fi

    # If package not on PyPI, try local install
    if [ -f "pyproject.toml" ]; then
        log_info "Installing from local source"
        if $PIP_CMD install -e . 2>/dev/null; then
            log_check "VenomQA installed from local source"
            return 0
        fi
    fi

    log_cross "Failed to install VenomQA"
    return 1
}

install_venomqa

echo ""

# ============================================================================
# Verification
# ============================================================================

echo -e "${BOLD}Verifying Installation${NC}"
echo "----------------------"

verify_installation() {
    # Check venomqa command is available
    if command_exists venomqa; then
        VENOMQA_VERSION=$(venomqa --version 2>&1 || echo "unknown")
        log_check "venomqa CLI: $VENOMQA_VERSION"
    else
        log_cross "venomqa command not found in PATH"
        log_info "You may need to add ~/.local/bin to your PATH"
        return 1
    fi

    # Run doctor command
    echo ""
    echo -e "${BOLD}Running Health Checks${NC}"
    echo "---------------------"

    if venomqa doctor 2>/dev/null; then
        log_check "Health checks passed"
    else
        log_warn "Some health checks failed (non-critical)"
    fi

    return 0
}

verify_installation

echo ""

# ============================================================================
# Quick Start Guide
# ============================================================================

echo -e "${BOLD}${GREEN}Installation Complete!${NC}"
echo ""
echo -e "${BOLD}Quick Start Guide${NC}"
echo "-----------------"
echo ""
echo "  1. Initialize a new project:"
echo -e "     ${CYAN}venomqa init${NC}"
echo ""
echo "  2. Configure your environment in venomqa.yaml"
echo ""
echo "  3. Create your first journey in journeys/"
echo ""
echo "  4. Run your journeys:"
echo -e "     ${CYAN}venomqa run${NC}"
echo ""
echo "  5. Check system status anytime:"
echo -e "     ${CYAN}venomqa doctor${NC}"
echo ""

if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo -e "${YELLOW}${BOLD}Warnings:${NC}"
    for warning in "${WARNINGS[@]}"; do
        echo -e "  ${WARN} $warning"
    done
    echo ""
fi

echo -e "${BOLD}Learn More${NC}"
echo "----------"
echo "  Documentation: https://venomqa.dev"
echo "  GitHub:        https://github.com/venomqa/venomqa"
echo "  Examples:      venomqa init --example quickstart"
echo ""
echo -e "${GREEN}Happy Testing!${NC}"
