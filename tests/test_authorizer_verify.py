"""JWT verification: signature, kid, exp, iss, audience, token_use, tampering."""
import pytest

import verify
from common.tokenError import TokenError

def test_valid_access_token_passes(make_token, jwks, issuer, audience):
    token = make_token(groups=["empleado"])
    claims = verify.verify_token(token, jwks, issuer, audience)
    assert claims["cognito:groups"] == ["empleado"]
    assert claims["token_use"] == "access"


def test_unknown_kid_denied(make_token, jwks, issuer, audience):
    token = make_token(kid="does-not-exist")
    with pytest.raises(TokenError):
        verify.verify_token(token, jwks, issuer, audience)


def test_expired_token_denied(make_token, jwks, issuer, audience):
    token = make_token(exp_delta=-10)
    with pytest.raises(TokenError):
        verify.verify_token(token, jwks, issuer, audience)


def test_wrong_issuer_denied(make_token, jwks, issuer, audience):
    token = make_token(issuer="https://evil.example.com")
    with pytest.raises(TokenError):
        verify.verify_token(token, jwks, issuer, audience)


def test_wrong_audience_denied(make_token, jwks, issuer, audience):
    token = make_token(client_id="some-other-client")
    with pytest.raises(TokenError):
        verify.verify_token(token, jwks, issuer, audience)


def test_id_token_denied(make_token, jwks, issuer, audience):
    # Only access tokens are accepted (gap #1).
    token = make_token(token_use="id")
    with pytest.raises(TokenError):
        verify.verify_token(token, jwks, issuer, audience)


def test_tampered_payload_denied(make_token, jwks, issuer, audience):
    token = make_token(groups=["admin"])
    header, payload, sig = token.split(".")
    tampered = f"{header}.{payload[:-2]}XX.{sig}"
    with pytest.raises(TokenError):
        verify.verify_token(tampered, jwks, issuer, audience)


def test_malformed_token_denied(jwks, issuer, audience):
    with pytest.raises(TokenError):
        verify.verify_token("not-a-jwt", jwks, issuer, audience)
