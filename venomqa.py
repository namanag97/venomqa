#!/usr/bin/env python3
"""VenomQA Bootstrap Script.

Download and run directly:
    curl -fsSL https://raw.githubusercontent.com/namanag97/venomqa/main/venomqa.py | python3 - init

Or save locally:
    curl -fsSL https://raw.githubusercontent.com/namanag97/venomqa/main/venomqa.py -o venomqa
    chmod +x venomqa
    ./venomqa init

This script handles installation automatically - no pip commands needed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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


def install_venomqa(upgrade: bool = False) -> bool:
    """Install venomqa using pip."""
    print("\n" + "=" * 60)
    print("  VenomQA - Autonomous API Testing")
    print("=" * 60)

    if upgrade:
        print("\n📦 Upgrading venomqa...")
    else:
        print("\n📦 Installing venomqa (first-time setup)...")

    cmd = [get_python(), "-m", "pip", "install", "--quiet"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.append("venomqa")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            version = get_venomqa_version() or "latest"
            print(f"✓ Successfully installed venomqa v{version}")
            return True
        else:
            print(f"✗ Installation failed: {result.stderr}")
            print("\nManual installation:")
            print(f"  {get_python()} -m pip install venomqa")
            return False
    except Exception as e:
        print(f"✗ Installation error: {e}")
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
