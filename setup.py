#!/usr/bin/env python3
"""VenomQA One-Click Setup Script.

This script provides a streamlined setup experience for VenomQA, including:
- Python version validation
- Virtual environment detection and creation
- Package installation
- Preflight checks
- Optional example project creation

Usage:
    python setup.py              # Interactive setup
    python setup.py --quick      # Quick setup with defaults
    python setup.py --example    # Setup with example project
    python setup.py --dev        # Setup for development
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


# ANSI color codes
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def supports_color() -> bool:
    """Check if the terminal supports color output."""
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    if platform.system() == "Windows":
        return os.getenv("TERM") == "ANSI" or os.getenv("WT_SESSION")
    return True


USE_COLOR = supports_color()


def color(text: str, color_code: str) -> str:
    """Apply color to text if supported."""
    if USE_COLOR:
        return f"{color_code}{text}{Colors.RESET}"
    return text


def print_header(text: str) -> None:
    """Print a header."""
    print()
    print(color(f"{'=' * 50}", Colors.BLUE))
    print(color(f"  {text}", Colors.BOLD + Colors.BLUE))
    print(color(f"{'=' * 50}", Colors.BLUE))
    print()


def print_step(step: int, total: int, text: str) -> None:
    """Print a step."""
    print(color(f"[{step}/{total}]", Colors.CYAN) + f" {text}")


def print_success(text: str) -> None:
    """Print a success message."""
    print(color("  [OK]", Colors.GREEN) + f" {text}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print(color("  [WARN]", Colors.YELLOW) + f" {text}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(color("  [ERROR]", Colors.RED) + f" {text}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(color("  [INFO]", Colors.DIM) + f" {text}")


def check_python_version() -> tuple[bool, str]:
    """Check if Python version meets minimum requirements (>= 3.10)."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version >= (3, 10):
        return True, version_str
    return False, version_str


def check_in_virtual_env() -> bool:
    """Check if running inside a virtual environment."""
    return (
        hasattr(sys, "real_prefix") or
        (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix) or
        os.getenv("VIRTUAL_ENV") is not None
    )


def find_python_executable() -> str:
    """Find the best Python executable to use."""
    # Try python3 first, then python
    for cmd in ["python3", "python"]:
        if shutil.which(cmd):
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return cmd
            except Exception:
                pass
    return "python3"


def create_virtual_env(venv_path: Path) -> bool:
    """Create a virtual environment."""
    try:
        python_cmd = find_python_executable()
        subprocess.run(
            [python_cmd, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False


def get_venv_python(venv_path: Path) -> str:
    """Get the Python executable path in the virtual environment."""
    if platform.system() == "Windows":
        return str(venv_path / "Scripts" / "python.exe")
    return str(venv_path / "bin" / "python")


def get_venv_activate(venv_path: Path) -> str:
    """Get the activation script path for the virtual environment."""
    if platform.system() == "Windows":
        return str(venv_path / "Scripts" / "activate")
    return str(venv_path / "bin" / "activate")


def install_package(python_cmd: str, package: str, dev: bool = False, user: bool = False) -> bool:
    """Install a package using pip."""
    try:
        extras = "[dev]" if dev else ""
        cmd = [python_cmd, "-m", "pip", "install", "-q"]
        if user:
            cmd.append("--user")
        cmd.append(f"{package}{extras}")
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def install_venomqa(python_cmd: str, editable: bool = False, dev: bool = False, user: bool = False) -> bool:
    """Install VenomQA package."""
    try:
        setup_dir = Path(__file__).parent.resolve()

        if editable:
            extras = "[dev]" if dev else ""
            cmd = [python_cmd, "-m", "pip", "install"]
            if user:
                cmd.append("--user")
            cmd.extend(["-e", f".{extras}"])
        else:
            # Try to install from PyPI first
            extras = "[dev]" if dev else ""
            cmd = [python_cmd, "-m", "pip", "install"]
            if user:
                cmd.append("--user")
            cmd.append(f"venomqa{extras}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(setup_dir) if editable else None,
        )

        # Check for PEP 668 error (externally managed environment)
        if result.returncode != 0:
            if "externally-managed-environment" in result.stderr.lower() or "pep 668" in result.stderr.lower():
                # Try with --user flag or --break-system-packages
                if not user:
                    print_info("System Python detected, trying --user install...")
                    return install_venomqa(python_cmd, editable=editable, dev=dev, user=True)
            # Fall back to editable install from local if PyPI failed
            if not editable:
                return install_venomqa(python_cmd, editable=True, dev=dev, user=user)
            return False

        return True
    except subprocess.CalledProcessError:
        # Fall back to editable install from local
        if not editable:
            return install_venomqa(python_cmd, editable=True, dev=dev, user=user)
        return False


def run_preflight_checks(python_cmd: str) -> bool:
    """Run VenomQA preflight checks."""
    try:
        result = subprocess.run(
            [python_cmd, "-m", "venomqa.cli", "doctor"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Print the output
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False
    except subprocess.TimeoutExpired:
        print_warning("Preflight checks timed out")
        return False
    except Exception as e:
        print_warning(f"Could not run preflight checks: {e}")
        return False


def create_example_project(python_cmd: str, path: str = "qa") -> bool:
    """Create an example VenomQA project."""
    try:
        result = subprocess.run(
            [python_cmd, "-m", "venomqa.cli", "init", "--with-sample", "-p", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False
    except Exception as e:
        print_error(f"Could not create example project: {e}")
        return False


def check_docker() -> tuple[bool, str]:
    """Check if Docker is installed and running."""
    if not shutil.which("docker"):
        return False, "Docker not found in PATH"

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            version_result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return True, version_result.stdout.strip()
        return False, "Docker daemon not running"
    except subprocess.TimeoutExpired:
        return False, "Docker check timed out"
    except Exception as e:
        return False, str(e)


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    while True:
        try:
            answer = input(f"{question} [{default_str}]: ").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            print("Please answer 'yes' or 'no'.")
        except (EOFError, KeyboardInterrupt):
            print()
            return default


def main() -> int:
    """Main setup function."""
    parser = argparse.ArgumentParser(
        description="VenomQA One-Click Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup.py              Interactive setup
  python setup.py --quick      Quick setup with defaults
  python setup.py --example    Setup with example project
  python setup.py --dev        Setup for development
        """,
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick setup with default options (no prompts)",
    )
    parser.add_argument(
        "--example", "-e",
        action="store_true",
        help="Create an example project after setup",
    )
    parser.add_argument(
        "--dev", "-d",
        action="store_true",
        help="Install development dependencies",
    )
    parser.add_argument(
        "--venv",
        type=str,
        default=".venv",
        help="Virtual environment path (default: .venv)",
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Skip virtual environment creation",
    )
    parser.add_argument(
        "--project-path",
        type=str,
        default="qa",
        help="Path for example project (default: qa)",
    )

    args = parser.parse_args()

    print_header("VenomQA One-Click Setup")

    total_steps = 5
    current_step = 0

    # Step 1: Check Python version
    current_step += 1
    print_step(current_step, total_steps, "Checking Python version...")

    py_ok, py_version = check_python_version()
    if not py_ok:
        print_error(f"Python {py_version} is not supported. VenomQA requires Python 3.10+")
        print_info("Please upgrade Python and try again.")
        print_info("Visit: https://www.python.org/downloads/")
        return 1

    print_success(f"Python {py_version}")

    # Step 2: Check/create virtual environment
    current_step += 1
    print_step(current_step, total_steps, "Setting up virtual environment...")

    in_venv = check_in_virtual_env()
    venv_path = Path(args.venv)
    python_cmd = sys.executable

    if args.no_venv:
        print_info("Skipping virtual environment (--no-venv)")
    elif in_venv:
        print_success(f"Already in virtual environment: {os.getenv('VIRTUAL_ENV', 'active')}")
    else:
        print_warning("Not in a virtual environment")

        create_venv = args.quick or prompt_yes_no(
            f"Create virtual environment at '{venv_path}'?"
        )

        if create_venv:
            if venv_path.exists():
                print_info(f"Using existing virtual environment: {venv_path}")
            else:
                print_info(f"Creating virtual environment: {venv_path}")
                if not create_virtual_env(venv_path):
                    return 1

            python_cmd = get_venv_python(venv_path)
            activate_path = get_venv_activate(venv_path)
            print_success(f"Virtual environment ready")
            print_info(f"Activate with: source {activate_path}")
        else:
            print_warning("Proceeding without virtual environment")

    # Step 3: Install VenomQA
    current_step += 1
    print_step(current_step, total_steps, "Installing VenomQA...")

    # Check if we're in the VenomQA source directory
    setup_dir = Path(__file__).parent.resolve()
    is_source_dir = (setup_dir / "pyproject.toml").exists() and (setup_dir / "venomqa").is_dir()

    if is_source_dir:
        print_info("Installing from source directory...")
        if not install_venomqa(python_cmd, editable=True, dev=args.dev):
            print_error("Failed to install VenomQA")
            return 1
    else:
        print_info("Installing from PyPI...")
        if not install_venomqa(python_cmd, editable=False, dev=args.dev):
            print_error("Failed to install VenomQA")
            return 1

    print_success("VenomQA installed successfully")

    # Step 4: Run preflight checks
    current_step += 1
    print_step(current_step, total_steps, "Running preflight checks...")

    preflight_ok = run_preflight_checks(python_cmd)
    if preflight_ok:
        print_success("All preflight checks passed")
    else:
        print_warning("Some preflight checks failed (see above)")
        print_info("VenomQA is installed but some features may not work")

    # Step 5: Create example project (optional)
    current_step += 1
    print_step(current_step, total_steps, "Example project setup...")

    create_example = args.example or (
        not args.quick and prompt_yes_no("Create an example project?")
    )

    if create_example:
        print_info(f"Creating example project at '{args.project_path}/'...")
        if create_example_project(python_cmd, args.project_path):
            print_success(f"Example project created at '{args.project_path}/'")
        else:
            print_warning("Could not create example project")
    else:
        print_info("Skipping example project")

    # Done!
    print_header("Setup Complete!")

    # Print activation instructions if we created a venv
    if not in_venv and not args.no_venv and venv_path.exists():
        activate_path = get_venv_activate(venv_path)
        print(color("Activate your virtual environment:", Colors.BOLD))
        print(f"  source {activate_path}")
        print()

    print(color("Quick start:", Colors.BOLD))
    print("  venomqa doctor      # Check system status")
    print("  venomqa init        # Initialize a new project")
    print("  venomqa run         # Run your tests")
    print()

    if create_example:
        print(color("Run your first test:", Colors.BOLD))
        print(f"  cd {args.project_path}")
        print("  venomqa run sample_journey")
        print()

    print(color("Documentation:", Colors.BOLD))
    print("  https://venomqa.dev")
    print()

    # Check Docker status
    docker_ok, docker_msg = check_docker()
    if not docker_ok:
        print(color("Note:", Colors.YELLOW))
        print(f"  Docker is not available: {docker_msg}")
        print("  Some VenomQA features require Docker.")
        print("  Install Docker: https://docs.docker.com/get-docker/")
        print()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(130)
