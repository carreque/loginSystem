"""GET /resource/{id}: group re-check, validate {id}, s3:GetObject.

Allowed groups: empleado, supervisor, admin.
"""
from __future__ import annotations

import os
import re

import boto3

from common.http import AuthorizationError, require_groups, response

ALLOWED_GROUPS = ("empleado", "supervisor", "admin")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CLIENT = None


def _s3():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = boto3.client("s3")
    return _CLIENT


def handler(event, context):  # noqa: ARG001
    try:
        require_groups(event, ALLOWED_GROUPS)
    except AuthorizationError as exc:
        return response(403, {"message": str(exc)})

    resource_id = (event.get("pathParameters") or {}).get("id", "")
    if not ID_PATTERN.match(resource_id):
        return response(400, {"message": "invalid resource id"})

    bucket = os.environ["RESOURCE_BUCKET"]
    try:
        obj = _s3().get_object(Bucket=bucket, Key=f"resources/{resource_id}")
    except _s3().exceptions.NoSuchKey:
        return response(404, {"message": "not found"})
    return response(200, {"id": resource_id, "content": obj["Body"].read().decode("utf-8")})