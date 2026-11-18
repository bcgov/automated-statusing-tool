"""
Login check: is the caller of an API route someone who has signed in?

The frontend signs a person in with the BC Gov login service (Keycloak) and is
given an access token. It sends that token with every request:

    Authorization: Bearer <access token>

TokenVerifier checks the token is one the login service issued for this
application and that it has not expired. Nothing about the token is taken on
trust: its signature is checked against the login service's published keys, so
a token that was made up or altered is refused.

A token is a credential. It is never logged, and neither are the claims in it,
which name the person.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt

# The login service signs its tokens with an RSA key. Naming the algorithm here,
# rather than reading it from the token, is what stops a token from choosing a
# weaker check for itself.
SIGNING_ALGORITHMS = ["RS256"]

# Where Keycloak publishes a realm's signing keys, under the issuer's address.
JWKS_PATH = "/protocol/openid-connect/certs"

# How long to wait for the login service's keys, and how long to keep them.
JWKS_TIMEOUT_SECONDS = 5
JWKS_LIFESPAN_SECONDS = 60 * 60

# The type Keycloak gives an access token. An ID token is signed with the same
# key and names the same application, but it is not a credential for an API.
ACCESS_TOKEN_TYPE = "Bearer"


class TokenError(Exception):
    """The token is not one this API accepts. The message says why, for the log."""


class KeyServiceError(Exception):
    """The login service's keys could not be fetched, so no token can be checked."""


@dataclass(frozen=True)
class AuthenticatedUser:
    """The signed-in person a request was made by."""

    # The login service's own id for the person; the same on every sign-in.
    subject: str


class TokenVerifier:
    """Checks access tokens issued by one login service for one application."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_url: str | None = None,
        signing_key_for: Callable[[str], Any] | None = None,
    ):
        """
        issuer: the login service's address, as it appears in a token's "iss".
        audience: this application's client id, as it appears in a token's "aud".
        jwks_url: where the signing keys are published. Worked out from the
            issuer when not given.
        signing_key_for: returns the key a token was signed with. Left out in
            normal use, when the key is fetched from jwks_url; the tests pass
            one in so that no login service is needed.
        """
        self.issuer = issuer
        self.audience = audience
        if signing_key_for is None:
            jwks_client = jwt.PyJWKClient(
                jwks_url or issuer.rstrip("/") + JWKS_PATH,
                cache_keys=True,
                lifespan=JWKS_LIFESPAN_SECONDS,
                timeout=JWKS_TIMEOUT_SECONDS,
            )
            signing_key_for = lambda token: jwks_client.get_signing_key_from_jwt(token).key
        self._signing_key_for = signing_key_for

    def verify(self, token: str) -> AuthenticatedUser:
        """Return who a token belongs to.

        Raises TokenError when the token is refused, and KeyServiceError when
        the login service's keys could not be fetched to check it with.
        """
        try:
            claims = jwt.decode(
                token,
                self._signing_key_for(token),
                algorithms=SIGNING_ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as e:
            raise KeyServiceError("The login service's keys could not be fetched") from e
        except jwt.PyJWTError as e:
            # The library's messages describe the fault ("Signature has
            # expired") and do not repeat the token.
            raise TokenError(str(e)) from e

        if claims.get("typ", ACCESS_TOKEN_TYPE) != ACCESS_TOKEN_TYPE:
            raise TokenError("Not an access token")

        return AuthenticatedUser(subject=claims["sub"])
