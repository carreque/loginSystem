"""Fixtures for the live smoke tests (real, deployed AWS stack).

These tests are skipped unless the stack coordinates are exported, so
`python -m pytest` stays green offline. To run them, feed in the
`terraform output` values:

    export LIVE_API_URL=https://<id>.execute-api.<region>.amazonaws.com/prod
    export LIVE_USER_POOL_ID=us-east-1_XXXXXXXXX
    export LIVE_APP_CLIENT_ID=<app client id>
    export LIVE_BUCKET=<resource bucket>
    export LIVE_CLOUDFRONT_DOMAIN=<distribution domain>
    python -m pytest tests/live -m live

The route-matrix tests additionally need one real access token per profile
(`LIVE_TOKEN_EMPLEADO` / `LIVE_TOKEN_SUPERVISOR` / `LIVE_TOKEN_ADMIN`); each
test skips individually while its token is missing.
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

REQUIRED_VARS = (
    "LIVE_API_URL",
    "LIVE_USER_POOL_ID",
    "LIVE_APP_CLIENT_ID",
    "LIVE_BUCKET",
    "LIVE_CLOUDFRONT_DOMAIN",
)


def _env(name, default=""):
    return os.environ.get(name, default).strip()


@pytest.fixture(scope="session")
def live(request):
    """Deployed-stack coordinates, derived from the terraform outputs."""
    missing = [v for v in REQUIRED_VARS if not _env(v)]
    if missing:
        pytest.skip(f"live tests need: {', '.join(missing)}")

    api_url = _env("LIVE_API_URL").rstrip("/")
    host = api_url.split("//", 1)[1].split("/", 1)[0]
    rest_api_id, _, region = host.split(".")[0], None, host.split(".")[2]
    pool_id = _env("LIVE_USER_POOL_ID")

    return {
        "api_url": api_url,
        "rest_api_id": rest_api_id,
        "stage": api_url.rsplit("/", 1)[-1],
        "region": region,
        "user_pool_id": pool_id,
        "app_client_id": _env("LIVE_APP_CLIENT_ID"),
        "bucket": _env("LIVE_BUCKET"),
        "cloudfront_domain": _env("LIVE_CLOUDFRONT_DOMAIN"),
        "issuer": f"https://cognito-idp.{region}.amazonaws.com/{pool_id}",
        "project": _env("LIVE_PROJECT_NAME", "employee-portal-auth"),
    }


@pytest.fixture(scope="session")
def live_jwks(live):
    """The user pool's real JWKS — proves the authorizer's key source is reachable."""
    url = f"{live['issuer']}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


@pytest.fixture(scope="session")
def token_for(live):
    """Real access token for a profile, or skip while it is not supplied."""

    def _token(group):
        var = f"LIVE_TOKEN_{group.upper()}"
        value = _env(var)
        if not value:
            pytest.skip(f"set {var} to a real access token for a '{group}' user")
        return value

    return _token
