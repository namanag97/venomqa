#!/usr/bin/env python3
"""VenomQA Bootstrap Script.

Download and run directly:
    curl -fsSL https://venomqa.dev/install.py | python3 - init

Or save locally:
    curl -fsSL https://venomqa.dev/install.py -o venomqa
    chmod +x venomqa
    ./venomqa init

This script handles installation automatically - no pip commands needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ANSI colors
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"


def color(text: str, c: str) -> str:
    """Apply color if stdout is a tty."""
    if sys.stdout.isatty():
        return f"{c}{text}{RESET}"
    return text


def get_python() -> str:
    """Get the Python executable path."""
    return sys.executable


def is_venomqa_installed() -> bool:
    """Check if venomqa is importable."""
    try:
        import venomqa  # noqa: F401
        return True
    except ImportError:
        return False


def get_venomqa_version() -> str | None:
    """Get installed venomqa version."""
    try:
        import venomqa
        return getattr(venomqa, "__version__", "unknown")
    except ImportError:
        return None


def diagnose_environment() -> dict:
    """Diagnose Python environment issues."""
    info = {
        "python_path": sys.executable,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "sys_prefix": sys.prefix,
        "in_virtualenv": hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        ),
        "pip_available": False,
        "pipx_available": shutil.which("pipx") is not None,
        "uv_available": shutil.which("uv") is not None,
        "venomqa_importable": False,
        "venomqa_in_path": shutil.which("venomqa"),
        "issues": [],
    }

    # Check pip
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, check=True
        )
        info["pip_available"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        info["issues"].append("pip not available for this Python")

    # Check venomqa import
    try:
        import venomqa  # noqa: F401
        info["venomqa_importable"] = True
        info["venomqa_version"] = getattr(venomqa, "__version__", "unknown")
    except ImportError:
        pass

    # Detect environment mismatch
    if info["venomqa_in_path"] and not info["venomqa_importable"]:
        info["issues"].append(
            f"venomqa command found at {info['venomqa_in_path']} but package not importable - "
            "this usually means it was installed for a different Python"
        )

    return info


def print_diagnosis(info: dict) -> None:
    """Print environment diagnosis."""
    print(f"\n{color('Environment Diagnosis', BOLD)}")
    print("=" * 50)
    print(f"Python:      {info['python_path']}")
    print(f"Version:     {info['python_version']}")
    print(f"Virtualenv:  {'Yes' if info['in_virtualenv'] else 'No'}")
    print(f"pip:         {color('OK', GREEN) if info['pip_available'] else color('Not found', RED)}")
    print(f"pipx:        {color('Available', GREEN) if info['pipx_available'] else color('Not found', DIM)}")
    print(f"uv:          {color('Available', GREEN) if info['uv_available'] else color('Not found', DIM)}")

    if info["venomqa_in_path"]:
        print(f"venomqa cmd: {info['venomqa_in_path']}")
    else:
        print(f"venomqa cmd: {color('Not in PATH', DIM)}")

    if info["venomqa_importable"]:
        version = info.get("venomqa_version", "?")
        print(f"venomqa pkg: {color(f'v{version}', GREEN)}")
    else:
        print(f"venomqa pkg: {color('Not importable', YELLOW)}")

    if info["issues"]:
        print(f"\n{color('Issues Found:', YELLOW)}")
        for issue in info["issues"]:
            print(f"  - {issue}")


def print_fix_suggestions(info: dict) -> None:
    """Print suggestions to fix environment issues."""
    print(f"\n{color('Recommended Fix:', BOLD)}")

    if info["pipx_available"]:
        print(f"""
  The most reliable way to install CLI tools is with {color('pipx', CYAN)}:

    pipx install venomqa

  This creates an isolated environment and avoids Python conflicts.
""")
    elif info["uv_available"]:
        print(f"""
  You have {color('uv', CYAN)} installed. Use it to install venomqa:

    uv tool install venomqa
""")
    else:
        print(f"""
  Install with pip using this exact Python:

    {info['python_path']} -m pip install venomqa

  Or use this bootstrap script which handles everything:

    curl -fsSL https://venomqa.dev/install.py | python3 - init

  For the best experience, install {color('pipx', CYAN)} first:

    brew install pipx  # macOS
    apt install pipx   # Ubuntu/Debian
    pip install pipx   # Other

  Then: pipx install venomqa
""")


def install_venomqa(upgrade: bool = False, quiet: bool = False) -> bool:
    """Install venomqa using pip."""
    if not quiet:
        print()
        print("=" * 60)
        print(f"  {color('VenomQA', BOLD)} - Autonomous API Testing")
        print("=" * 60)

        if upgrade:
            print(f"\n{color('Upgrading venomqa...', CYAN)}")
        else:
            print(f"\n{color('Installing venomqa (first-time setup)...', CYAN)}")

    cmd = [get_python(), "-m", "pip", "install", "--quiet"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.append("venomqa")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            version = get_venomqa_version() or "latest"
            if not quiet:
                print(f"{color('OK', GREEN)} Successfully installed venomqa v{version}")
            return True
        else:
            if not quiet:
                print(f"{color('FAILED', RED)} Installation failed")
                if result.stderr:
                    # Show last few lines of error
                    lines = result.stderr.strip().split("\n")[-5:]
                    for line in lines:
                        print(f"  {color(line, DIM)}")

                # Run diagnosis
                info = diagnose_environment()
                print_diagnosis(info)
                print_fix_suggestions(info)
            return False
    except Exception as e:
        if not quiet:
            print(f"{color('ERROR', RED)} Installation error: {e}")
        return False


def run_venomqa(args: list[str]) -> int:
    """Run venomqa CLI with the given arguments."""
    try:
        from venomqa.cli import main
        sys.argv = ["venomqa"] + args
        main()
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def show_help() -> None:
    """Show bootstrap script help."""
    print("""
VenomQA Bootstrap Script
========================

Usage:
  ./venomqa.py <command> [options]
  python3 venomqa.py <command> [options]

Quick Start:
  ./venomqa.py init           Create a new VenomQA project
  ./venomqa.py doctor         Check system health
  ./venomqa.py --help         Show all commands

Bootstrap Options:
  --bootstrap-upgrade     Force upgrade venomqa before running
  --bootstrap-reinstall   Reinstall venomqa from scratch
  --bootstrap-version     Show installed version

One-liner Install:
  curl -fsSL https://raw.githubusercontent.com/namanag97/venomqa/main/venomqa.py | python3 - init

Documentation: https://venomqa.dev
""")


def main() -> int:
    """Main entry point for the bootstrap script."""
    args = sys.argv[1:]

    # Handle bootstrap-specific flags
    if "--bootstrap-upgrade" in args:
        args.remove("--bootstrap-upgrade")
        if not install_venomqa(upgrade=True):
            return 1

    if "--bootstrap-reinstall" in args:
        args.remove("--bootstrap-reinstall")
        subprocess.run([get_python(), "-m", "pip", "uninstall", "-y", "venomqa"],
                      capture_output=True)
        if not install_venomqa():
            return 1

    if "--bootstrap-version" in args:
        version = get_venomqa_version()
        if version:
            print(f"venomqa {version}")
        else:
            print("venomqa is not installed")
        return 0

    # Show help if no args
    if not args or args == ["--help"] or args == ["-h"]:
        if not is_venomqa_installed():
            show_help()
            print("\n⚠️  venomqa is not installed. Install with:")
            print(f"   {get_python()} -m pip install venomqa")
            print("\nOr run any command and it will install automatically:")
            print("   ./venomqa.py init")
            return 0

    # Auto-install if not present
    if not is_venomqa_installed():
        if not install_venomqa():
            return 1
        print()  # Blank line before command output

    # Run the actual venomqa CLI
    return run_venomqa(args)


if __name__ == "__main__":
    sys.exit(main())
