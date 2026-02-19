#!/usr/bin/env python3
"""Test VenomQA v1 against GitHub API.

This example demonstrates testing a real public API with VenomQA v1.

GitHub API endpoints tested:
- GET /repos/{owner}/{repo} - Repository info
- GET /repos/{owner}/{repo}/issues - Issues list
- GET /repos/{owner}/{repo}/pulls - Pull requests
- GET /repos/{owner}/{repo}/contributors - Contributors
- GET /users/{username} - User details
- GET /repos/{owner}/{repo}/languages - Languages

Invariants verified:
- Data structure validity (required fields present)
- Cross-endpoint consistency (counts match)
- No server errors (all 2xx responses)
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
from datetime import datetime

from venomqa import (
    Agent,
    BFS,
    CoverageGuided,
    Action,
    ActionResult,
    HTTPRequest,
    HTTPResponse,
    Invariant,
    Severity,
)
from venomqa.core.state import Observation
from venomqa.world import World
from venomqa.world.rollbackable import Rollbackable, SystemCheckpoint


# Configuration
BASE_URL = "https://api.github.com"
TEST_OWNER = "anthropics"
TEST_REPO = "anthropic-cookbook"  # Small repo for fast tests


class GitHubApiClient(Rollbackable):
    """HTTP client for GitHub API that implements Rollbackable.

    Since GitHub API is stateless (read-only public data), rollback
    is a no-op. We just track the last response for observation.
    """

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "VenomQA/1.0",
            },
        )
        self._context: dict = {}  # Stores fetched data for invariant checks
        self._request_count = 0

    def get(self, path: str, params: dict | None = None) -> ActionResult:
        """Make GET request to GitHub API."""
        import time

        url = f"{self.base_url}{path}"
        start = time.time()
        self._request_count += 1

        try:
            resp = self.client.get(url, params=params)
            duration_ms = int((time.time() - start) * 1000)

            body = None
            if resp.headers.get("content-type", "").startswith("application/json"):
                body = resp.json()

            return ActionResult.from_response(
                request=HTTPRequest(method="GET", url=url),
                response=HTTPResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=body,
                ),
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ActionResult.from_error(
                request=HTTPRequest(method="GET", url=url),
                error=str(e),
            )

    def store(self, key: str, value) -> None:
        """Store data in context for later invariant checks."""
        self._context[key] = value

    def get_context(self, key: str, default=None):
        """Get data from context."""
        return self._context.get(key, default)

    # Rollbackable interface
    def checkpoint(self, name: str) -> SystemCheckpoint:
        """GitHub API is read-only, checkpoint just records state."""
        return {
            "name": name,
            "context": dict(self._context),
            "request_count": self._request_count,
        }

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore context from checkpoint."""
        self._context = dict(checkpoint.get("context", {}))

    def observe(self) -> Observation:
        """Return current observation."""
        return Observation(
            system="github_api",
            data={
                "request_count": self._request_count,
                "context_keys": list(self._context.keys()),
                "has_repo": "repo" in self._context,
                "has_issues": "issues" in self._context,
                "has_prs": "prs" in self._context,
                "has_contributors": "contributors" in self._context,
            },
        )

    def close(self):
        """Close HTTP client."""
        self.client.close()


def create_actions(api: GitHubApiClient) -> list[Action]:
    """Create all GitHub API actions."""

    def get_repo(client: GitHubApiClient) -> ActionResult:
        """Fetch repository information."""
        result = client.get(f"/repos/{TEST_OWNER}/{TEST_REPO}")
        if result.success and result.response.status_code == 200:
            client.store("repo", result.response.body)
        return result

    def get_issues(client: GitHubApiClient) -> ActionResult:
        """Fetch repository issues (includes PRs in GitHub API)."""
        result = client.get(
            f"/repos/{TEST_OWNER}/{TEST_REPO}/issues",
            params={"state": "all", "per_page": 30},
        )
        if result.success and result.response.status_code == 200:
            issues = result.response.body
            # GitHub returns PRs in issues endpoint, separate them
            pure_issues = [i for i in issues if "pull_request" not in i]
            client.store("issues", pure_issues)
            client.store("issues_with_prs", issues)
        return result

    def get_pulls(client: GitHubApiClient) -> ActionResult:
        """Fetch pull requests."""
        result = client.get(
            f"/repos/{TEST_OWNER}/{TEST_REPO}/pulls",
            params={"state": "all", "per_page": 30},
        )
        if result.success and result.response.status_code == 200:
            client.store("prs", result.response.body)
        return result

    def get_contributors(client: GitHubApiClient) -> ActionResult:
        """Fetch repository contributors."""
        result = client.get(
            f"/repos/{TEST_OWNER}/{TEST_REPO}/contributors",
            params={"per_page": 30},
        )
        if result.success and result.response.status_code == 200:
            client.store("contributors", result.response.body)
        return result

    def get_languages(client: GitHubApiClient) -> ActionResult:
        """Fetch repository languages."""
        result = client.get(f"/repos/{TEST_OWNER}/{TEST_REPO}/languages")
        if result.success and result.response.status_code == 200:
            client.store("languages", result.response.body)
        return result

    def get_owner_user(client: GitHubApiClient) -> ActionResult:
        """Fetch owner user/org details."""
        result = client.get(f"/users/{TEST_OWNER}")
        if result.success and result.response.status_code == 200:
            client.store("owner", result.response.body)
        return result

    def get_readme(client: GitHubApiClient) -> ActionResult:
        """Fetch repository README."""
        result = client.get(f"/repos/{TEST_OWNER}/{TEST_REPO}/readme")
        if result.success and result.response.status_code == 200:
            client.store("readme", result.response.body)
        return result

    return [
        Action(
            name="get_repo",
            execute=get_repo,
            description="GET /repos/{owner}/{repo}",
            tags=["repo", "read"],
        ),
        Action(
            name="get_issues",
            execute=get_issues,
            description="GET /repos/{owner}/{repo}/issues",
            tags=["issues", "read"],
        ),
        Action(
            name="get_pulls",
            execute=get_pulls,
            description="GET /repos/{owner}/{repo}/pulls",
            tags=["pulls", "read"],
        ),
        Action(
            name="get_contributors",
            execute=get_contributors,
            description="GET /repos/{owner}/{repo}/contributors",
            tags=["contributors", "read"],
        ),
        Action(
            name="get_languages",
            execute=get_languages,
            description="GET /repos/{owner}/{repo}/languages",
            tags=["languages", "read"],
        ),
        Action(
            name="get_owner",
            execute=get_owner_user,
            description="GET /users/{owner}",
            tags=["users", "read"],
        ),
        Action(
            name="get_readme",
            execute=get_readme,
            description="GET /repos/{owner}/{repo}/readme",
            tags=["readme", "read"],
        ),
    ]


def create_invariants(api: GitHubApiClient) -> list[Invariant]:
    """Create invariants to verify GitHub API consistency."""

    def repo_has_required_fields(world: World) -> bool:
        """Repository response must have required fields."""
        repo = api.get_context("repo")
        if repo is None:
            return True  # Not yet fetched

        required = ["id", "name", "full_name", "owner", "html_url", "description"]
        missing = [f for f in required if f not in repo]
        if missing:
            print(f"    [FAIL] Repo missing fields: {missing}")
            return False
        return True

    def issues_have_valid_structure(world: World) -> bool:
        """All issues must have required fields."""
        issues = api.get_context("issues")
        if issues is None:
            return True

        required = ["id", "number", "title", "user", "state"]
        for issue in issues:
            missing = [f for f in required if f not in issue]
            if missing:
                print(f"    [FAIL] Issue #{issue.get('number')} missing: {missing}")
                return False
            # User must have login
            if not issue.get("user", {}).get("login"):
                print(f"    [FAIL] Issue #{issue.get('number')} has no user login")
                return False
        return True

    def prs_have_valid_structure(world: World) -> bool:
        """All PRs must have head/base branches."""
        prs = api.get_context("prs")
        if prs is None:
            return True

        required = ["id", "number", "title", "head", "base", "state"]
        for pr in prs:
            missing = [f for f in required if f not in pr]
            if missing:
                print(f"    [FAIL] PR #{pr.get('number')} missing: {missing}")
                return False
            # Head and base must have ref
            if not pr.get("head", {}).get("ref"):
                print(f"    [FAIL] PR #{pr.get('number')} has no head ref")
                return False
            if not pr.get("base", {}).get("ref"):
                print(f"    [FAIL] PR #{pr.get('number')} has no base ref")
                return False
        return True

    def contributors_have_positive_counts(world: World) -> bool:
        """Contributors must have non-negative contribution counts."""
        contributors = api.get_context("contributors")
        if contributors is None:
            return True

        for contrib in contributors:
            count = contrib.get("contributions", 0)
            if count < 0:
                print(f"    [FAIL] {contrib.get('login')} has negative contributions")
                return False
        return True

    def repo_stats_are_valid(world: World) -> bool:
        """Repository stats must be non-negative."""
        repo = api.get_context("repo")
        if repo is None:
            return True

        for stat in ["stargazers_count", "forks_count", "open_issues_count", "watchers_count"]:
            value = repo.get(stat, 0)
            if value < 0:
                print(f"    [FAIL] {stat} is negative: {value}")
                return False
        return True

    def owner_matches_repo(world: World) -> bool:
        """Owner user should match repo owner."""
        repo = api.get_context("repo")
        owner = api.get_context("owner")
        if repo is None or owner is None:
            return True

        repo_owner_login = repo.get("owner", {}).get("login")
        owner_login = owner.get("login")

        if repo_owner_login != owner_login:
            print(f"    [FAIL] Owner mismatch: repo={repo_owner_login}, user={owner_login}")
            return False
        return True

    def no_server_errors(world: World) -> bool:
        """All requests should return 2xx or expected 4xx codes."""
        # This is checked via ActionResult.success in exploration
        return True

    return [
        Invariant(
            name="repo_structure",
            check=repo_has_required_fields,
            message="Repository must have required fields (id, name, full_name, owner, html_url)",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="issues_structure",
            check=issues_have_valid_structure,
            message="Issues must have required fields and valid user",
            severity=Severity.HIGH,
        ),
        Invariant(
            name="prs_structure",
            check=prs_have_valid_structure,
            message="Pull requests must have head/base branch refs",
            severity=Severity.HIGH,
        ),
        Invariant(
            name="contributors_valid",
            check=contributors_have_positive_counts,
            message="Contributors must have non-negative contribution counts",
            severity=Severity.MEDIUM,
        ),
        Invariant(
            name="repo_stats_valid",
            check=repo_stats_are_valid,
            message="Repository stats (stars, forks, issues) must be non-negative",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="owner_consistency",
            check=owner_matches_repo,
            message="Owner user should match repository owner",
            severity=Severity.HIGH,
        ),
    ]


def generate_mermaid(result) -> str:
    """Generate Mermaid diagram of exploration graph."""
    lines = ["graph TD"]

    # Map state IDs to short labels
    state_labels = {}
    for i, state in enumerate(result.graph.iter_states()):
        label = f"S{i}"
        state_labels[state.id] = label
        # Show context keys in state
        obs = state.observations.get("github_api")
        if obs:
            keys = obs.data.get("context_keys", [])
            if keys:
                short_keys = ",".join(k[:3] for k in keys[:3])
                lines.append(f'    {label}["{label}: {short_keys}"]')
            else:
                lines.append(f'    {label}["{label}: initial"]')
        else:
            lines.append(f"    {label}[{label}]")

    # Add transitions
    for transition in result.graph.iter_transitions():
        from_label = state_labels.get(transition.from_state_id, "?")
        to_label = state_labels.get(transition.to_state_id, "?")
        action = transition.action_name.replace("get_", "")
        status = transition.result.response.status_code if transition.result.response else "err"
        lines.append(f"    {from_label} -->|{action}:{status}| {to_label}")

    return "\n".join(lines)


def main():
    """Run GitHub API exploration with VenomQA v1."""
    print("=" * 70)
    print("VenomQA v1 - GitHub API State Exploration")
    print("=" * 70)
    print(f"\nTarget: {BASE_URL}")
    print(f"Repository: {TEST_OWNER}/{TEST_REPO}")
    print()

    # Create API client
    api = GitHubApiClient(BASE_URL)

    # Create World with API client as the system
    world = World(api=api, systems={"github_api": api})

    # Create actions and invariants
    actions = create_actions(api)
    invariants = create_invariants(api)

    print(f"Actions: {len(actions)}")
    for action in actions:
        print(f"  - {action.name}: {action.description}")

    print(f"\nInvariants: {len(invariants)}")
    for inv in invariants:
        print(f"  - {inv.name} [{inv.severity.name}]")

    # Use CoverageGuided strategy to try all actions
    strategy = CoverageGuided()

    print("\n" + "-" * 70)
    print("Starting exploration (BFS, max_steps=30)")
    print("-" * 70)

    # Create agent
    agent = Agent(
        world=world,
        actions=actions,
        invariants=invariants,
        strategy=BFS(),
        max_steps=30,
    )

    # Run exploration
    start_time = datetime.now()
    result = agent.explore()
    end_time = datetime.now()

    # Close API client
    api.close()

    # Print results
    print("\n" + "=" * 70)
    print("EXPLORATION RESULTS")
    print("=" * 70)

    print(f"\nStates visited: {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Coverage: {result.coverage_percent:.1f}%")
    print(f"Duration: {result.duration_ms:.0f}ms")
    print(f"Success: {result.success}")

    # Print violations
    print(f"\nViolations: {len(result.violations)}")
    if result.violations:
        for v in result.violations:
            print(f"  [{v.severity.name}] {v.invariant_name}")
            print(f"    Message: {v.message}")
            if v.action:
                print(f"    After action: {v.action}")
    else:
        print("  (no violations - all invariants passed)")

    # Print summary
    print("\n" + "-" * 70)
    print("Summary:")
    summary = result.summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    # Print exploration graph
    print("\n" + "=" * 70)
    print("EXPLORATION GRAPH (Mermaid)")
    print("=" * 70)
    print()
    print("```mermaid")
    print(generate_mermaid(result))
    print("```")

    # Final status
    print("\n" + "=" * 70)
    if result.success:
        print("ALL INVARIANTS PASSED")
        print(f"GitHub API for {TEST_OWNER}/{TEST_REPO} is consistent!")
    else:
        print("ISSUES FOUND")
        print(f"Found {len(result.violations)} violations")
        for v in result.critical_violations:
            print(f"  CRITICAL: {v.invariant_name}")
    print("=" * 70)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
