from __future__ import annotations
import json
import jwt
import re
from jwt.algorithms import RSAAlgorithm
from exceptions.tokenError import TokenError
from utils.errors import known_errors

_MATRIX = [
    ("GET", re.compile(r"^resource/[^/]+$"), frozenset({"empleado", "supervisor", "admin"})),
    ("POST", re.compile(r"^upload$"), frozenset({"supervisor", "admin"})),
    ("POST", re.compile(r"^createUser$"), frozenset({"admin"})),
]

# --- JWT verification ---------------------------------------------------------
def verify_header(token: any) -> dict[str, any]:
    try:
        return jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError(f"malformed token header: {exc}") from exc

def _key_for_kid(jwks, kid):
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return RSAAlgorithm.from_jwk(json.dumps(key))
    return None
    
def verify_kid(jwks: any, header: dict[str, any]):
    kid = header.get("kid")
    public_key = _key_for_kid(jwks, kid)
    if public_key is None:
        raise TokenError(f"unknown kid: {kid!r}")
    return public_key

def verify_claims(token, public_key, issuer, audience):
    try:
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "iss"], "verify_aud": False},
        )
        # Cognito access tokens put the app client id in `client_id`, not `aud`.
        if claims.get("client_id") != audience:
            raise TokenError("client_id does not match expected audience")
        if claims.get("token_use") != "access":
            raise TokenError("token_use is not 'access'")
        return claims
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    
def verify_token(token, jwks, issuer, audience):
    """Verify a Cognito access token. Returns its claims or raises TokenError."""
   
    try: 
        header = verify_header(token)
        public_key = verify_kid(jwks, header)
        return verify_claims(token, public_key, issuer, audience)
    except TokenError as err:
        raise TokenError(str(err)) 


# --- RBAC + policy ------------------------------------------------------------
def _parse_method_arn(method_arn):
    # arn:aws:execute-api:REGION:ACCOUNT:API-ID/STAGE/METHOD/RESOURCE...
    api_part = method_arn.split(":", 5)[5]
    segments = api_part.split("/")
    method = segments[2]
    resource_path = "/".join(segments[3:])
    return method, resource_path


def _allowed_groups_for(method, resource_path):
    for apiMethod, pattern, allowed in _MATRIX:
        if apiMethod == method and pattern.match(resource_path):
            return allowed
    return known_errors.UNKNOWN_ROUTE


def _policy(principal_id, effect, resource, context=None):
    doc = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {"Action": "execute-api:Invoke", "Effect": effect, "Resource": resource}
            ],
        },
    }
    if context:
        doc["context"] = context
    return doc

def isAllowedMethodPermittedForTheseGroups(groups, allowed) ->bool:
    return allowed is not None and bool(set(groups) & allowed)

def authorize(method_arn, groups, principal_id="user"):
    """Apply the route matrix to `groups`; build an Allow/Deny IAM policy."""
    method, resource_path = _parse_method_arn(method_arn)
    allowed = _allowed_groups_for(method, resource_path)
    permitted = isAllowedMethodPermittedForTheseGroups(groups, allowed)
    effect = "Allow" if permitted else "Deny"
    # Carry groups downstream so resource Lambdas can re-check (defense in depth).
    context = {"groups": ",".join(groups)}
    return _policy(principal_id, effect, method_arn, context)


def deny(method_arn, principal_id="user"):
    """Explicit fail-closed Deny (used by the handler's error path)."""
    return _policy(principal_id, "Deny", method_arn, {"reason": "deny-by-default"})