"""Shared pytest fixtures.

Phase 2 will add here:
  - an RSA keypair generated in-process,
  - a fake JWKS document derived from that key,
  - an access-token factory (kid / exp / aud / iss / cognito:groups),
so the authorizer can be exercised without a real Cognito User Pool.

During Phase 1 this file only marks the tests package; it holds no fixtures yet.
"""
