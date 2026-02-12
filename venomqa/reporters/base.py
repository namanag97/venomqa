"""Abstract base reporter class for VenomQA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from venomqa.core.models import JourneyResult


class BaseReporter(ABC):
    """Abstract base class for all reporters."""

    def __init__(self, output_path: str | Path | None = None):
        self.output_path = Path(output_path) if output_path else None

    @abstractmethod
    def generate(self, results: list[JourneyResult]) -> str | dict[str, Any] | bytes:
        """Generate report from journey results."""
        ...

    def save(self, results: list[JourneyResult], path: str | Path | None = None) -> Path:
        """Save report to file."""
        output_path = Path(path) if path else self.output_path
        if not output_path:
            raise ValueError("Output path required for saving report")

        content = self.generate(results)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"
        with open(output_path, mode, encoding=encoding) as f:
            f.write(content)

        return output_path

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return file extension for this reporter (e.g., '.md', '.json')."""
        ...
