"""VenomQA CLI - Command line interface for VenomQA."""

from venomqa.cli.commands import cli


def main() -> None:
    """Main entry point for the venomqa CLI."""
    cli()


__all__ = ["main", "cli"]
