"""Lambda REQUEST authorizer for API Gateway.

Implements the "two-layer" auth model as a single authorizer (see
docs/planLoginSystem.md, "Key architectural reconciliation"):
  1. Full JWT verification via JWKS/RS256 (exp, aud, iss).
  2. `cognito:groups` per-route RBAC (deny-by-default, fail-closed).

Scaffolding only — implemented test-first in Phase 2. The pure logic lives in
`verify.py`; this handler is a thin adapter over it.
"""


def handler(event, context):  # noqa: ARG001
    raise NotImplementedError("Phase 2: implement JWT verification + group RBAC")
