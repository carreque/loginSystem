"""POST /createUser: admin-only re-check, input validation, AdminCreateUser.

Allowed groups: admin only. Creates the user then adds them to a valid group.
"""
from __future__ import annotations

import json
import os
import re

import boto3

from common.http import AuthorizationError, require_groups, response

ALLOWED_GROUPS = ("admin",)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_GROUPS = {"empleado", "supervisor", "admin"}

COGNITO_CLIENT = None


def _cognito():
    global COGNITO_CLIENT
    if COGNITO_CLIENT is None:
        COGNITO_CLIENT = boto3.client("cognito-idp")
    return COGNITO_CLIENT


def handler(event, context):  # noqa: ARG001
    try:
        require_groups(event, ALLOWED_GROUPS)
    except AuthorizationError as exc:
        return response(403, {"message": str(exc)})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"message": "invalid JSON body"})

    email = payload.get("email", "")
    group = payload.get("group", "empleado")
    if not EMAIL_PATTERN.match(email):
        return response(400, {"message": "invalid email"})
    if group not in VALID_GROUPS:
        return response(400, {"message": "invalid group"})

    pool_id = os.environ["USER_POOL_ID"]
    _cognito().admin_create_user(
        UserPoolId=pool_id,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
        DesiredDeliveryMediums=["EMAIL"],
    )
    _cognito().admin_add_user_to_group(UserPoolId=pool_id, Username=email, GroupName=group)
    return response(201, {"username": email, "group": group})