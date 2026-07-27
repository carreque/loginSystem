"""`live_tokens.py --reset` must never destroy the only copy of the TOTP secrets.

`.live-users.json` is the *recovery key* for the smoke users: it holds their
passwords and TOTP secrets, and the pool enforces MFA. Once it is gone, a user
that still exists in the pool can never be signed in again — `sign_in` raises
"already has TOTP enrolled but no secret is cached" and points at `--reset`,
which is the very operation that cannot recover the situation.

So `reset()` owes two guarantees:

  1. It finds the smoke users even when the state file does not list them —
     their names are deterministic (`smoke-{profile}@{domain}`).
  2. It removes the state file only once every targeted user is confirmed gone.

Every test here monkeypatches `STATE_FILE` to a tmp_path. It must never point at
the repo's real `.live-users.json` — deleting that is precisely the bug.
"""
from __future__ import annotations

import json
import sys

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

import live_tokens

REGION = "us-east-1"


@pytest.fixture(autouse=True)
def dummy_aws_credentials(monkeypatch):
    """Belt-and-braces: moto intercepts botocore, but never risk real calls."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Redirect the module's STATE_FILE away from the real .live-users.json."""
    path = tmp_path / ".live-users.json"
    monkeypatch.setattr(live_tokens, "STATE_FILE", path)
    return path


@pytest.fixture
def cognito():
    with mock_aws():
        yield boto3.client("cognito-idp", region_name=REGION)


@pytest.fixture
def pool_id(cognito):
    return cognito.create_user_pool(PoolName="test-pool")["UserPool"]["Id"]


def seed(cognito, pool_id, *emails):
    for email in emails:
        cognito.admin_create_user(UserPoolId=pool_id, Username=email, MessageAction="SUPPRESS")


def usernames(cognito, pool_id):
    return {u["Username"] for u in cognito.list_users(UserPoolId=pool_id)["Users"]}


def state_of(*emails):
    return {e.split("@")[0].removeprefix("smoke-"): {"email": e} for e in emails}


SMOKE = [f"smoke-{p}@example.com" for p in live_tokens.PROFILES]


# --- Defect 1: the state file is not the only source of truth -----------------
def test_deletes_smoke_users_absent_from_state(cognito, pool_id, state_file):
    """The whole point: no state file, users still in the pool, still cleaned up.

    This is the deadlock's entry condition. `--reset` previously printed its
    header, deleted nothing, exited 0, and looked like success.
    """
    seed(cognito, pool_id, *SMOKE)
    assert not state_file.exists()

    live_tokens.reset(cognito, pool_id, {}, "example.com")

    assert usernames(cognito, pool_id) == set()


def test_deletes_users_listed_in_state(cognito, pool_id, state_file):
    seed(cognito, pool_id, *SMOKE)
    state_file.write_text(json.dumps(state_of(*SMOKE)), encoding="utf-8")

    live_tokens.reset(cognito, pool_id, state_of(*SMOKE), "example.com")

    assert usernames(cognito, pool_id) == set()
    assert not state_file.exists()


def test_deletes_adhoc_users_keyed_by_email(cognito, pool_id, state_file):
    """`--user` entries are keyed by email, not profile (live_tokens.py:244)."""
    seed(cognito, pool_id, "alice@example.com", *SMOKE)

    live_tokens.reset(
        cognito, pool_id, {"alice@example.com": {"email": "alice@example.com"}}, "example.com"
    )

    assert usernames(cognito, pool_id) == set()


def test_honours_custom_email_domain(cognito, pool_id, state_file):
    """The seeded names follow LIVE_TEST_EMAIL_DOMAIN (live_tokens.py:254)."""
    corp = [f"smoke-{p}@corp.test" for p in live_tokens.PROFILES]
    seed(cognito, pool_id, *corp)

    live_tokens.reset(cognito, pool_id, {}, "corp.test")

    assert usernames(cognito, pool_id) == set()


# --- Defect 2: the state file is the recovery key -----------------------------
def test_keeps_state_file_when_a_delete_fails(cognito, pool_id, state_file, monkeypatch):
    """A failed delete must NOT cost you the secrets of the user that survived.

    Throttling, an IAM denial or a network blip previously still fell through to
    an unconditional unlink, manufacturing the deadlock from a healthy start.
    """
    seed(cognito, pool_id, *SMOKE)
    state_file.write_text(json.dumps(state_of(*SMOKE)), encoding="utf-8")

    real = cognito.admin_delete_user
    stubborn = "smoke-admin@example.com"

    def flaky(**kwargs):
        if kwargs["Username"] == stubborn:
            raise ClientError(
                {"Error": {"Code": "TooManyRequestsException", "Message": "slow down"}},
                "AdminDeleteUser",
            )
        return real(**kwargs)

    monkeypatch.setattr(cognito, "admin_delete_user", flaky)

    live_tokens.reset(cognito, pool_id, state_of(*SMOKE), "example.com")

    assert state_file.exists(), "secrets destroyed while a user still exists"
    assert json.loads(state_file.read_text(encoding="utf-8"))["admin"]["email"] == stubborn
    assert usernames(cognito, pool_id) == {stubborn}


def test_removes_state_file_once_everything_is_gone(cognito, pool_id, state_file):
    seed(cognito, pool_id, *SMOKE)
    state_file.write_text(json.dumps(state_of(*SMOKE)), encoding="utf-8")

    live_tokens.reset(cognito, pool_id, state_of(*SMOKE), "example.com")

    assert not state_file.exists()


# --- Defect 4: "already absent" is the expected case, not an error ------------
def test_absent_users_are_not_reported_as_failures(cognito, pool_id, state_file, capsys):
    """After a pool replacement every user is legitimately gone.

    Printing "could not delete" for all three is noise that would also mask a
    genuine permissions error.
    """
    state_file.write_text(json.dumps(state_of(*SMOKE)), encoding="utf-8")

    live_tokens.reset(cognito, pool_id, state_of(*SMOKE), "example.com")

    assert "could not delete" not in capsys.readouterr().out
    assert not state_file.exists()


# --- The call site ------------------------------------------------------------
def test_main_reset_supplies_the_domain(cognito, pool_id, state_file, monkeypatch):
    """`main()` must pass `domain` through to reset().

    `domain` is derived after the --reset branch returns, so the call site needs
    it hoisted; otherwise --reset dies with TypeError before deleting anything.
    """
    seed(cognito, pool_id, *SMOKE)
    monkeypatch.setenv("LIVE_USER_POOL_ID", pool_id)
    monkeypatch.setenv("LIVE_APP_CLIENT_ID", "test-client-id")
    monkeypatch.delenv("LIVE_TEST_EMAIL_DOMAIN", raising=False)
    monkeypatch.setattr(sys, "argv", ["live_tokens.py", "--reset"])
    monkeypatch.setattr(live_tokens.boto3, "client", lambda *a, **k: cognito)

    live_tokens.main()

    assert usernames(cognito, pool_id) == set()
