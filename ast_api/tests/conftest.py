"""Shared setup for the API tests."""

import pytest

import ast_api.main as api_main
from ast_api.auth import AuthenticatedUser


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    """Run each test as a signed-in user, so it can test what its route does.

    The login check itself is tested in test_auth.py, which takes this away.
    """
    monkeypatch.setitem(
        api_main.app.dependency_overrides,
        api_main.require_user,
        lambda: AuthenticatedUser(subject="test-user"),
    )
