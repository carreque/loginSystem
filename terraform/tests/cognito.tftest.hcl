# IAM roles/bucket policies in the root config render assume/policy JSON from
# aws_iam_policy_document; under a bare mock that JSON is invalid and fails
# provider validation. This test asserts only on Cognito, so give those docs a
# valid empty-policy default. (Policy *content* is checked in iam.tftest.hcl.)
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "cognito_hardening" {
  command = plan

  assert {
    condition     = aws_cognito_user_pool.main.password_policy[0].minimum_length >= 12
    error_message = "password minimum length must be >= 12"
  }
  assert {
    condition     = aws_cognito_user_pool.main.user_pool_add_ons[0].advanced_security_mode == "ENFORCED"
    error_message = "advanced security (breached-password) must be ENFORCED"
  }
  assert {
    condition     = contains(aws_cognito_user_pool_client.portal.allowed_oauth_flows, "code")
    error_message = "authorization-code flow must be enabled"
  }
  assert {
    condition     = !contains(aws_cognito_user_pool_client.portal.allowed_oauth_flows, "implicit")
    error_message = "implicit grant must be disabled"
  }
}
