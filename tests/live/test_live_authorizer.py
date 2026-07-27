"""Live fail-closed checks — no user credentials required.

Every case here proves the deployed authorizer denies without ever handing out a
valid token, so they can run the moment `terraform apply` finishes. Two distinct
rejections are expected and must not be confused:

* **401** — no `Authorization` header at all. API Gateway short-circuits on the
  authorizer's `identity_source` and never invokes the Lambda.
* **403** — header present, authorizer ran and returned an explicit Deny
  (`{"Message": "User is not authorized to access this resource..."}`).
"""
from __future__ import annotations

import pytest
import requests

pytestmark = pytest.mark.live

TIMEOUT = 20
ROUTES = [
    ("GET", "/resource/demo"),
    ("POST", "/upload?key=smoke.txt"),
    ("POST", "/createUser"),
]


def call(live, method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(
        method, f"{live['api_url']}{path}", headers=headers, timeout=TIMEOUT, **kwargs
    )


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_missing_authorization_header_is_401(live, method, path):
    assert call(live, method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_garbage_token_is_denied(live, method, path):
    assert call(live, method, path, token="not-a-jwt").status_code == 403


def test_token_signed_by_an_unknown_key_is_denied(live, make_token):
    """Correct issuer and client_id, but our own signing key and an unknown kid.

    The authorizer refreshes the JWKS once on an unknown kid; the refresh cannot
    produce our key, so it must still deny.
    """
    forged = make_token(
        groups=["admin"], issuer=live["issuer"], client_id=live["app_client_id"]
    )
    assert call(live, "GET", "/resource/demo", token=forged).status_code == 403


def test_token_with_a_real_kid_but_a_forged_signature_is_denied(live, live_jwks, make_token):
    """Borrow a genuine `kid` from the pool's JWKS — the signature still fails."""
    real_kid = live_jwks["keys"][0]["kid"]
    forged = make_token(
        groups=["admin"],
        kid=real_kid,
        issuer=live["issuer"],
        client_id=live["app_client_id"],
    )
    assert call(live, "GET", "/resource/demo", token=forged).status_code == 403


def test_undefined_route_is_not_reachable(live):
    """Deny-by-default: a path with no method defined never reaches a Lambda."""
    assert call(live, "GET", "/admin/secrets", token="not-a-jwt").status_code == 403


def test_jwks_endpoint_is_reachable(live_jwks):
    """The authorizer fetches this at runtime; if it 404s, every request denies."""
    assert live_jwks["keys"], "user pool JWKS returned no signing keys"
