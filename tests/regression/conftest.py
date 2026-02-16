"""Pytest configuration for regression tests."""

import pytest


def pytest_addoption(parser):
    """Add custom options for regression tests."""
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Update golden files with current output"
    )
    parser.addoption(
        "--update-fingerprints",
        action="store_true",
        default=False,
        help="Print current fingerprints for updating"
    )


@pytest.fixture
def update_golden(request):
    """Fixture to check if --update-golden flag is set."""
    return request.config.getoption("--update-golden")


@pytest.fixture
def update_fingerprints(request):
    """Check if --update-fingerprints flag is set."""
    return request.config.getoption("--update-fingerprints")
