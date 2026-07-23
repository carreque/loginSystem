"""RBAC over the route->group matrix, deny-by-default, fail-closed helper."""
import pytest

import verify

BASE = "arn:aws:execute-api:us-east-1:123456789012:abc123/prod"


def _arn(method, path):
    return f"{BASE}/{method}/{path}"


def _effect(policy):
    return policy["policyDocument"]["Statement"][0]["Effect"]


@pytest.mark.parametrize("group", ["empleado", "supervisor", "admin"])
def test_get_resource_allows_every_role(group):
    policy = verify.authorize(_arn("GET", "resource/42"), [group])
    assert _effect(policy) == "Allow"


@pytest.mark.parametrize(
    "group,expected",
    [("empleado", "Deny"), ("supervisor", "Allow"), ("admin", "Allow")],
)
def test_upload_requires_supervisor_or_admin(group, expected):
    policy = verify.authorize(_arn("POST", "upload"), [group])
    assert _effect(policy) == expected


@pytest.mark.parametrize(
    "group,expected",
    [("empleado", "Deny"), ("supervisor", "Deny"), ("admin", "Allow")],
)
def test_create_user_is_admin_only(group, expected):
    policy = verify.authorize(_arn("POST", "createUser"), [group])
    assert _effect(policy) == expected


def test_unknown_route_denied():
    policy = verify.authorize(_arn("DELETE", "resource/42"), ["admin"])
    assert _effect(policy) == "Deny"


def test_no_groups_denied_by_default():
    policy = verify.authorize(_arn("GET", "resource/42"), [])
    assert _effect(policy) == "Deny"


def test_multiple_groups_allow_if_any_match():
    policy = verify.authorize(_arn("POST", "createUser"), ["empleado", "admin"])
    assert _effect(policy) == "Allow"


def test_deny_helper_is_deny_policy():
    policy = verify.deny(_arn("GET", "resource/42"))
    assert _effect(policy) == "Deny"
    assert policy["context"]["reason"] == "deny-by-default"


def test_context_carries_groups_for_downstream_recheck():
    policy = verify.authorize(_arn("GET", "resource/42"), ["empleado"])
    assert policy["context"]["groups"] == "empleado"
