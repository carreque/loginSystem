"""POST /upload: group re-check, size + content-type limits, s3:PutObject.

Allowed groups: supervisor, admin.
"""
from __future__ import annotations

import base64
import os

import boto3

from common.http import AuthorizationError, require_groups, response

ALLOWED_GROUPS = ("supervisor", "admin")
MAX_BYTES = 5 * 1024 * 1024  # 5 MiB
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
S3_CLIENT = None


def _s3():
    global S3_CLIENT
    if S3_CLIENT is None:
        S3_CLIENT = boto3.client("s3")
    return S3_CLIENT


def handler(event, context):  # noqa: ARG001
    try:
        require_groups(event, ALLOWED_GROUPS)
    except AuthorizationError as exc:
        return response(403, {"message": str(exc)})

    headers = event.get("headers") or {}
    content_type = headers.get("Content-Type") or headers.get("content-type") or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        return response(415, {"message": "unsupported content type"})

    raw = event.get("body") or ""
    data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")
    if len(data) > MAX_BYTES:
        return response(413, {"message": "payload too large"})

    key = (event.get("queryStringParameters") or {}).get("key", "")
    if not key or "/" in key or ".." in key:
        return response(400, {"message": "invalid or missing key"})

    bucket = os.environ["RESOURCE_BUCKET"]
    _s3().put_object(Bucket=bucket, Key=f"uploads/{key}", Body=data, ContentType=content_type)
    return response(201, {"key": f"uploads/{key}", "bytes": len(data)})