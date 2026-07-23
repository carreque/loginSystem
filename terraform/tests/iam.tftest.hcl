# Least-privilege assertions inspect the *rendered* policy JSON
# (strcontains on data.aws_iam_policy_document.*.json). That only renders when
# the policy inputs are known at plan and carry no pending-resource dependency,
# so we test the IAM logic as an isolated module (modules/iam) fed ARN
# *variables* rather than live resource references. The offline provider
# (skip_* + dummy creds) lets `plan` run with no AWS account.
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

run "roles_are_least_privilege" {
  command = plan

  # Drive the child module directly; it becomes the root module for this run,
  # so its data.aws_iam_policy_document.* documents are addressable below.
  module {
    source = "./modules/iam"
  }

  # Interface the module must expose (project_name + one ARN per dependency).
  variables {
    project_name               = "employee-portal-auth"
    bucket_arn                 = "arn:aws:s3:::employee-portal-auth-resources-123456789012"
    user_pool_arn              = "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST"
    authorizer_log_group_arn   = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/employee-portal-auth-authorizer"
    get_resource_log_group_arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/employee-portal-auth-get-resource"
    upload_to_s3_log_group_arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/employee-portal-auth-upload-to-s3"
    create_user_log_group_arn  = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/employee-portal-auth-create-user"
  }

  # get-resource: exactly s3:GetObject (+ scoped logs), no wildcards.
  assert {
    condition     = strcontains(data.aws_iam_policy_document.get_resource.json, "s3:GetObject")
    error_message = "get-resource role must allow s3:GetObject"
  }
  assert {
    condition     = !strcontains(data.aws_iam_policy_document.get_resource.json, "\"*\"")
    error_message = "get-resource role must not contain a wildcard action/resource"
  }

  # create-resource (upload): s3:PutObject only.
  assert {
    condition     = strcontains(data.aws_iam_policy_document.create_resource.json, "s3:PutObject")
    error_message = "create-resource role must allow s3:PutObject"
  }
  assert {
    condition     = !strcontains(data.aws_iam_policy_document.create_resource.json, "\"*\"")
    error_message = "create-resource role must not contain a wildcard"
  }

  # create-user: the two Cognito admin actions only.
  assert {
    condition     = strcontains(data.aws_iam_policy_document.create_user.json, "cognito-idp:AdminCreateUser")
    error_message = "create-user role must allow AdminCreateUser"
  }
  assert {
    condition     = strcontains(data.aws_iam_policy_document.create_user.json, "cognito-idp:AdminAddUserToGroup")
    error_message = "create-user role must allow AdminAddUserToGroup"
  }
  assert {
    condition     = !strcontains(data.aws_iam_policy_document.create_user.json, "\"*\"")
    error_message = "create-user role must not contain a wildcard"
  }

  # authorizer: logs only (present), and no wildcards.
  assert {
    condition     = strcontains(data.aws_iam_policy_document.authorizer.json, "logs:PutLogEvents")
    error_message = "authorizer role must allow logs:PutLogEvents"
  }
  assert {
    condition     = !strcontains(data.aws_iam_policy_document.authorizer.json, "\"*\"")
    error_message = "authorizer role must not contain a wildcard"
  }
}
