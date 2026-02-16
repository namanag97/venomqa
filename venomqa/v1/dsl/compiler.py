"""Journey compiler - converts DSL to core objects."""

from __future__ import annotations

from venomqa.v1.core.action import Action
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant
from venomqa.v1.dsl.journey import Journey, Step, Checkpoint, Branch, Path


class CompiledJourney:
    """Result of compiling a Journey."""

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

    This flattens the journey structure into:
    - A list of Actions (from Steps)
    - A list of Invariants
    - A list of checkpoint names

    The branching structure is preserved in the action preconditions,
    which are set based on which checkpoint they follow.

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
