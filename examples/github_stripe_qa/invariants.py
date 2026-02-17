"""VenomQA invariants for the GitHub + Stripe QA exploration.

Each invariant is checked after every action. Violations indicate that
the mock server is behaving incorrectly.

Invariants defined here:

  GitHub invariants
  -----------------
  1. open_issues_never_contain_closed (CRITICAL)
       The list of "open" issues must never include a closed issue.
       Catches BUG: GitHubHandler leaks a closed issue into the open list.

  2. open_issues_count_matches_response (HIGH)
       The repo's open_issues_count field must equal the number of issues
       returned by GET /repos/{id}/issues?state=open.

  3. deleted_repo_returns_404 (CRITICAL)
       After deleting a repo, a GET on its URL must return HTTP 404.

  Stripe invariants
  -----------------
  4. refund_cannot_exceed_payment (CRITICAL)
       A PaymentIntent's refunded_amount must never exceed its original amount.
       Catches BUG: StripeHandler accepts over-refunds without validation.

  5. confirmed_payment_status_is_succeeded (HIGH)
       After confirming a PaymentIntent the status must be "succeeded".

  6. customer_must_exist_for_payment_intent (HIGH)
       Every PaymentIntent with a customer_id must reference a customer that
       still exists (GET /customers/{id} returns 200).
"""

from __future__ import annotations

from venomqa.v1.core.invariant import Invariant, Severity


# ---------------------------------------------------------------------------
# GitHub invariants
# ---------------------------------------------------------------------------

def _check_open_issues_never_contain_closed(world) -> bool:  # type: ignore[no-untyped-def]
    """Listing open issues must never return a closed issue."""
    open_issues = world.context.get("open_issues")
    if not open_issues:
        return True  # No data yet — skip

    closed_in_open = [i for i in open_issues if i.get("state") == "closed"]
    return len(closed_in_open) == 0


open_issues_never_contain_closed = Invariant(
    name="open_issues_never_contain_closed",
    check=_check_open_issues_never_contain_closed,
    message=(
        "GET /repos/{id}/issues?state=open returned issues with state='closed'. "
        "The server's open-issue filter is broken — closed issues are leaking "
        "into the open list."
    ),
    severity=Severity.CRITICAL,
)


def _check_open_issues_count_matches(world) -> bool:  # type: ignore[no-untyped-def]
    """Repo's open_issues_count must equal len(open issues list)."""
    repo_id = world.context.get("repo_id")
    open_issues = world.context.get("open_issues")
    if not repo_id or open_issues is None:
        return True  # Nothing to check yet

    # Re-fetch the repo to get the current count field
    result = world.api.get(f"/repos/{repo_id}")
    if not result.success or result.response.status_code != 200:
        return True  # Can't check — repo may be deleted; skip

    reported_count: int = result.response.body.get("open_issues_count", 0)
    # Strip any closed issues that leaked into the open list (separate concern)
    actual_open = [i for i in open_issues if i.get("state") == "open"]
    return reported_count == len(actual_open)


open_issues_count_matches = Invariant(
    name="open_issues_count_matches_response",
    check=_check_open_issues_count_matches,
    message=(
        "The repo's open_issues_count field does not match the number of "
        "open issues returned by the issues endpoint."
    ),
    severity=Severity.HIGH,
)


def _check_deleted_repo_returns_404(world) -> bool:  # type: ignore[no-untyped-def]
    """After deleting a repo, GET must return 404."""
    deleted_id = world.context.get("deleted_repo_id")
    if not deleted_id:
        return True  # No delete has happened yet

    status = world.context.get("deleted_repo_status")
    # deleted_repo_status is set by the delete_repo action right after deletion
    if status is None:
        return True
    return int(status) == 404


deleted_repo_returns_404 = Invariant(
    name="deleted_repo_returns_404",
    check=_check_deleted_repo_returns_404,
    message=(
        "After DELETE /repos/{id} succeeded, GET /repos/{id} did not return "
        "HTTP 404. The resource is still accessible after deletion."
    ),
    severity=Severity.CRITICAL,
)


# ---------------------------------------------------------------------------
# Stripe invariants
# ---------------------------------------------------------------------------

def _check_refund_cannot_exceed_payment(world) -> bool:  # type: ignore[no-untyped-def]
    """refunded_amount on a PaymentIntent must never exceed its original amount."""
    pi_id = world.context.get("pi_id")
    if not pi_id:
        return True

    stripe = world.context.get("stripe")
    if not stripe:
        return True

    result = stripe.get(f"/payment_intents/{pi_id}")
    if not result.success or result.response.status_code != 200:
        return True  # PI not yet created or already gone

    pi = result.response.body
    amount: int = pi.get("amount", 0)
    refunded: int = pi.get("refunded_amount", 0)
    return refunded <= amount


refund_cannot_exceed_payment = Invariant(
    name="refund_cannot_exceed_payment",
    check=_check_refund_cannot_exceed_payment,
    message=(
        "A PaymentIntent's refunded_amount exceeds its original amount. "
        "The server accepted an over-refund without returning HTTP 400 / "
        "error code 'amount_too_large'. This is a critical billing integrity bug."
    ),
    severity=Severity.CRITICAL,
)


def _check_confirmed_payment_status(world) -> bool:  # type: ignore[no-untyped-def]
    """A confirmed PaymentIntent must have status='succeeded'."""
    pi_data = world.context.get("pi_data")
    if not pi_data:
        return True

    # Only check if the PI has been confirmed (we know because confirm_payment
    # was called, which sets pi_data via get_payment_intent)
    status = pi_data.get("status")
    # If status is set but NOT succeeded, that's a bug
    if status is None:
        return True
    return status == "succeeded"


confirmed_payment_status_is_succeeded = Invariant(
    name="confirmed_payment_status_is_succeeded",
    check=_check_confirmed_payment_status,
    message=(
        "After confirming a PaymentIntent, its status must be 'succeeded'. "
        "The server returned an unexpected status."
    ),
    severity=Severity.HIGH,
)


def _check_customer_exists_for_payment(world) -> bool:  # type: ignore[no-untyped-def]
    """Every PaymentIntent with a customer_id must reference an existing customer."""
    pi_id = world.context.get("pi_id")
    customer_id = world.context.get("customer_id")
    if not pi_id or not customer_id:
        return True

    stripe = world.context.get("stripe")
    if not stripe:
        return True

    result = stripe.get(f"/customers/{customer_id}")
    return result.success and result.response.status_code == 200


customer_must_exist_for_payment = Invariant(
    name="customer_must_exist_for_payment_intent",
    check=_check_customer_exists_for_payment,
    message=(
        "A PaymentIntent references a customer_id that returns 404. "
        "The customer was deleted but the PaymentIntent still references it."
    ),
    severity=Severity.HIGH,
)


# ---------------------------------------------------------------------------
# Exported list
# ---------------------------------------------------------------------------

ALL_INVARIANTS = [
    open_issues_never_contain_closed,
    open_issues_count_matches,
    deleted_repo_returns_404,
    refund_cannot_exceed_payment,
    confirmed_payment_status_is_succeeded,
    customer_must_exist_for_payment,
]
