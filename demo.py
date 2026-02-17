#!/usr/bin/env python3
"""VenomQA demo script — used for product GIF.

Runs the GitHub + Stripe exploration with a clean banner.
Finds 2 deliberately planted bugs.
"""
from __future__ import annotations

import sys
import os
import time
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "examples/github_stripe_qa"))

from venomqa.v1 import Agent, World
from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.core.action import Action
from venomqa.v1.agent.strategies import BFS
from venomqa.v1.reporters.console import ConsoleReporter

from stripe_proxy import StripeProxy
from api_observers import GitHubObserver, StripeObserver
from mock_github import start_server as start_github, reset_state as reset_github
from mock_stripe import start_server as start_stripe, reset_state as reset_stripe
from actions import (
    create_user, create_repo, list_repos,
    create_issue, list_open_issues, close_issue, delete_repo,
    create_customer, create_payment_intent, confirm_payment,
    create_refund, get_payment_intent,
)
from invariants import ALL_INVARIANTS

GITHUB_PORT = 8103
STRIPE_PORT = 8104

CYAN  = "\033[96m"
GREEN = "\033[92m"
RED   = "\033[91m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"

BANNER = f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════╗
║              VenomQA  —  Autonomous API Testing          ║
║         Find sequence bugs no unit test will catch       ║
╚══════════════════════════════════════════════════════════╝{RESET}
"""

def main():
    print(BANNER)
    time.sleep(0.3)

    print(f"{DIM}  Spinning up in-process mock servers...{RESET}")
    reset_github(); reset_stripe()
    github_server = start_github(GITHUB_PORT)
    stripe_server = start_stripe(STRIPE_PORT)
    time.sleep(0.1)
    print(f"  {GREEN}✓{RESET} GitHub mock  {DIM}http://localhost:{GITHUB_PORT}{RESET}")
    print(f"  {GREEN}✓{RESET} Stripe mock  {DIM}http://localhost:{STRIPE_PORT}{RESET}")
    time.sleep(0.2)

    print(f"\n{DIM}  Actions defined: 12{RESET}")
    print(f"{DIM}  Invariants:       4{RESET}")
    print(f"{DIM}  Strategy:         BFS (breadth-first){RESET}")
    print(f"{DIM}  Max steps:        60{RESET}")

    print(f"\n  {CYAN}Exploring every reachable action sequence...{RESET}\n")
    time.sleep(0.2)

    github_api = HttpClient(f"http://localhost:{GITHUB_PORT}")
    stripe_api = StripeProxy(f"http://localhost:{STRIPE_PORT}")

    world = World(
        api=github_api,
        systems={"github": GitHubObserver(), "stripe_obs": StripeObserver()},
    )
    world.context.set("stripe", stripe_api)

    actions = [
        Action(name="create_user",           execute=create_user,           tags=["github"]),
        Action(name="create_repo",           execute=create_repo,           tags=["github"]),
        Action(name="list_repos",            execute=list_repos,            tags=["github"]),
        Action(name="create_issue",          execute=create_issue,          tags=["github"]),
        Action(name="list_open_issues",      execute=list_open_issues,      tags=["github"]),
        Action(name="close_issue",           execute=close_issue,           tags=["github"]),
        Action(name="delete_repo",           execute=delete_repo,           tags=["github"]),
        Action(name="create_customer",       execute=create_customer,       tags=["stripe"]),
        Action(name="create_payment_intent", execute=create_payment_intent, tags=["stripe"]),
        Action(name="confirm_payment",       execute=confirm_payment,       tags=["stripe"]),
        Action(name="create_refund",         execute=create_refund,         tags=["stripe"]),
        Action(name="get_payment_intent",    execute=get_payment_intent,    tags=["stripe"]),
    ]

    agent = Agent(
        world=world,
        actions=actions,
        invariants=ALL_INVARIANTS,
        strategy=BFS(),
        max_steps=60,
    )

    result = agent.explore()

    github_server.shutdown(); stripe_server.shutdown()
    github_api.close(); stripe_api.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"  States explored   : {BOLD}{result.states_visited}{RESET}")
    print(f"  Transitions taken : {result.transitions_taken}")
    print(f"  Action coverage   : {BOLD}{result.action_coverage_percent:.0f}%{RESET}  (12/12 actions reached)")
    print(f"  Duration          : {result.duration_ms:.0f} ms")

    unique = {}
    for v in result.violations:
        unique.setdefault(v.invariant_name, v)

    print(f"\n  {RED}{BOLD}Violations found: {len(unique)}{RESET}\n")

    for v in unique.values():
        sev = v.severity.value.upper()
        print(f"  {RED}{BOLD}[{sev}]{RESET} {BOLD}{v.invariant_name}{RESET}")
        # wrap message at 60 chars
        msg = v.message
        words = msg.split()
        line = "    "
        for w in words:
            if len(line) + len(w) + 1 > 64:
                print(f"{DIM}{line}{RESET}")
                line = "    " + w + " "
            else:
                line += w + " "
        if line.strip():
            print(f"{DIM}{line}{RESET}")
        if hasattr(v, 'reproduction_path') and v.reproduction_path:
            path = " → ".join(v.reproduction_path)
            print(f"    {DIM}Path: {path}{RESET}")
        print()

    print(f"  {DIM}Run venomqa replay to step through the exact sequence.{RESET}")
    print(f"\n{CYAN}{BOLD}  docs: https://namanag97.github.io/venomqa{RESET}\n")


if __name__ == "__main__":
    main()
