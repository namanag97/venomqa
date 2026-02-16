"""Agent module - the explorer.

Agent explores the state space by:
1. Observing current state
2. Picking next action via Strategy
3. Executing action via World
4. Recording transition in Graph
5. Checking invariants
6. Repeating until done
"""

from venomqa.v1.agent.strategies import Strategy, BFS, DFS, Random

__all__ = [
    "Agent",
    "Strategy",
    "BFS",
    "DFS",
    "Random",
]

# TODO: Implement Agent class in Task #12
class Agent:
    """The state space explorer."""
    pass
