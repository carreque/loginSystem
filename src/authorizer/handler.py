"""Lambda REQUEST authorizer: JWT verify (verify.py) + group RBAC, fail-closed.

Reads the access token from the `Authorization` header, verifies it against the
User Pool JWKS (cached in module scope, refreshed once on an unknown kid), then
applies per-route RBAC. Any error path returns an explicit Deny policy.
"""
from __future__ import annotations
from exceptions.tokenError import TokenError
import json
import logging
import os
import urllib.request

import jwt

import verify

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_JWKS_CACHE = {}


def _issuer():
    region = os.environ["AWS_REGION"]  # provided by the Lambda runtime
    pool = os.environ["USER_POOL_ID"]
    return f"https://cognito-idp.{region}.amazonaws.com/{pool}"


def _jwks_url():
    return os.environ.get("JWKS_URL", f"{_issuer()}/.well-known/jwks.json")


def _load_jwks(force_refresh=False):
    if force_refresh or "jwks" not in _JWKS_CACHE:
        with urllib.request.urlopen(_jwks_url(), timeout=5) as resp:  # noqa: S310
            _JWKS_CACHE["jwks"] = json.loads(resp.read())
    return _JWKS_CACHE["jwks"]


def _extract_token(event):
    headers = event.get("headers") or {}
    raw = headers.get("Authorization") or headers.get("authorization") or ""
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw.strip()

def _token_kid(token):
    try:
        return jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        return None


def loadOrRefreshToken(token, issuer, audience):
    jwks = _load_jwks()
    kid = _token_kid(token)
    known_kids = {key.get("kid") for key in jwks.get("keys", [])}
    if kid not in known_kids:
        # A rotated signing key may not be in the cache yet — the only failure a
        # refresh can fix. Expired/tampered/wrong-claim tokens deny with no fetch.
        jwks = _load_jwks(force_refresh=True)
    return verify.verify_token(token, jwks, issuer, audience)
    
def handler(event, context):  # noqa: ARG001
    method_arn = event.get("methodArn", "*")
    try:
        token = _extract_token(event)
        if not token:
            raise verify.TokenError("missing Authorization header")
        issuer, audience = _issuer(), os.environ["APP_CLIENT_ID"]
        claims = loadOrRefreshToken(token, issuer, audience)
        groups = claims.get("cognito:groups", [])
        return verify.authorize(method_arn, groups, principal_id=claims.get("sub", "user"))
    except TokenError as err:
        logger.error(f"There was an error with the token: {str(err)}")
        return verify.deny(method_arn)
    except Exception as exc:  # fail closed on ANY error
        logger.warning(f"authorizer denying request: {exc}")
        return verify.deny(method_arn)