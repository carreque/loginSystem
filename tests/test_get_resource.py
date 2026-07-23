"""GET /resource/{id}: moto S3, group re-check, {id} validation."""
import boto3
import pytest
from moto import mock_aws

from get_resource import handler

BUCKET = "test-resource-bucket"


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("RESOURCE_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    handler._CLIENT = None  # force the lazy client to bind inside the mock
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        client.put_object(Bucket=BUCKET, Key="resources/42", Body=b"hello world")
        yield client
    handler._CLIENT = None


def _event(resource_id, groups="empleado"):
    return {
        "pathParameters": {"id": resource_id},
        "requestContext": {"authorizer": {"groups": groups}},
    }


def test_returns_object_for_allowed_group(s3):
    resp = handler.handler(_event("42"), None)
    assert resp["statusCode"] == 200
    assert "hello world" in resp["body"]


def test_forbidden_without_a_permitted_group(s3):
    resp = handler.handler(_event("42", groups=""), None)
    assert resp["statusCode"] == 403


def test_invalid_id_rejected(s3):
    resp = handler.handler(_event("../secret"), None)
    assert resp["statusCode"] == 400


def test_missing_object_is_404(s3):
    resp = handler.handler(_event("99"), None)
    assert resp["statusCode"] == 404
