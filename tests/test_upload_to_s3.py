"""POST /upload: moto S3, size/type limits, group re-check."""
import boto3
import pytest
from moto import mock_aws

from upload_to_s3 import handler

BUCKET = "test-resource-bucket"


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("RESOURCE_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    handler._CLIENT = None
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client
    handler._CLIENT = None


def _event(groups="supervisor", body="hi", content_type="text/plain", key="doc.txt"):
    return {
        "headers": {"Content-Type": content_type},
        "body": body,
        "isBase64Encoded": False,
        "queryStringParameters": {"key": key},
        "requestContext": {"authorizer": {"groups": groups}},
    }


def test_supervisor_can_upload(s3):
    resp = handler.handler(_event(), None)
    assert resp["statusCode"] == 201
    assert s3.get_object(Bucket=BUCKET, Key="uploads/doc.txt")["Body"].read() == b"hi"


def test_empleado_forbidden(s3):
    resp = handler.handler(_event(groups="empleado"), None)
    assert resp["statusCode"] == 403


def test_unsupported_content_type_rejected(s3):
    resp = handler.handler(_event(content_type="application/x-msdownload"), None)
    assert resp["statusCode"] == 415


def test_oversized_payload_rejected(s3):
    resp = handler.handler(_event(body="x" * (5 * 1024 * 1024 + 1)), None)
    assert resp["statusCode"] == 413


def test_bad_key_rejected(s3):
    resp = handler.handler(_event(key="../evil"), None)
    assert resp["statusCode"] == 400
