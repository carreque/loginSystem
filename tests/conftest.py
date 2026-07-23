"""Shared pytest fixtures for the authorizer.

Generates an RSA keypair in-process, exposes a fake JWKS document derived from
that key, and an access-token factory so the authorizer can be exercised without
a real Cognito User Pool.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

KID = "test-key-1"
ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TESTPOOL"
AUDIENCE = "test-app-client-id"  # Cognito access tokens carry this as `client_id`


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def jwks(rsa_key):
    """A JWKS document ({"keys": [...]}) holding the public half of `rsa_key`."""
    jwk = json.loads(RSAAlgorithm.to_jwk(rsa_key.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


@pytest.fixture
def issuer():
    return ISSUER


@pytest.fixture
def audience():
    return AUDIENCE


@pytest.fixture
def make_token(rsa_key):
    """Factory: mint a signed access token with chosen kid/exp/aud/iss/groups."""
    private_pem = rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    def _make(
        groups=None,
        kid=KID,
        exp_delta=3600,
        issuer=ISSUER,
        client_id=AUDIENCE,
        token_use="access",
        sub="user-123",
        **overrides,
    ):
        now = int(time.time())
        claims = {
            "sub": sub,
            "iss": issuer,
            "client_id": client_id,
            "token_use": token_use,
            "iat": now,
            "exp": now + exp_delta,
        }
        if groups is not None:
            claims["cognito:groups"] = groups
        claims.update(overrides)
        return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})

    return _make
