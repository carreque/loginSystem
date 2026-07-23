"""POST /createUser: moto Cognito AdminCreateUser, admin-only re-check."""
import json

import boto3
import pytest
from moto import mock_aws

from create_user import handler


@pytest.fixture
def cognito(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    handler._CLIENT = None
    with mock_aws():
        client = boto3.client("cognito-idp", region_name="us-east-1")
        pool_id = client.create_user_pool(PoolName="test")["UserPool"]["Id"]
        for name in ("empleado", "supervisor", "admin"):
            client.create_group(GroupName=name, UserPoolId=pool_id)
        monkeypatch.setenv("USER_POOL_ID", pool_id)
        yield client, pool_id
    handler._CLIENT = None


def _event(body, groups="admin"):
    return {
        "body": json.dumps(body),
        "requestContext": {"authorizer": {"groups": groups}},
    }


def test_admin_creates_user_in_group(cognito):
    client, pool_id = cognito
    resp = handler.handler(_event({"email": "new@example.com", "group": "supervisor"}), None)
    assert resp["statusCode"] == 201
    groups = client.admin_list_groups_for_user(Username="new@example.com", UserPoolId=pool_id)
    assert groups["Groups"][0]["GroupName"] == "supervisor"


def test_non_admin_forbidden(cognito):
    resp = handler.handler(_event({"email": "x@example.com"}, groups="supervisor"), None)
    assert resp["statusCode"] == 403


def test_invalid_email_rejected(cognito):
    resp = handler.handler(_event({"email": "not-an-email"}), None)
    assert resp["statusCode"] == 400


def test_invalid_group_rejected(cognito):
    resp = handler.handler(_event({"email": "a@b.com", "group": "root"}), None)
    assert resp["statusCode"] == 400
