"""Smoke tests for the public venomqa API.

Validates that every name in venomqa.__all__ is actually importable and that
the CLI entry point loads. This is the canary that catches botched __init__.py
edits (e.g. a renamed import) before they reach PyPI.
"""

import venomqa


def test_all_exports_present():
    """Every name declared in __all__ must exist as an attribute on the package."""
    missing = [name for name in venomqa.__all__ if not hasattr(venomqa, name)]
    assert not missing, (
        f"The following names are in venomqa.__all__ but cannot be imported: {missing}\n"
        "This is a broken __init__.py — fix the import, not this test."
    )


def test_all_exports_count():
    """__all__ must not be empty (guards against accidental wipe)."""
    assert len(venomqa.__all__) >= 50, (
        f"venomqa.__all__ only has {len(venomqa.__all__)} entries — suspiciously small."
    )


def test_cli_importable():
    """CLI entry point must load without errors."""
    from venomqa.cli import main  # noqa: F401

    assert callable(main)


def test_cli_commands_importable():
    """CLI commands module must have no syntax errors."""
    from venomqa.cli.commands import cli  # noqa: F401

    assert cli is not None


def test_validation_exports():
    """Validation module public symbols must be importable by name."""
    from venomqa import SchemaValidator, has_fields, is_list, matches_type, validate_response  # noqa: F401

    assert callable(has_fields)
    assert callable(is_list)
    assert callable(matches_type)
    assert callable(validate_response)
    # SchemaValidator is a dataclass, not callable in the usual sense — just check it exists
    assert SchemaValidator is not None


def test_core_exports():
    """Core action/invariant types must be importable."""
    from venomqa import Action, Agent, BFS, DFS, Invariant, Severity, Violation, World  # noqa: F401

    assert Action is not None
    assert Invariant is not None
    assert World is not None
    assert Agent is not None


def test_version_present():
    """Package must expose a __version__ string."""
    assert hasattr(venomqa, "__version__")
    assert isinstance(venomqa.__version__, str)
    assert venomqa.__version__  # non-empty


def test_core_api_works():
    """Agent.explore() runs without error using the correct minimal API.

    This test exists specifically to catch documentation/API drift — i.e. cases
    where CLAUDE.md or examples reference a wrong constructor signature or a
    method that doesn't exist (e.g. agent.run() vs agent.explore()).
    """
    from unittest.mock import MagicMock

    from venomqa import Action, Agent, BFS, Invariant, Severity, World

    call_count = {"n": 0}

    def increment(api, context):
        call_count["n"] += 1
        context.set("count", call_count["n"])
        return MagicMock(status_code=200)

    inv = Invariant(
        name="non_negative",
        check=lambda world: world.context.get("count", 0) >= 0,
        severity=Severity.CRITICAL,
    )

    # World requires state_from_context OR systems — bare World(api=api) raises ValueError
    world = World(api=MagicMock(), state_from_context=["count"])

    # actions/invariants go on Agent, not World; BFS() takes no arguments
    agent = Agent(
        world=world,
        actions=[Action(name="increment", execute=increment)],
        invariants=[inv],
        strategy=BFS(),
        max_steps=10,
    )

    # Method is .explore(), NOT .run()
    result = agent.explore()

    assert isinstance(result.states_visited, int)
    assert isinstance(result.violations, list)
    assert result.violations == [], f"Unexpected violations: {result.violations}"
