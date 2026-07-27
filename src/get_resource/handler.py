"""GET /resource/{id}: group re-check, validate {id}, s3:GetObject.

Allowed groups: empleado, supervisor, admin.
"""
from __future__ import annotations

import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

from common.http import AuthorizationError, require_groups, response

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ALLOWED_GROUPS = ("empleado", "supervisor", "admin")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# This role holds s3:GetObject but not s3:ListBucket, so S3 refuses to reveal
# whether a key exists: a plain miss comes back as AccessDenied rather than
# NoSuchKey. Both mean "not found" to the caller. Anything else is a real fault
# and must not be flattened into a 404.
NOT_FOUND_CODES = frozenset({"NoSuchKey", "AccessDenied", "404", "403"})
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
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code not in NOT_FOUND_CODES:
            raise
        # An AccessDenied here is indistinguishable from a genuine miss, so a
        # real permissions regression would masquerade as one. Log it.
        logger.warning(f"get_object on resources/{resource_id} failed with {code}")
        return response(404, {"message": "not found"})
    return response(200, {"id": resource_id, "content": obj["Body"].read().decode("utf-8")})