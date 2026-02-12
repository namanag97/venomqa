"""VenomQA CLI - Command line interface for VenomQA."""

from venomqa.cli.commands import cli
from venomqa.cli.output import CLIOutput, ProgressConfig, create_output


def main() -> None:
    """Main entry point for the venomqa CLI."""
    cli()


__all__ = ["main", "cli", "CLIOutput", "ProgressConfig", "create_output"]
