mock_provider "aws" {}

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
