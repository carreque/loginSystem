"""Shared HTTP helpers for resource Lambdas: JSON responses + group re-check.

`require_groups` re-derives the caller's Cognito groups from the authorizer
context (never from the client) and enforces membership as defense-in-depth
(planLoginSystem.md, Phase 3; research §3, A01).
"""
from __future__ import annotations

import json


class AuthorizationError(Exception):
    """Raised when the caller lacks a required group (maps to HTTP 403)."""


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def caller_groups(event):
    """Groups the authorizer stamped into the request context (comma-joined)."""
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    raw = authorizer.get("groups", "") or ""
    return [g for g in raw.split(",") if g]


def require_groups(event, allowed):
    groups = set(caller_groups(event))
    if not groups & set(allowed):
        raise AuthorizationError(
            f"caller groups {sorted(groups)} not permitted; need one of {sorted(allowed)}"
        )
    return groups