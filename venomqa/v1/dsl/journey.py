"""Journey DSL objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.v1.core.action import ActionResult
    from venomqa.v1.core.invariant import Invariant


@dataclass
class Step:
    """A single action in a journey."""

    name: str
    action: Callable[..., "ActionResult"]
    description: str = ""

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class Checkpoint:
    """A named savepoint in a journey.

    Not to be confused with world/checkpoint.py which is the
    actual checkpoint implementation. This is a DSL marker.
    """

    name: str

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class Path:
    """A sequence of steps in a branch."""

    name: str
    steps: list[Step | Checkpoint] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class Branch:
    """A fork from a checkpoint into multiple paths."""

    from_checkpoint: str
    paths: list[Path] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash((self.from_checkpoint, tuple(p.name for p in self.paths)))


@dataclass
class Journey:
    """A user-friendly flow definition.

    Example:
        journey = Journey(
            name="checkout_flow",
            steps=[
                Step("login", login_action),
                Checkpoint("logged_in"),
                Step("add_to_cart", add_action),
                Checkpoint("cart_ready"),
                Branch(
                    from_checkpoint="cart_ready",
                    paths=[
                        Path("buy", [Step("checkout", checkout_action)]),
                        Path("abandon", [Step("clear", clear_action)]),
                    ],
                ),
            ],
            invariants=[order_invariant],
        )
    """

    name: str
    steps: list[Step | Checkpoint | Branch] = field(default_factory=list)
    invariants: list["Invariant"] = field(default_factory=list)
    description: str = ""

    def __hash__(self) -> int:
        return hash(self.name)

    def get_checkpoints(self) -> list[str]:
        """Get all checkpoint names in the journey."""
        names = []
        for item in self.steps:
            if isinstance(item, Checkpoint):
                names.append(item.name)
        return names

    def get_branches(self) -> list[Branch]:
        """Get all branches in the journey."""
        return [item for item in self.steps if isinstance(item, Branch)]

    def get_steps(self) -> list[Step]:
        """Get all steps (flattened from branches)."""
        steps = []
        for item in self.steps:
            if isinstance(item, Step):
                steps.append(item)
            elif isinstance(item, Branch):
                for path in item.paths:
                    for step in path.steps:
                        if isinstance(step, Step):
                            steps.append(step)
        return steps
