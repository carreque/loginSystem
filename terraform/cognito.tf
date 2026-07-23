
resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-pool"
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 1
  }

  # Breached-password detection + adaptive auth (gap #7).
  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  # TOTP MFA available; step-up for admin/supervisor is enforced at the app layer.
  mfa_configuration = "ON"
  software_token_mfa_configuration {
    enabled = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }
}

# Three employee profiles. Lower precedence = higher priority.
resource "aws_cognito_user_group" "empleado" {
  name         = "empleado"
  user_pool_id = aws_cognito_user_pool.main.id
  precedence   = 30
}

resource "aws_cognito_user_group" "supervisor" {
  name         = "supervisor"
  user_pool_id = aws_cognito_user_pool.main.id
  precedence   = 20
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.main.id
  precedence   = 10
}

resource "aws_cognito_user_pool_client" "portal" {
  name         = "${var.project_name}-portal"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  # Authorization-code grant only; implicit flow disabled (A07).
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  access_token_validity = var.access_token_validity_minutes
  token_validity_units {
    access_token = "minutes"
  }

  prevent_user_existence_errors = "ENABLED"
}