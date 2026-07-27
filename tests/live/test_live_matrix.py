"""The route -> group matrix, exercised against the deployed API.

This is the acceptance test for the whole system: nine cases (three profiles x
three routes) plus the negatives that prove the server, not the client, decides.
Each test skips until `LIVE_TOKEN_<PROFILE>` holds a real **access** token
(not an ID token) for a user in that Cognito group.

| Route                | empleado | supervisor | admin |
|----------------------|----------|------------|-------|
| `GET /resource/{id}` | allow    | allow      | allow |
| `POST /upload`       | deny     | allow      | allow |
| `POST /createUser`   | deny     | deny       | allow |
"""
from __future__ import annotations

import uuid

import boto3
import pytest
import requests

pytestmark = pytest.mark.live

TIMEOUT = 20
DENIED = 403


def call(live, method, path, token, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return requests.request(
        method, f"{live['api_url']}{path}", headers=headers, timeout=TIMEOUT, **kwargs
    )


@pytest.fixture(scope="session")
def seeded_resource(live):
    """An object at `resources/<id>`, so GET has something real to return."""
    s3 = boto3.client("s3", region_name=live["region"])
    resource_id = f"smoke-{uuid.uuid4().hex[:8]}"
    s3.put_object(
        Bucket=live["bucket"],
        Key=f"resources/{resource_id}",
        Body=b"live smoke test payload",
        ContentType="text/plain",
    )
    yield resource_id
    s3.delete_object(Bucket=live["bucket"], Key=f"resources/{resource_id}")


# --- GET /resource/{id} — all three profiles -------------------------------
@pytest.mark.parametrize("profile", ["empleado", "supervisor", "admin"])
def test_get_resource_is_allowed_for_every_profile(live, token_for, seeded_resource, profile):
    resp = call(live, "GET", f"/resource/{seeded_resource}", token_for(profile))
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"] == "live smoke test payload"


def test_get_resource_rejects_a_malformed_id(live, token_for):
    """Input validation runs inside the Lambda, after authorization succeeds."""
    resp = call(live, "GET", "/resource/..%2Fetc%2Fpasswd", token_for("empleado"))
    assert resp.status_code == 400, resp.text


def test_get_missing_resource_is_404(live, token_for):
    """A missing object must be a clean 404, not a 5xx.

    The get-resource role holds `s3:GetObject` but no `s3:ListBucket`, so S3
    answers AccessDenied (not NoSuchKey) for a key that does not exist — which
    the handler does not catch. Expect this to fail until that is handled.
    """
    resp = call(live, "GET", f"/resource/absent-{uuid.uuid4().hex[:8]}", token_for("empleado"))
    assert resp.status_code == 404, resp.text


# --- POST /upload — supervisor + admin only --------------------------------
@pytest.mark.parametrize("profile", ["supervisor", "admin"])
def test_upload_is_allowed_for_supervisor_and_admin(live, profile, token_for):
    key = f"smoke-{uuid.uuid4().hex[:8]}.txt"
    resp = call(
        live,
        "POST",
        f"/upload?key={key}",
        token_for(profile),
        headers={"Content-Type": "text/plain"},
        data="live smoke test upload",
    )
    assert resp.status_code == 201, resp.text

    s3 = boto3.client("s3", region_name=live["region"])
    stored = s3.get_object(Bucket=live["bucket"], Key=f"uploads/{key}")
    assert stored["Body"].read() == b"live smoke test upload"
    s3.delete_object(Bucket=live["bucket"], Key=f"uploads/{key}")


def test_upload_is_denied_for_empleado(live, token_for):
    resp = call(
        live,
        "POST",
        "/upload?key=denied.txt",
        token_for("empleado"),
        headers={"Content-Type": "text/plain"},
        data="should never be stored",
    )
    assert resp.status_code == DENIED, resp.text


def test_upload_rejects_a_disallowed_content_type(live, token_for):
    resp = call(
        live,
        "POST",
        "/upload?key=evil.html",
        token_for("supervisor"),
        headers={"Content-Type": "text/html"},
        data="<script>alert(1)</script>",
    )
    assert resp.status_code == 415, resp.text


# --- POST /createUser — admin only -----------------------------------------
def test_create_user_is_allowed_for_admin(live, token_for):
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    resp = call(
        live,
        "POST",
        "/createUser",
        token_for("admin"),
        json={"email": email, "group": "empleado"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"username": email, "group": "empleado"}

    cognito = boto3.client("cognito-idp", region_name=live["region"])
    groups = cognito.admin_list_groups_for_user(
        UserPoolId=live["user_pool_id"], Username=email
    )["Groups"]
    assert [g["GroupName"] for g in groups] == ["empleado"]
    cognito.admin_delete_user(UserPoolId=live["user_pool_id"], Username=email)


@pytest.mark.parametrize("profile", ["empleado", "supervisor"])
def test_create_user_is_denied_below_admin(live, profile, token_for):
    resp = call(
        live,
        "POST",
        "/createUser",
        token_for(profile),
        json={"email": f"nope-{uuid.uuid4().hex[:8]}@example.com", "group": "admin"},
    )
    assert resp.status_code == DENIED, resp.text


def test_create_user_rejects_an_unknown_group(live, token_for):
    resp = call(
        live,
        "POST",
        "/createUser",
        token_for("admin"),
        json={"email": f"smoke-{uuid.uuid4().hex[:8]}@example.com", "group": "root"},
    )
    assert resp.status_code == 400, resp.text


# --- Never trust the client ------------------------------------------------
def test_client_supplied_group_headers_are_ignored(live, token_for):
    """An empleado claiming to be an admin in headers is still an empleado."""
    resp = call(
        live,
        "POST",
        "/upload?key=escalated.txt",
        token_for("empleado"),
        headers={
            "Content-Type": "text/plain",
            "x-cognito-groups": "admin",
            "X-Groups": "admin,supervisor",
        },
        data="privilege escalation attempt",
    )
    assert resp.status_code == DENIED, resp.text


def test_id_token_is_rejected(live):
    """Authorize on the access token only; an ID token must not work.

    Needs `LIVE_ID_TOKEN_ADMIN` — the ID token from the same sign-in that
    produced `LIVE_TOKEN_ADMIN`.
    """
    import os

    id_token = os.environ.get("LIVE_ID_TOKEN_ADMIN", "").strip()
    if not id_token:
        pytest.skip("set LIVE_ID_TOKEN_ADMIN to an admin's ID token")
    resp = call(live, "GET", "/resource/demo", id_token)
    assert resp.status_code == DENIED, resp.text
