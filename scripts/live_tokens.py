"""Seed one user per profile and mint the access tokens `tests/live` needs.

The deployed app client allows SRP only (no Hosted UI, no password flows) and
the pool enforces TOTP MFA, so tokens cannot be fetched with plain boto3 calls.
This walks the real flow instead: AdminCreateUser -> permanent password ->
USER_SRP_AUTH -> TOTP enrolment -> SOFTWARE_TOKEN_MFA.

Nothing about the deployed configuration is relaxed to make this work.

    python scripts/live_tokens.py            # seed (first run) then print exports
    python scripts/live_tokens.py --reset    # delete the seeded users and start over

Credentials and TOTP secrets are cached in `.live-users.json` (gitignored) so
later runs skip enrolment and just re-mint tokens. Users are created with
MessageAction=SUPPRESS — Cognito sends no email.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import string
import sys

import boto3
import pyotp
from botocore.exceptions import ClientError
from pycognito.aws_srp import AWSSRP
from pycognito.exceptions import SoftwareTokenMFAChallengeException

PROFILES = ("empleado", "supervisor", "admin")
STATE_FILE = pathlib.Path(__file__).resolve().parent.parent / ".live-users.json"
DEVICE_NAME = "live-smoke-tests"

QUIET = False


def say(message):
    """Progress output, silenced by --token-only so stdout stays capturable."""
    if not QUIET:
        print(message)


def export_line(name, value, shell):
    """Emit an assignment in the caller's shell dialect (PowerShell != bash)."""
    if shell == "powershell":
        return f'$env:{name} = "{value}"'
    return f"export {name}={value}"


def config():
    pool_id = os.environ.get("LIVE_USER_POOL_ID", "").strip()
    client_id = os.environ.get("LIVE_APP_CLIENT_ID", "").strip()
    if not pool_id or not client_id:
        sys.exit("set LIVE_USER_POOL_ID and LIVE_APP_CLIENT_ID (see terraform output)")
    return pool_id, client_id, pool_id.split("_")[0]


def strong_password():
    """Meets the pool policy: >=12 chars, upper, lower, digit, symbol."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(20))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in "!@#$%^&*-_" for c in candidate)
        ):
            return candidate


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ensure_user(cognito, pool_id, email, password, group):
    """Create the user (if absent), give them a permanent password, set the group.

    A permanent password sidesteps the NEW_PASSWORD_REQUIRED challenge, leaving
    TOTP as the only interactive step.
    """
    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        say(f"  created {email}")
    except cognito.exceptions.UsernameExistsException:
        say(f"  {email} already exists")

    cognito.admin_set_user_password(
        UserPoolId=pool_id, Username=email, Password=password, Permanent=True
    )
    cognito.admin_add_user_to_group(UserPoolId=pool_id, Username=email, GroupName=group)


def challenge_username(challenge, fallback):
    return challenge.get("ChallengeParameters", {}).get("USER_ID_FOR_SRP", fallback)


def sign_in(cognito, pool_id, client_id, email, password, totp_secret):
    """Full SRP sign-in. Returns (AuthenticationResult, totp_secret)."""
    srp = AWSSRP(
        username=email,
        password=password,
        pool_id=pool_id,
        client_id=client_id,
        client=cognito,
    )
    try:
        challenge = srp.authenticate_user()
    except SoftwareTokenMFAChallengeException as exc:
        challenge = exc.get_tokens()

    name = challenge.get("ChallengeName")
    if name is None:  # MFA somehow not required — nothing left to answer
        return challenge["AuthenticationResult"], totp_secret

    if name == "MFA_SETUP":
        assoc = cognito.associate_software_token(Session=challenge["Session"])
        totp_secret = assoc["SecretCode"]
        verified = cognito.verify_software_token(
            Session=assoc["Session"],
            UserCode=pyotp.TOTP(totp_secret).now(),
            FriendlyDeviceName=DEVICE_NAME,
        )
        if verified["Status"] != "SUCCESS":
            raise RuntimeError(f"TOTP enrolment failed for {email}: {verified['Status']}")
        final = cognito.respond_to_auth_challenge(
            ClientId=client_id,
            ChallengeName="MFA_SETUP",
            Session=verified["Session"],
            ChallengeResponses={"USERNAME": challenge_username(challenge, email)},
        )
        return final["AuthenticationResult"], totp_secret

    if name == "SOFTWARE_TOKEN_MFA":
        if not totp_secret:
            raise RuntimeError(
                f"{email} already has TOTP enrolled but no secret is cached; "
                "run with --reset to recreate the users"
            )
        final = cognito.respond_to_auth_challenge(
            ClientId=client_id,
            ChallengeName="SOFTWARE_TOKEN_MFA",
            Session=challenge["Session"],
            ChallengeResponses={
                "USERNAME": challenge_username(challenge, email),
                "SOFTWARE_TOKEN_MFA_CODE": pyotp.TOTP(totp_secret).now(),
            },
        )
        return final["AuthenticationResult"], totp_secret

    raise RuntimeError(f"unexpected challenge for {email}: {name}")


def reset(cognito, pool_id, state, domain):
    targets = {e["email"] for e in state.values()}
    targets |= {f"smoke-{p}@{domain}" for p in PROFILES}

    survivors = set()
    for email in sorted(targets):
        try:
            cognito.admin_delete_user(UserPoolId=pool_id, Username=email)
            print(f"  deleted {email}")
        except cognito.exceptions.UserNotFoundException:
            pass                                            
        except ClientError as exc:
            print(f"  could not delete {email}: {exc.response['Error']['Code']}")
            survivors.add(email)

    if survivors:                                           
        print(f"  keeping {STATE_FILE.name} — still present: {', '.join(sorted(survivors))}")
    else:
        STATE_FILE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="delete the seeded users and cached state"
    )
    parser.add_argument(
        "--shell",
        choices=("powershell", "bash"),
        default="powershell" if os.name == "nt" else "bash",
        help="dialect for the printed variable assignments",
    )
    parser.add_argument(
        "--user",
        metavar="EMAIL",
        help="mint a token for this one user instead of the three profiles; "
        "creates them if absent, and sets a password on a user made via POST /createUser",
    )
    parser.add_argument(
        "--group", choices=PROFILES, help="Cognito group for --user (required with it)"
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="print nothing but the access token, for capturing into a variable",
    )
    args = parser.parse_args()

    global QUIET
    QUIET = args.token_only

    pool_id, client_id, region = config()
    cognito = boto3.client("cognito-idp", region_name=region)
    state = load_state()
    domain = os.environ.get("LIVE_TEST_EMAIL_DOMAIN", "example.com").strip()
    
    if args.reset:
        print("Removing seeded users:")
        reset(cognito, pool_id, state, domain)
        return

    if args.user:
        if not args.group:
            sys.exit("--user requires --group")
        entry = state.get(args.user) or {
            "email": args.user,
            "password": strong_password(),
            "totp_secret": None,
        }
        say(f"{args.user} ({args.group}):")
        ensure_user(cognito, pool_id, args.user, entry["password"], args.group)
        auth, entry["totp_secret"] = sign_in(
            cognito, pool_id, client_id, args.user, entry["password"], entry["totp_secret"]
        )
        state[args.user] = entry
        save_state(state)  # so --reset can clean this user up too
    
        if args.token_only:
            print(auth["AccessToken"])
        else:
            say(f"  signed in, token valid for {auth['ExpiresIn']}s\n")
            print(export_line("LIVE_TOKEN_ADHOC", auth["AccessToken"], args.shell))
        return

    exports = []
    for profile in PROFILES:
        print(f"{profile}:")
        entry = state.get(profile) or {
            "email": f"smoke-{profile}@{domain}",
            "password": strong_password(),
            "totp_secret": None,
        }
        ensure_user(cognito, pool_id, entry["email"], entry["password"], profile)

        auth, entry["totp_secret"] = sign_in(
            cognito, pool_id, client_id, entry["email"], entry["password"], entry["totp_secret"]
        )
        state[profile] = entry
        save_state(state)  # persist as we go; a failure mid-run stays resumable
        print(f"  signed in, token valid for {auth['ExpiresIn']}s")

        exports.append(
            export_line(f"LIVE_TOKEN_{profile.upper()}", auth["AccessToken"], args.shell)
        )
        if profile == "admin":
            exports.append(export_line("LIVE_ID_TOKEN_ADMIN", auth["IdToken"], args.shell))

    suffix = "ps1" if args.shell == "powershell" else "sh"
    token_file = STATE_FILE.parent / f".live-tokens.{suffix}"
    token_file.write_text("\n".join(exports) + "\n", encoding="utf-8")

    print(f"\nState cached in {STATE_FILE.name}; tokens written to {token_file.name} (both gitignored).")
    print("Tokens expire in 60 minutes — re-run this script for fresh ones.\n")
    if args.shell == "powershell":
        print(f"Load them into this session:  . .\\{token_file.name}")
    else:
        print(f"Load them into this session:  source ./{token_file.name}")


if __name__ == "__main__":
    main()
