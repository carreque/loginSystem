"""GET /resource/{id}: moto S3, group re-check, {id} validation."""
import boto3
import pytest
from botocore.exceptions import ClientError
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


def _raise(error):
    def _stub(**_kwargs):
        raise error

    return _stub


def test_missing_object_is_404_when_s3_answers_access_denied(s3, monkeypatch):
    """A miss looks like AccessDenied in AWS, not NoSuchKey.

    `get-resource-role` holds `s3:GetObject` but not `s3:ListBucket`, so S3
    refuses to reveal whether the key exists and returns AccessDenied instead.
    moto returns NoSuchKey regardless of IAM, which is why the test above
    passes while the deployed call returns 502.
    """
    denied = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "GetObject"
    )
    monkeypatch.setattr(handler._s3(), "get_object", _raise(denied))

    resp = handler.handler(_event("99"), None)
    assert resp["statusCode"] == 404


def test_unexpected_s3_error_is_not_masked_as_404(s3, monkeypatch):
    """Only not-found-shaped errors may become a 404.

    Guards the obvious over-correction: a blanket `except ClientError -> 404`
    would report throttling or a KMS denial as a clean miss, and the deny
    alarm would never see it.
    """
    throttled = ClientError(
        {"Error": {"Code": "SlowDown", "Message": "Please reduce your request rate"}},
        "GetObject",
    )
    monkeypatch.setattr(handler._s3(), "get_object", _raise(throttled))

    try:
        resp = handler.handler(_event("99"), None)
    except ClientError:
        return  # letting it surface is a valid choice; masking it is not
    assert resp["statusCode"] != 404
