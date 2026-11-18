"""
Tests for the login check: which tokens are accepted, and that every route asks
for one.

No login service is needed. The tests make their own signing key, sign tokens
with it the way Keycloak does, and hand the verifier the matching public key.
"""

import sqlite3
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import ast_api.database as database
import ast_api.main as api_main
from ast_api.auth import AuthenticatedUser, KeyServiceError, TokenError, TokenVerifier
from ast_api.tests.fakes import FakeRedis

pytestmark = pytest.mark.unit

ISSUER = "https://login.example/auth/realms/standard"
AUDIENCE = "automated-status-tool"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(signing_key) -> TokenVerifier:
    return TokenVerifier(ISSUER, AUDIENCE, signing_key_for=lambda token: signing_key.public_key())


def _token(key, algorithm="RS256", **changes) -> str:
    """An access token as the login service issues one, with any claims changed.

    A claim changed to None is left out of the token.
    """
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "typ": "Bearer",
        "exp": int(time.time()) + 300,
    }
    claims.update(changes)
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key, algorithm=algorithm)


def test_a_token_from_the_login_service_names_its_user(verifier, signing_key):
    assert verifier.verify(_token(signing_key)) == AuthenticatedUser(subject="user-123")


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": int(time.time()) - 60},
        {"iss": "https://somewhere.else/auth/realms/standard"},
        {"aud": "another-application"},
        {"typ": "ID"},
        {"exp": None},
        {"sub": None},
        {"aud": None},
    ],
    ids=["expired", "other issuer", "other application", "id token", "no expiry", "no subject", "no audience"],
)
def test_a_token_with_the_wrong_claims_is_refused(verifier, signing_key, changes):
    with pytest.raises(TokenError):
        verifier.verify(_token(signing_key, **changes))


def test_a_token_signed_with_another_key_is_refused(verifier):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(TokenError):
        verifier.verify(_token(other_key))


def test_a_token_cannot_choose_a_weaker_signature_for_itself(verifier):
    """A token signed with a shared secret, or not signed, is not checked that way."""
    with pytest.raises(TokenError):
        verifier.verify(_token("a-shared-secret-that-is-long-enough-for-hs256", algorithm="HS256"))
    with pytest.raises(TokenError):
        verifier.verify(_token(None, algorithm="none"))


def test_text_that_is_not_a_token_is_refused(verifier):
    with pytest.raises(TokenError):
        verifier.verify("not-a-token")


def test_keys_that_cannot_be_fetched_are_not_reported_as_a_bad_token(signing_key):
    def unreachable(token):
        raise jwt.PyJWKClientConnectionError("connection refused")

    verifier = TokenVerifier(ISSUER, AUDIENCE, signing_key_for=unreachable)

    with pytest.raises(KeyServiceError):
        verifier.verify(_token(signing_key))


def test_the_keys_are_looked_for_under_the_issuer_unless_told_otherwise(monkeypatch):
    asked = []
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url, **options: asked.append(url))

    TokenVerifier(ISSUER + "/", AUDIENCE)
    TokenVerifier(ISSUER, AUDIENCE, jwks_url="https://keys.example/certs")

    assert asked == [ISSUER + "/protocol/openid-connect/certs", "https://keys.example/certs"]


# --- the routes ---------------------------------------------------------------

# One of each kind of route. The job id does not need to exist: the login check
# comes before anything is looked up.
ROUTES = [
    ("POST", "/api/jobs"),
    ("GET", "/api/jobs"),
    ("GET", "/api/jobs/some-job"),
    ("GET", "/api/jobs/some-job/results"),
    ("GET", "/api/jobs/some-job/report"),
    ("GET", "/api/jobs/some-job/maps"),
    ("GET", "/api/jobs/some-job/maps/overview"),
    ("GET", "/api/debug/queue"),
    ("GET", "/api/results"),
    ("GET", "/jobs"),
]


@pytest.fixture
def client(monkeypatch, tmp_path, verifier):
    """The API with the login check on, checking against the tests' own key."""
    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(database, "create_connection", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(api_main, "redis_client", FakeRedis())
    monkeypatch.setattr(api_main.settings, "auth_required", True)
    # The other API tests run signed in as a stand-in user; these ones do not.
    monkeypatch.delitem(api_main.app.dependency_overrides, api_main.require_user, raising=False)
    monkeypatch.setitem(api_main.app.dependency_overrides, api_main.get_token_verifier, lambda: verifier)
    with TestClient(api_main.app) as test_client:
        yield test_client


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_route_refuses_a_request_with_no_token(client, method, path):
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_no_route_is_left_without_the_login_check():
    """ROUTES above covers every route the API has, so a new one cannot be missed."""
    listed = {(method, path.replace("some-job", "{job_id}").replace("maps/overview", "maps/{map_name}"))
              for method, path in ROUTES}
    documentation = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

    served = {
        (method, route.path)
        for route in api_main.app.routes
        if route.path not in documentation
        for method in route.methods - {"HEAD", "OPTIONS"}
    }

    assert served == listed


def test_a_request_with_a_refused_token_is_turned_away(client, signing_key):
    expired = _token(signing_key, exp=int(time.time()) - 60)

    response = client.get("/api/jobs", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401
    # The reason stays in the log: the caller is not told what to change.
    assert response.json() == {"detail": "Not signed in"}


def test_a_request_with_a_good_token_is_served(client, signing_key):
    response = client.get("/api/jobs", headers={"Authorization": f"Bearer {_token(signing_key)}"})

    assert response.status_code == 200
    assert response.json() == []


def test_the_api_says_so_when_the_login_service_cannot_be_reached(client, signing_key, monkeypatch):
    def unreachable(token):
        raise jwt.PyJWKClientConnectionError("connection refused")

    monkeypatch.setitem(
        api_main.app.dependency_overrides,
        api_main.get_token_verifier,
        lambda: TokenVerifier(ISSUER, AUDIENCE, signing_key_for=unreachable),
    )

    response = client.get("/api/jobs", headers={"Authorization": f"Bearer {_token(signing_key)}"})

    assert response.status_code == 503


def test_the_api_refuses_everyone_when_the_login_check_is_not_set_up(client, signing_key, monkeypatch):
    """Required but with no login service named: closed, rather than open."""
    monkeypatch.setitem(api_main.app.dependency_overrides, api_main.get_token_verifier, lambda: None)

    response = client.get("/api/jobs", headers={"Authorization": f"Bearer {_token(signing_key)}"})

    assert response.status_code == 503


def test_the_login_check_can_be_switched_off_for_local_work(client, monkeypatch):
    monkeypatch.setattr(api_main.settings, "auth_required", False)

    assert client.get("/api/jobs").status_code == 200
