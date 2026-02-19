#!/bin/bash
# VenomQA Installer Script
# Usage: curl -fsSL https://venomqa.dev/install.sh | bash
#    or: curl -fsSL https://raw.githubusercontent.com/namanag97/venomqa/main/scripts/install.sh | bash

set -e

BOLD='\033[1m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
CYAN='\033[36m'
RESET='\033[0m'

echo ""
echo -e "${BOLD}VenomQA Installer${RESET}"
echo "================================"
echo ""

# Detect Python
detect_python() {
    if command -v python3 &> /dev/null; then
        echo "python3"
    elif command -v python &> /dev/null; then
        # Check if python is python3
        if python --version 2>&1 | grep -q "Python 3"; then
            echo "python"
        else
            return 1
        fi
    else
        return 1
    fi
}

PYTHON=$(detect_python)
if [ -z "$PYTHON" ]; then
    echo -e "${RED}Error: Python 3 is required but not found.${RESET}"
    echo ""
    echo "Install Python 3:"
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    echo "  Windows: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2)
echo -e "Python:  ${GREEN}$PYTHON_VERSION${RESET} ($PYTHON)"

# Check Python version >= 3.10
MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo -e "${RED}Error: Python 3.10+ is required (found $PYTHON_VERSION)${RESET}"
    exit 1
fi

# Check if pipx is available (preferred method)
if command -v pipx &> /dev/null; then
    echo -e "pipx:    ${GREEN}available${RESET}"
    echo ""
    echo -e "${BOLD}Installing with pipx (recommended)...${RESET}"
    pipx install venomqa --force
    echo ""
    echo -e "${GREEN}✓ Installation complete!${RESET}"
    echo ""
    echo "Run:"
    echo -e "  ${CYAN}venomqa init${RESET}     Create a new project"
    echo -e "  ${CYAN}venomqa doctor${RESET}   Check system health"
    exit 0
fi

# Check if uv is available
if command -v uv &> /dev/null; then
    echo -e "uv:      ${GREEN}available${RESET}"
    echo ""
    echo -e "${BOLD}Installing with uv...${RESET}"
    uv tool install venomqa
    echo ""
    echo -e "${GREEN}✓ Installation complete!${RESET}"
    echo ""
    echo "Run:"
    echo -e "  ${CYAN}venomqa init${RESET}     Create a new project"
    echo -e "  ${CYAN}venomqa doctor${RESET}   Check system health"
    exit 0
fi

# Fall back to pip
echo -e "pipx:    ${YELLOW}not found (using pip)${RESET}"
echo ""
echo -e "${BOLD}Installing with pip...${RESET}"

# Try pip install
if $PYTHON -m pip install venomqa --quiet; then
    echo ""
    echo -e "${GREEN}✓ Installation complete!${RESET}"
else
    echo ""
    echo -e "${YELLOW}pip install failed. Trying with --user...${RESET}"
    if $PYTHON -m pip install --user venomqa --quiet; then
        echo ""
        echo -e "${GREEN}✓ Installation complete (user install)!${RESET}"
        echo ""
        echo -e "${YELLOW}Note: You may need to add ~/.local/bin to your PATH${RESET}"
        echo "  Add this to your ~/.bashrc or ~/.zshrc:"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    else
        echo ""
        echo -e "${RED}Installation failed.${RESET}"
        echo ""
        echo "Try manually:"
        echo "  $PYTHON -m pip install venomqa"
        echo ""
        echo "Or use the bootstrap script:"
        echo "  curl -fsSL https://raw.githubusercontent.com/namanag97/venomqa/main/venomqa.py -o venomqa.py"
        echo "  python3 venomqa.py init"
        exit 1
    fi
fi

echo ""
echo "Run:"
echo -e "  ${CYAN}venomqa init${RESET}     Create a new project"
echo -e "  ${CYAN}venomqa doctor${RESET}   Check system health"
echo ""

# Check if venomqa command works
if ! command -v venomqa &> /dev/null; then
    echo -e "${YELLOW}Note: 'venomqa' command not in PATH.${RESET}"
    echo "You can run with:"
    echo -e "  ${CYAN}$PYTHON -m venomqa init${RESET}"
fi
