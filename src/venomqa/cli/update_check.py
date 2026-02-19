"""Non-blocking PyPI update checker.

Checks once per 24 hours in a background thread.
Result is shown after the command completes — zero startup latency impact.

Cache file: ~/.venomqa/update-check.json
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple


_CACHE_DIR = Path.home() / ".venomqa"
_CACHE_FILE = _CACHE_DIR / "update-check.json"
_CHECK_INTERVAL = timedelta(hours=24)
_PYPI_URL = "https://pypi.org/pypi/venomqa/json"
_FETCH_TIMEOUT = 2  # seconds — never block the user


class UpdateInfo(NamedTuple):
    current: str
    latest: str


def _current_version() -> str:
    try:
        from venomqa import __version__
        return __version__
    except Exception:
        return "0.0.0"


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _read_cache() -> dict | None:
    try:
        if _CACHE_FILE.exists():
            data = json.loads(_CACHE_FILE.read_text())
            checked_at = datetime.fromisoformat(data["checked_at"])
            if datetime.now() - checked_at < _CHECK_INTERVAL:
                return data
    except Exception:
        pass
    return None


def _write_cache(latest: str) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps({
            "checked_at": datetime.now().isoformat(),
            "latest": latest,
        }))
    except Exception:
        pass


def _fetch_latest_from_pypi() -> str | None:
    try:
        import urllib.request
        with urllib.request.urlopen(_PYPI_URL, timeout=_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


class UpdateChecker:
    """Starts a background thread to check for updates.

    Usage:
        checker = UpdateChecker()
        checker.start()
        # ... run the command ...
        checker.show_if_available()
    """

    def __init__(self) -> None:
        self._result: UpdateInfo | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Kick off the background check (non-blocking)."""
        self._thread = threading.Thread(target=self._check, daemon=True, name="venomqa-update")
        self._thread.start()

    def _check(self) -> None:
        current = _current_version()

        # Try cache first — avoids hitting network on every run
        cached = _read_cache()
        if cached:
            latest = cached["latest"]
        else:
            latest = _fetch_latest_from_pypi()
            if latest:
                _write_cache(latest)

        if latest and _parse_version(latest) > _parse_version(current):
            self._result = UpdateInfo(current=current, latest=latest)

    def show_if_available(self) -> None:
        """Wait briefly for the thread, then print notice if update found."""
        if self._thread:
            self._thread.join(timeout=0.1)  # don't wait long — just collect if done

        if not self._result:
            return

        current, latest = self._result
        try:
            from rich.console import Console
            from rich.panel import Panel

            console = Console(stderr=True)
            console.print()
            console.print(Panel(
                f"[bold yellow]venomqa {latest}[/bold yellow] is available "
                f"[dim](you have {current})[/dim]\n\n"
                f"[bold]pip install --upgrade venomqa[/bold]",
                title="[yellow]Update available[/yellow]",
                border_style="yellow",
                expand=False,
            ))
        except Exception:
            # Rich not available — plain text fallback
            import sys
            print(
                f"\n  Update available: venomqa {current} → {latest}\n"
                f"  Run: pip install --upgrade venomqa\n",
                file=sys.stderr,
            )
