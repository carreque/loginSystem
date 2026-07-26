# Phase 6 (gap #5, A06): the three routes are fronted by a REST API whose methods
# all delegate authorization to the single Lambda REQUEST authorizer, and the API
# is rate-limited at the stage.
#
# Interface asserted (names match apigateway.tf):
#   aws_api_gateway_authorizer.lambda      # type = REQUEST, identity source = Authorization header
#   aws_api_gateway_method.get_resource    # GET  /resource/{id}
#   aws_api_gateway_method.upload          # POST /upload
#   aws_api_gateway_method.create_user     # POST /createUser
#   aws_api_gateway_method_settings.all    # stage throttling from the api_throttle_* vars
#
# IAM roles/bucket policies in the root config render assume/policy JSON from
# aws_iam_policy_document; under a bare mock that JSON is invalid and fails provider
# validation, so give those docs a valid empty-policy default (same as the other
# tftest files). This test asserts only on the API Gateway resources.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "methods_use_custom_authorizer_and_api_is_throttled" {
  command = plan

  # --- Single Lambda REQUEST authorizer, reading the Authorization header ------
  assert {
    condition     = aws_api_gateway_authorizer.lambda.type == "REQUEST"
    error_message = "the authorizer must be a REQUEST (Lambda) authorizer, not TOKEN"
  }
  assert {
    condition     = aws_api_gateway_authorizer.lambda.identity_source == "method.request.header.Authorization"
    error_message = "the authorizer identity source must be the Authorization header"
  }

  # --- Every route delegates authorization to the custom authorizer -----------
  # NOTE: the *binding* (method.authorizer_id == aws_api_gateway_authorizer.lambda.id)
  # cannot be asserted at plan — authorizer_id resolves to the authorizer's computed
  # id, unknown until apply. authorization == "CUSTOM" is the plan-knowable control.
  assert {
    condition     = aws_api_gateway_method.get_resource.authorization == "CUSTOM"
    error_message = "GET /resource/{id} must use the custom authorizer"
  }
  assert {
    condition     = aws_api_gateway_method.upload.authorization == "CUSTOM"
    error_message = "POST /upload must use the custom authorizer"
  }
  assert {
    condition     = aws_api_gateway_method.create_user.authorization == "CUSTOM"
    error_message = "POST /createUser must use the custom authorizer"
  }

  # --- Methods match the route -> group matrix's HTTP verbs -------------------
  assert {
    condition     = aws_api_gateway_method.get_resource.http_method == "GET"
    error_message = "getResource must be wired to GET"
  }
  assert {
    condition     = aws_api_gateway_method.upload.http_method == "POST"
    error_message = "uploadToS3 must be wired to POST"
  }
  assert {
    condition     = aws_api_gateway_method.create_user.http_method == "POST"
    error_message = "createUser must be wired to POST"
  }

  # --- Rate limiting at the stage (A06) ---------------------------------------
  assert {
    condition     = aws_api_gateway_method_settings.all.settings[0].throttling_rate_limit == var.api_throttle_rate_limit
    error_message = "stage steady-state rate limit must come from api_throttle_rate_limit"
  }
  assert {
    condition     = aws_api_gateway_method_settings.all.settings[0].throttling_burst_limit == var.api_throttle_burst_limit
    error_message = "stage burst limit must come from api_throttle_burst_limit"
  }
}
