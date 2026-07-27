"""Does the deployed account actually match the hardening the config promises?

`terraform test` asserts the *plan*; these assert the *account*. They overlap on
purpose — the point is catching a deploy that silently diverged (a stale layer,
a half-applied stage, a distribution still propagating). All read-only apart
from one direct Lambda invoke and one seeded S3 object.
"""
from __future__ import annotations

import json
import uuid

import boto3
import pytest
import requests

pytestmark = pytest.mark.live

TIMEOUT = 20


# --- The layer actually loads on Linux -------------------------------------
def test_authorizer_lambda_imports_its_dependencies(live):
    """Invoke the authorizer directly: a Deny proves PyJWT/cryptography imported.

    This is the check that catches a layer built with Windows or wrong-Python
    wheels — that failure mode surfaces as Runtime.ImportModuleError, which
    through the API would look like an ordinary deny.
    """
    lam = boto3.client("lambda", region_name=live["region"])
    event = {
        "methodArn": (
            f"arn:aws:execute-api:{live['region']}:000000000000:"
            f"{live['rest_api_id']}/{live['stage']}/GET/resource/demo"
        ),
        "headers": {},
    }
    result = lam.invoke(
        FunctionName=f"{live['project']}-authorizer",
        Payload=json.dumps(event).encode(),
    )
    payload = json.loads(result["Payload"].read())
    assert "FunctionError" not in result, payload
    effect = payload["policyDocument"]["Statement"][0]["Effect"]
    assert effect == "Deny"


def test_lambdas_run_the_expected_runtime_and_layer(live):
    lam = boto3.client("lambda", region_name=live["region"])
    for name in ("authorizer", "get-resource", "upload-to-s3", "create-user"):
        cfg = lam.get_function_configuration(FunctionName=f"{live['project']}-{name}")
        assert cfg["Runtime"] == "python3.12", name
        assert cfg.get("Layers"), f"{name} has no layer attached"


def test_authorizer_knows_the_pool_it_must_verify_against(live):
    lam = boto3.client("lambda", region_name=live["region"])
    env = lam.get_function_configuration(
        FunctionName=f"{live['project']}-authorizer"
    )["Environment"]["Variables"]
    assert env["USER_POOL_ID"] == live["user_pool_id"]
    assert env["APP_CLIENT_ID"] == live["app_client_id"]


# --- S3 is private; CloudFront is the only public path ----------------------
def test_bucket_blocks_all_public_access(live):
    s3 = boto3.client("s3", region_name=live["region"])
    cfg = s3.get_public_access_block(Bucket=live["bucket"])["PublicAccessBlockConfiguration"]
    assert all(cfg.values()), cfg


def test_bucket_is_encrypted(live):
    s3 = boto3.client("s3", region_name=live["region"])
    rules = s3.get_bucket_encryption(Bucket=live["bucket"])[
        "ServerSideEncryptionConfiguration"
    ]["Rules"]
    assert rules, "no default encryption configured"


def test_object_is_unreachable_directly_but_served_via_cloudfront(live):
    """The OAC bucket policy must be the only read path.

    A freshly created distribution can take several minutes to propagate; a
    403/404 from CloudFront right after apply may just mean "not deployed yet".
    """
    s3 = boto3.client("s3", region_name=live["region"])
    key = f"resources/public-check-{uuid.uuid4().hex[:8]}"
    s3.put_object(Bucket=live["bucket"], Key=key, Body=b"cdn-only", ContentType="text/plain")
    try:
        direct = requests.get(
            f"https://{live['bucket']}.s3.{live['region']}.amazonaws.com/{key}",
            timeout=TIMEOUT,
        )
        assert direct.status_code == 403, "bucket object is publicly readable"

        through_cdn = requests.get(
            f"https://{live['cloudfront_domain']}/{key}", timeout=TIMEOUT
        )
        assert through_cdn.status_code == 200, through_cdn.text
        assert through_cdn.text == "cdn-only"
    finally:
        s3.delete_object(Bucket=live["bucket"], Key=key)


# --- Cognito ---------------------------------------------------------------
def test_user_pool_password_and_mfa_hardening(live):
    cognito = boto3.client("cognito-idp", region_name=live["region"])
    pool = cognito.describe_user_pool(UserPoolId=live["user_pool_id"])["UserPool"]
    assert pool["Policies"]["PasswordPolicy"]["MinimumLength"] >= 12
    assert pool["MfaConfiguration"] == "ON"
    assert pool["UserPoolAddOns"]["AdvancedSecurityMode"] == "ENFORCED"


def test_the_three_profiles_exist(live):
    cognito = boto3.client("cognito-idp", region_name=live["region"])
    groups = cognito.list_groups(UserPoolId=live["user_pool_id"])["Groups"]
    assert {g["GroupName"] for g in groups} == {"empleado", "supervisor", "admin"}


def test_app_client_disallows_implicit_and_password_flows(live):
    cognito = boto3.client("cognito-idp", region_name=live["region"])
    client = cognito.describe_user_pool_client(
        UserPoolId=live["user_pool_id"], ClientId=live["app_client_id"]
    )["UserPoolClient"]
    assert client["AllowedOAuthFlows"] == ["code"]
    assert "implicit" not in client["AllowedOAuthFlows"]
    assert "ALLOW_USER_PASSWORD_AUTH" not in client["ExplicitAuthFlows"]
    assert client["AccessTokenValidity"] <= 60


# --- API Gateway -----------------------------------------------------------
@pytest.mark.parametrize(
    ("http_method", "path"),
    [("GET", "/resource/{id}"), ("POST", "/upload"), ("POST", "/createUser")],
)
def test_every_method_is_behind_the_custom_authorizer(live, http_method, path):
    api = boto3.client("apigateway", region_name=live["region"])
    resources = api.get_resources(restApiId=live["rest_api_id"], limit=500)["items"]
    match = next((r for r in resources if r["path"] == path), None)
    assert match is not None, f"{path} is not deployed"

    method = api.get_method(
        restApiId=live["rest_api_id"], resourceId=match["id"], httpMethod=http_method
    )
    assert method["authorizationType"] == "CUSTOM"
    assert method.get("authorizerId"), f"{http_method} {path} has no authorizer bound"


def test_stage_throttling_is_in_force(live):
    api = boto3.client("apigateway", region_name=live["region"])
    stage = api.get_stage(restApiId=live["rest_api_id"], stageName=live["stage"])
    settings = stage["methodSettings"].get("*/*", {})
    assert settings.get("throttlingRateLimit", 0) > 0, stage["methodSettings"]
    assert settings.get("throttlingBurstLimit", 0) > 0, stage["methodSettings"]


# --- Observability ---------------------------------------------------------
def test_log_groups_have_retention(live):
    logs = boto3.client("logs", region_name=live["region"])
    found = logs.describe_log_groups(
        logGroupNamePrefix=f"/aws/lambda/{live['project']}-"
    )["logGroups"]
    assert len(found) >= 4, [g["logGroupName"] for g in found]
    for group in found:
        assert group.get("retentionInDays"), f"{group['logGroupName']} retains forever"


def test_deny_alarm_exists(live):
    cw = boto3.client("cloudwatch", region_name=live["region"])
    alarms = cw.describe_alarms(AlarmNamePrefix=live["project"])["MetricAlarms"]
    assert alarms, "no authorizer-deny alarm deployed"


def test_cloudtrail_is_logging(live):
    trail = boto3.client("cloudtrail", region_name=live["region"])
    trails = [t for t in trail.describe_trails()["trailList"] if live["project"] in t["Name"]]
    assert trails, "no CloudTrail for this project"
    status = trail.get_trail_status(Name=trails[0]["TrailARN"])
    assert status["IsLogging"], "trail exists but is not logging"
