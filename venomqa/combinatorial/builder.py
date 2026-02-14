"""State graph builder from combinatorial dimensions.

This module bridges the combinatorial system with VenomQA's StateGraph.
It auto-generates StateNodes from dimension combinations and creates
Edges for transitions between states that differ in exactly one dimension.

The builder uses composition -- it creates a StateGraph instance and
populates it, rather than subclassing StateGraph. This maintains full
backward compatibility with the existing graph system.

Example:
    >>> from venomqa.combinatorial import (
    ...     Dimension, DimensionSpace, ConstraintSet,
    ...     CoveringArrayGenerator, CombinatorialGraphBuilder,
    ... )
    >>> from venomqa.core.graph import StateGraph
    >>>
    >>> space = DimensionSpace([
    ...     Dimension("auth", ["anon", "user", "admin"]),
    ...     Dimension("count", [0, 1, "many"]),
    ... ])
    >>>
    >>> builder = CombinatorialGraphBuilder(
    ...     name="api_test",
    ...     space=space,
    ...     constraints=ConstraintSet(),
    ... )
    >>>
    >>> # Register transition actions for each dimension
    >>> builder.register_transition("auth", "anon", "user", action=login_as_user)
    >>> builder.register_transition("auth", "user", "admin", action=elevate_to_admin)
    >>> builder.register_transition("count", 0, 1, action=create_item)
    >>>
    >>> # Build the StateGraph
    >>> graph = builder.build(strength=2)  # Pairwise coverage
    >>> result = graph.explore(client, db)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Hashable

from venomqa.combinatorial.constraints import ConstraintSet
from venomqa.combinatorial.dimensions import Combination, DimensionSpace
from venomqa.combinatorial.generator import CoveringArrayGenerator
from venomqa.core.graph import (
    ActionCallable,
    Edge,
    Invariant,
    InvariantChecker,
    Severity,
    StateChecker,
    StateGraph,
    StateNode,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitionKey:
    """Key identifying a specific value transition within a dimension.

    Attributes:
        dimension: The dimension being changed.
        from_value: The starting value.
        to_value: The target value.
    """

    dimension: str
    from_value: Hashable
    to_value: Hashable


@dataclass
class TransitionAction:
    """An action that transitions one dimension from one value to another.

    Attributes:
        key: The transition being performed.
        action: The callable that executes the transition.
        name: Human-readable name for this transition.
        description: Extended description.
        setup_required: If True, additional setup is needed before this
            transition can execute.
    """

    key: TransitionKey
    action: ActionCallable
    name: str = ""
    description: str = ""
    setup_required: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            self.name = (
                f"{self.key.dimension}_"
                f"{self.key.from_value}_to_{self.key.to_value}"
            )


@dataclass
class StateSetup:
    """Configuration for setting up a specific dimension-value state.

    When the graph explorer needs to reach a certain combination,
    StateSetup defines how to get there.

    Attributes:
        dimension: The dimension this setup applies to.
        value: The target value.
        action: Callable to set up this state.
        description: What this setup does.
    """

    dimension: str
    value: Hashable
    action: ActionCallable
    description: str = ""


class CombinatorialGraphBuilder:
    """Builds a StateGraph from combinatorial dimension definitions.

    This builder:
    1. Takes dimension definitions and constraints.
    2. Generates combinations (pairwise or other strengths).
    3. Creates StateNodes for each combination.
    4. Creates Edges between nodes that differ by one dimension.
    5. Attaches invariants.

    The resulting StateGraph can be explored using the standard
    StateGraph.explore() method.

    Attributes:
        name: Name for the generated StateGraph.
        space: The dimension space.
        constraints: Constraints for filtering invalid combinations.
        description: Description for the StateGraph.

    Example:
        >>> builder = CombinatorialGraphBuilder(
        ...     name="api_combinatorial",
        ...     space=space,
        ...     constraints=constraints,
        ... )
        >>>
        >>> builder.register_transition("auth", "anon", "user", action=login)
        >>> builder.register_transition("count", 0, 1, action=create_item)
        >>>
        >>> # Add invariant
        >>> builder.add_invariant("api_db_match", check=check_counts_match)
        >>>
        >>> graph = builder.build(strength=2)
    """

    def __init__(
        self,
        name: str,
        space: DimensionSpace,
        constraints: ConstraintSet | None = None,
        description: str = "",
        seed: int | None = None,
    ) -> None:
        self.name = name
        self.space = space
        self.constraints = constraints or ConstraintSet()
        self.description = description
        self.seed = seed

        self._transitions: dict[TransitionKey, TransitionAction] = {}
        self._state_setups: dict[tuple[str, Hashable], StateSetup] = {}
        self._state_checkers: dict[tuple[str, Hashable], StateChecker] = {}
        self._invariants: list[tuple[str, InvariantChecker, str, Severity]] = []
        self._initial_combination: Combination | None = None
        self._node_entry_actions: dict[str, list[ActionCallable]] = {}

    def register_transition(
        self,
        dimension: str,
        from_value: Hashable,
        to_value: Hashable,
        action: ActionCallable,
        name: str = "",
        description: str = "",
    ) -> TransitionAction:
        """Register an action for transitioning between dimension values.

        Args:
            dimension: The dimension being changed.
            from_value: The starting value.
            to_value: The target value.
            action: Callable(client, context) that performs the transition.
            name: Optional human-readable name.
            description: Optional description.

        Returns:
            The created TransitionAction.

        Raises:
            ValueError: If dimension or values are invalid.
        """
        dim = self.space.get_dimension(dimension)
        if from_value not in dim.values:
            raise ValueError(
                f"Value '{from_value}' not in dimension '{dimension}'. "
                f"Valid values: {dim.values}"
            )
        if to_value not in dim.values:
            raise ValueError(
                f"Value '{to_value}' not in dimension '{dimension}'. "
                f"Valid values: {dim.values}"
            )

        key = TransitionKey(dimension, from_value, to_value)
        trans = TransitionAction(
            key=key,
            action=action,
            name=name,
            description=description,
        )
        self._transitions[key] = trans

        logger.debug(f"Registered transition: {dimension} {from_value} -> {to_value}")
        return trans

    def register_setup(
        self,
        dimension: str,
        value: Hashable,
        action: ActionCallable,
        description: str = "",
    ) -> StateSetup:
        """Register a setup action for a specific dimension value.

        Setup actions prepare the system to be in a specific state.
        They are used as entry_actions on StateNodes.

        Args:
            dimension: The dimension this setup applies to.
            value: The value to set up.
            action: Callable to execute the setup.
            description: What this setup does.

        Returns:
            The created StateSetup.
        """
        dim = self.space.get_dimension(dimension)
        if value not in dim.values:
            raise ValueError(
                f"Value '{value}' not in dimension '{dimension}'. "
                f"Valid values: {dim.values}"
            )

        setup = StateSetup(
            dimension=dimension,
            value=value,
            action=action,
            description=description,
        )
        self._state_setups[(dimension, value)] = setup
        return setup

    def register_checker(
        self,
        dimension: str,
        value: Hashable,
        checker: StateChecker,
    ) -> None:
        """Register a state checker for a specific dimension value.

        State checkers verify the system is in the expected state.
        They are combined for multi-dimension nodes.

        Args:
            dimension: The dimension this checker applies to.
            value: The value this checker verifies.
            checker: Callable(client, db, context) -> bool.
        """
        dim = self.space.get_dimension(dimension)
        if value not in dim.values:
            raise ValueError(
                f"Value '{value}' not in dimension '{dimension}'. "
                f"Valid values: {dim.values}"
            )

        self._state_checkers[(dimension, value)] = checker

    def add_invariant(
        self,
        name: str,
        check: InvariantChecker,
        description: str = "",
        severity: Severity = Severity.HIGH,
    ) -> None:
        """Add an invariant to be checked at every state.

        Args:
            name: Unique invariant name.
            check: Callable(client, db, context) -> bool.
            description: What this invariant checks.
            severity: How critical a violation is.
        """
        self._invariants.append((name, check, description, severity))

    def set_initial(self, combination: Combination | dict[str, Hashable]) -> None:
        """Set the initial combination (starting state for exploration).

        Args:
            combination: The starting combination or dict of values.
        """
        if isinstance(combination, dict):
            combination = Combination(combination)

        # Validate all dimensions are present
        for dim in self.space.dimensions:
            if dim.name not in combination.values:
                raise ValueError(
                    f"Initial combination missing dimension '{dim.name}'"
                )

        if not self.constraints.is_valid(combination):
            raise ValueError(
                f"Initial combination {combination} violates constraints"
            )

        self._initial_combination = combination

    def build(
        self,
        strength: int = 2,
        combinations: list[Combination] | None = None,
    ) -> StateGraph:
        """Build a StateGraph from the combinatorial specification.

        Args:
            strength: The t-wise coverage strength (default: 2 for pairwise).
                Ignored if combinations are provided explicitly.
            combinations: Optional explicit list of combinations to use.
                If None, generates combinations using the specified strength.

        Returns:
            A fully constructed StateGraph ready for exploration.
        """
        # Generate or use provided combinations
        if combinations is not None:
            combos = self.constraints.filter(combinations)
        else:
            gen = CoveringArrayGenerator(
                self.space, self.constraints, seed=self.seed
            )
            # Cap strength at the number of dimensions
            effective_strength = min(strength, len(self.space.dimensions))
            combos = gen.generate(strength=effective_strength)

        if not combos:
            raise ValueError(
                "No valid combinations generated. Check constraints "
                "are not over-constrained."
            )

        logger.info(
            f"Building StateGraph '{self.name}' with {len(combos)} nodes"
        )

        # Build the graph
        graph = StateGraph(
            name=self.name,
            description=self.description or (
                f"Combinatorial state graph with {len(combos)} states "
                f"({strength}-wise coverage of "
                f"{len(self.space.dimensions)} dimensions)"
            ),
        )

        # Add nodes
        combo_map: dict[str, Combination] = {}
        for combo in combos:
            node_id = combo.node_id
            combo_map[node_id] = combo

            checker = self._build_checker(combo)
            node = graph.add_node(
                node_id=node_id,
                description=combo.description,
                checker=checker,
            )

            # Add entry actions based on state setups
            entry_actions = self._build_entry_actions(combo)
            node.entry_actions = entry_actions

        # Set initial node
        initial_combo = self._resolve_initial(combos)
        graph.set_initial_node(initial_combo.node_id)

        # Add edges between nodes that differ by exactly one dimension
        edge_count = 0
        for i, combo_a in enumerate(combos):
            for j, combo_b in enumerate(combos):
                if i == j:
                    continue

                diff_dim = combo_a.differs_by_one(combo_b)
                if diff_dim is None:
                    continue

                # Look up the transition action
                from_val = combo_a[diff_dim]
                to_val = combo_b[diff_dim]
                key = TransitionKey(diff_dim, from_val, to_val)

                trans = self._transitions.get(key)
                if trans is None:
                    # No registered transition for this value change, skip
                    continue

                edge_name = (
                    f"{diff_dim}_{from_val}_to_{to_val}__"
                    f"from_{combo_a.node_id}__to_{combo_b.node_id}"
                )

                # Wrap the action to inject the combination context
                wrapped_action = self._wrap_action(
                    trans.action, combo_a, combo_b, diff_dim
                )

                graph.add_edge(
                    from_node=combo_a.node_id,
                    to_node=combo_b.node_id,
                    action=wrapped_action,
                    name=edge_name,
                    description=(
                        trans.description or
                        f"Change {diff_dim}: {from_val} -> {to_val}"
                    ),
                )
                edge_count += 1

        # Add invariants
        for inv_name, check, desc, sev in self._invariants:
            graph.add_invariant(
                name=inv_name,
                check=check,
                description=desc,
                severity=sev,
            )

        logger.info(
            f"Built StateGraph: {len(combos)} nodes, {edge_count} edges, "
            f"{len(self._invariants)} invariants"
        )

        return graph

    def build_journey_graph(
        self,
        strength: int = 2,
        combinations: list[Combination] | None = None,
    ) -> tuple[StateGraph, list[Combination]]:
        """Build a StateGraph and return the combinations used.

        Same as build() but also returns the combination list for
        inspection or further analysis.

        Args:
            strength: The t-wise coverage strength.
            combinations: Optional explicit combinations.

        Returns:
            Tuple of (StateGraph, list of Combinations used).
        """
        if combinations is not None:
            combos = self.constraints.filter(combinations)
        else:
            gen = CoveringArrayGenerator(
                self.space, self.constraints, seed=self.seed
            )
            effective_strength = min(strength, len(self.space.dimensions))
            combos = gen.generate(strength=effective_strength)

        graph = self.build(strength=strength, combinations=combos)
        return graph, combos

    def _build_checker(self, combo: Combination) -> StateChecker | None:
        """Build a composite state checker for a combination.

        Combines individual dimension-value checkers into one function
        that verifies all dimensions simultaneously.
        """
        checkers: list[tuple[str, Hashable, StateChecker]] = []

        for dim_name, value in combo.values.items():
            key = (dim_name, value)
            if key in self._state_checkers:
                checkers.append((dim_name, value, self._state_checkers[key]))

        if not checkers:
            return None

        def combined_checker(
            client: Any, db: Any, context: dict[str, Any]
        ) -> bool:
            # Inject combination info into context
            context["_current_combination"] = combo.to_dict()

            for dim_name, value, checker in checkers:
                if not checker(client, db, context):
                    logger.debug(
                        f"State check failed: {dim_name}={value} "
                        f"at combination {combo.description}"
                    )
                    return False
            return True

        return combined_checker

    def _build_entry_actions(self, combo: Combination) -> list[ActionCallable]:
        """Build entry actions for a combination node."""
        actions: list[ActionCallable] = []

        for dim_name, value in sorted(combo.values.items()):
            key = (dim_name, value)
            if key in self._state_setups:
                actions.append(self._state_setups[key].action)

        return actions

    def _resolve_initial(self, combos: list[Combination]) -> Combination:
        """Resolve the initial combination for graph exploration.

        Uses the explicitly set initial if available, otherwise uses
        the first combination that uses default dimension values.
        """
        if self._initial_combination is not None:
            # Check it's in the combos list
            if self._initial_combination in combos:
                return self._initial_combination

            # If the exact initial is not in the generated set,
            # find the closest match
            best_match = combos[0]
            best_score = 0
            for combo in combos:
                score = sum(
                    1 for k, v in combo.values.items()
                    if self._initial_combination.values.get(k) == v
                )
                if score > best_score:
                    best_score = score
                    best_match = combo

            logger.warning(
                f"Exact initial combination not in generated set. "
                f"Using closest match: {best_match.description}"
            )
            return best_match

        # Use the default combination (first value of each dimension)
        default = self.space.default_combination()
        for combo in combos:
            if combo == default:
                return combo

        # Default not in set, use first combo
        return combos[0]

    def _wrap_action(
        self,
        action: ActionCallable,
        from_combo: Combination,
        to_combo: Combination,
        changed_dim: str,
    ) -> ActionCallable:
        """Wrap a transition action to inject combination context.

        The wrapper injects metadata about the current transition into
        the context dict so actions can reference the full state.
        """

        def wrapped(client: Any, context: dict[str, Any]) -> Any:
            context["_from_combination"] = from_combo.to_dict()
            context["_to_combination"] = to_combo.to_dict()
            context["_changed_dimension"] = changed_dim
            context["_from_value"] = from_combo[changed_dim]
            context["_to_value"] = to_combo[changed_dim]
            return action(client, context)

        wrapped.__name__ = f"transition_{changed_dim}_{from_combo[changed_dim]}_to_{to_combo[changed_dim]}"
        wrapped.__qualname__ = wrapped.__name__
        return wrapped

    def summary(self, strength: int = 2) -> str:
        """Generate a summary of what would be built.

        Args:
            strength: The coverage strength to analyze.

        Returns:
            Multi-line summary string.
        """
        gen = CoveringArrayGenerator(
            self.space, self.constraints, seed=self.seed
        )
        effective_strength = min(strength, len(self.space.dimensions))
        combos = gen.generate(strength=effective_strength)
        stats = gen.coverage_stats(combos, strength=effective_strength)

        lines = [
            f"Combinatorial Graph Builder: {self.name}",
            "=" * 50,
            "",
            "Dimensions:",
        ]

        for dim in self.space.dimensions:
            lines.append(f"  {dim.name}: {dim.values}")

        lines.extend([
            "",
            f"Constraints: {len(self.constraints)}",
            f"Transitions registered: {len(self._transitions)}",
            f"State setups: {len(self._state_setups)}",
            f"State checkers: {len(self._state_checkers)}",
            f"Invariants: {len(self._invariants)}",
            "",
            f"Coverage (strength={strength}):",
            f"  Total exhaustive combinations: {self.space.total_combinations}",
            f"  Generated test combinations: {stats.test_count}",
            f"  Reduction: {self.space.total_combinations - stats.test_count} "
            f"({(1 - stats.test_count / self.space.total_combinations) * 100:.1f}%)",
            f"  Tuple coverage: {stats.coverage_pct:.1f}%",
            "",
        ])

        # Count potential edges
        edge_count = 0
        for i, a in enumerate(combos):
            for j, b in enumerate(combos):
                if i == j:
                    continue
                diff = a.differs_by_one(b)
                if diff and TransitionKey(diff, a[diff], b[diff]) in self._transitions:
                    edge_count += 1

        lines.append(f"  Potential edges: {edge_count}")

        # Missing transitions
        missing = self._find_missing_transitions()
        if missing:
            lines.extend(["", "Missing transitions:"])
            for key in missing:
                lines.append(
                    f"  {key.dimension}: {key.from_value} -> {key.to_value}"
                )

        return "\n".join(lines)

    def _find_missing_transitions(self) -> list[TransitionKey]:
        """Find value transitions with no registered action.

        Returns transitions between adjacent values in each dimension
        that have no action registered.
        """
        missing: list[TransitionKey] = []

        for dim in self.space.dimensions:
            for i, from_val in enumerate(dim.values):
                for j, to_val in enumerate(dim.values):
                    if i == j:
                        continue
                    key = TransitionKey(dim.name, from_val, to_val)
                    if key not in self._transitions:
                        missing.append(key)

        return missing
