"""Journey compiler - converts DSL to core objects.

IMPORTANT: Understanding DSL vs Exploration
───────────────────────────────────────────

The Journey DSL is for ORGANIZING test scenarios, not for CONTROLLING exploration.

What the DSL provides:
- Action definitions (what can be done)
- Checkpoint markers (for rollback points)
- Invariants (what to check)
- Human-readable structure

What the Agent does:
- Explores ALL valid (state, action) pairs
- Uses BFS/DFS/Random strategy
- Ignores DSL ordering (explores exhaustively)

If you want to RESTRICT which actions can run from which states,
use ACTION PRECONDITIONS, not DSL structure:

    # This doesn't restrict exploration:
    Journey(
        steps=[
            Step("login", login),
            Checkpoint("logged_in"),
            Branch(from_checkpoint="logged_in", paths=[...])  # Agent ignores this!
        ]
    )

    # This DOES restrict exploration:
    Action(
        name="create_order",
        execute=create_order,
        preconditions=[lambda s: s.observations["db"].get("logged_in")]
    )
"""

from __future__ import annotations

from venomqa.v1.core.action import Action
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant
from venomqa.v1.dsl.journey import Branch, Checkpoint, Journey, Step


class CompiledJourney:
    """Result of compiling a Journey.

    Note: The DSL structure (Branch, Path, checkpoint ordering) is for
    human organization. The Agent will explore all valid actions from
    all states regardless of DSL structure. Use preconditions to restrict.
    """

    def __init__(
        self,
        actions: list[Action],
        invariants: list[Invariant],
        checkpoints: list[str],
    ) -> None:
        self.actions = actions
        self.invariants = invariants
        self.checkpoints = checkpoints

    def to_graph(self) -> Graph:
        """Create a Graph with the compiled actions."""
        return Graph(self.actions)


def compile(journey: Journey) -> CompiledJourney:
    """Compile a Journey DSL into core objects.

    This extracts:
    - A list of Actions (from Steps)
    - A list of Invariants
    - A list of checkpoint names

    NOTE: The Branch/Path structure is for human organization only.
    The Agent explores ALL valid (state, action) pairs regardless
    of DSL structure. Use action preconditions to control flow.

    Args:
        journey: The Journey to compile.

    Returns:
        A CompiledJourney with actions, invariants, and checkpoint names.
    """
    actions: list[Action] = []
    checkpoints: list[str] = []
    seen_actions: set[str] = set()

    # Process main steps
    for item in journey.steps:
        if isinstance(item, Step):
            if item.name not in seen_actions:
                action = _step_to_action(item)
                actions.append(action)
                seen_actions.add(item.name)

        elif isinstance(item, Checkpoint):
            checkpoints.append(item.name)

        elif isinstance(item, Branch):
            # Process all paths in the branch
            for path in item.paths:
                for step in path.steps:
                    if isinstance(step, Step):
                        if step.name not in seen_actions:
                            action = _step_to_action(step)
                            actions.append(action)
                            seen_actions.add(step.name)
                    elif isinstance(step, Checkpoint):
                        if step.name not in checkpoints:
                            checkpoints.append(step.name)

    return CompiledJourney(
        actions=actions,
        invariants=list(journey.invariants),
        checkpoints=checkpoints,
    )


def _step_to_action(step: Step) -> Action:
    """Convert a Step to an Action."""
    return Action(
        name=step.name,
        execute=step.action,
        description=step.description,
    )
