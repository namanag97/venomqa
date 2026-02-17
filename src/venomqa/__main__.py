"""VenomQA CLI entry point.

This module enables running VenomQA as:
    python -m venomqa <command>

This is the recommended way to run venomqa during development or when
the global `venomqa` command isn't available.
"""

from venomqa.cli import main

if __name__ == "__main__":
    main()
