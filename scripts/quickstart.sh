#!/bin/bash
# VenomQA Quick Setup Script
# One-line install: curl -sSL https://venomqa.dev/install.sh | bash
#
# This script provides a quick setup experience for VenomQA:
# - Checks Python version (>= 3.10)
# - Creates a virtual environment
# - Installs VenomQA
# - Runs preflight checks
# - Optionally creates an example project

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Disable colors if not in terminal or NO_COLOR is set
if [[ ! -t 1 ]] || [[ -n "$NO_COLOR" ]]; then
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' DIM='' NC=''
fi

print_header() {
    echo ""
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BLUE}==================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}[$1/$2]${NC} $3"
}

print_success() {
    echo -e "  ${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "  ${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "  ${DIM}[INFO]${NC} $1"
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Find the best Python executable (3.10+)
find_python() {
    local python_cmd=""

    # Try python3.12, python3.11, python3.10, python3, python
    for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command_exists "$cmd"; then
            local version
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            if [[ -n "$version" ]]; then
                local major minor
                IFS='.' read -r major minor <<< "$version"
                if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 10 ]]; then
                    python_cmd="$cmd"
                    break
                fi
            fi
        fi
    done

    echo "$python_cmd"
}

# Get Python version
get_python_version() {
    "$1" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null
}

# Check if in virtual environment
in_virtualenv() {
    [[ -n "$VIRTUAL_ENV" ]] || "$PYTHON_CMD" -c "import sys; sys.exit(0 if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else 1)" 2>/dev/null
}

# Main setup function
main() {
    print_header "VenomQA Quick Setup"

    local VENV_PATH="${VENV_PATH:-.venv}"
    local PROJECT_PATH="${PROJECT_PATH:-qa}"
    local SKIP_EXAMPLE="${SKIP_EXAMPLE:-false}"
    local DEV_MODE="${DEV_MODE:-false}"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --venv)
                VENV_PATH="$2"
                shift 2
                ;;
            --project)
                PROJECT_PATH="$2"
                shift 2
                ;;
            --skip-example)
                SKIP_EXAMPLE="true"
                shift
                ;;
            --dev)
                DEV_MODE="true"
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --venv PATH        Virtual environment path (default: .venv)"
                echo "  --project PATH     Example project path (default: qa)"
                echo "  --skip-example     Skip creating example project"
                echo "  --dev              Install development dependencies"
                echo "  --help, -h         Show this help message"
                echo ""
                echo "Environment variables:"
                echo "  VENV_PATH          Virtual environment path"
                echo "  PROJECT_PATH       Example project path"
                echo "  SKIP_EXAMPLE       Set to 'true' to skip example"
                echo "  DEV_MODE           Set to 'true' for dev install"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    local TOTAL_STEPS=5
    local STEP=0

    # Step 1: Check Python version
    STEP=$((STEP + 1))
    print_step "$STEP" "$TOTAL_STEPS" "Checking Python version..."

    PYTHON_CMD=$(find_python)

    if [[ -z "$PYTHON_CMD" ]]; then
        print_error "Python 3.10+ is required but not found"
        print_info "Please install Python 3.10 or later:"
        print_info "  macOS: brew install python@3.12"
        print_info "  Ubuntu: sudo apt install python3.12"
        print_info "  Or visit: https://www.python.org/downloads/"
        exit 1
    fi

    local PY_VERSION
    PY_VERSION=$(get_python_version "$PYTHON_CMD")
    print_success "Python $PY_VERSION ($PYTHON_CMD)"

    # Step 2: Set up virtual environment
    STEP=$((STEP + 1))
    print_step "$STEP" "$TOTAL_STEPS" "Setting up virtual environment..."

    if in_virtualenv; then
        print_success "Already in virtual environment: ${VIRTUAL_ENV:-active}"
    elif [[ -d "$VENV_PATH" ]]; then
        print_info "Using existing virtual environment: $VENV_PATH"
        source "$VENV_PATH/bin/activate" 2>/dev/null || source "$VENV_PATH/Scripts/activate" 2>/dev/null
        print_success "Virtual environment activated"
    else
        print_info "Creating virtual environment: $VENV_PATH"
        "$PYTHON_CMD" -m venv "$VENV_PATH"
        source "$VENV_PATH/bin/activate" 2>/dev/null || source "$VENV_PATH/Scripts/activate" 2>/dev/null
        print_success "Virtual environment created and activated"
    fi

    # Update pip
    print_info "Upgrading pip..."
    pip install --upgrade pip -q

    # Step 3: Install VenomQA
    STEP=$((STEP + 1))
    print_step "$STEP" "$TOTAL_STEPS" "Installing VenomQA..."

    local INSTALL_EXTRAS=""
    if [[ "$DEV_MODE" == "true" ]]; then
        INSTALL_EXTRAS="[dev]"
    fi

    # Check if we're in the VenomQA source directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

    if [[ -f "$PROJECT_ROOT/pyproject.toml" ]] && [[ -d "$PROJECT_ROOT/venomqa" ]]; then
        print_info "Installing from source directory..."
        pip install -e "${PROJECT_ROOT}${INSTALL_EXTRAS}" -q
    else
        print_info "Installing from PyPI..."
        pip install "venomqa${INSTALL_EXTRAS}" -q || {
            print_warning "PyPI install failed, trying local install..."
            pip install -e "${PROJECT_ROOT}${INSTALL_EXTRAS}" -q
        }
    fi

    print_success "VenomQA installed successfully"

    # Step 4: Run preflight checks
    STEP=$((STEP + 1))
    print_step "$STEP" "$TOTAL_STEPS" "Running preflight checks..."

    if venomqa doctor 2>/dev/null; then
        print_success "All preflight checks passed"
    else
        print_warning "Some preflight checks failed (VenomQA will still work)"
    fi

    # Step 5: Create example project
    STEP=$((STEP + 1))
    print_step "$STEP" "$TOTAL_STEPS" "Example project setup..."

    if [[ "$SKIP_EXAMPLE" == "true" ]]; then
        print_info "Skipping example project (--skip-example)"
    else
        print_info "Creating example project at '$PROJECT_PATH/'..."
        venomqa init --with-sample -p "$PROJECT_PATH" 2>/dev/null && {
            print_success "Example project created"
        } || {
            print_warning "Could not create example project"
        }
    fi

    # Done!
    print_header "Setup Complete!"

    echo -e "${BOLD}Quick start:${NC}"
    echo "  venomqa doctor      # Check system status"
    echo "  venomqa init        # Initialize a new project"
    echo "  venomqa run         # Run your tests"
    echo ""

    if [[ "$SKIP_EXAMPLE" != "true" ]]; then
        echo -e "${BOLD}Run your first test:${NC}"
        echo "  cd $PROJECT_PATH"
        echo "  venomqa run sample_journey"
        echo ""
    fi

    echo -e "${BOLD}Documentation:${NC}"
    echo "  https://venomqa.dev"
    echo ""

    # Check Docker
    if ! command_exists docker; then
        echo -e "${YELLOW}Note:${NC}"
        echo "  Docker is not installed."
        echo "  Some VenomQA features require Docker."
        echo "  Install Docker: https://docs.docker.com/get-docker/"
        echo ""
    elif ! docker info >/dev/null 2>&1; then
        echo -e "${YELLOW}Note:${NC}"
        echo "  Docker daemon is not running."
        echo "  Start Docker to use all VenomQA features."
        echo ""
    fi

    # Remind about virtual environment activation
    if [[ -d "$VENV_PATH" ]] && [[ -z "$VIRTUAL_ENV" ]]; then
        echo -e "${BOLD}Activate your virtual environment:${NC}"
        echo "  source $VENV_PATH/bin/activate"
        echo ""
    fi
}

# Run main function
main "$@"
