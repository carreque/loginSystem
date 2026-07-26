resource "aws_api_gateway_rest_api" "portal" {
  name = "${var.project_name}-api"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# Single Lambda REQUEST authorizer (JWT verify + RBAC) for every method.
resource "aws_api_gateway_authorizer" "lambda" {
  name                             = "${var.project_name}-authorizer"
  rest_api_id                      = aws_api_gateway_rest_api.portal.id
  type                             = "REQUEST"
  authorizer_uri                   = aws_lambda_function.authorizer.invoke_arn
  identity_source                  = "method.request.header.Authorization"
  authorizer_result_ttl_in_seconds = 0
}

# --- Resources: /resource/{id}, /upload, /createUser -------------------------
resource "aws_api_gateway_resource" "resource" {
  rest_api_id = aws_api_gateway_rest_api.portal.id
  parent_id   = aws_api_gateway_rest_api.portal.root_resource_id
  path_part   = "resource"
}

resource "aws_api_gateway_resource" "resource_id" {
  rest_api_id = aws_api_gateway_rest_api.portal.id
  parent_id   = aws_api_gateway_resource.resource.id
  path_part   = "{id}"
}

resource "aws_api_gateway_resource" "upload" {
  rest_api_id = aws_api_gateway_rest_api.portal.id
  parent_id   = aws_api_gateway_rest_api.portal.root_resource_id
  path_part   = "upload"
}

resource "aws_api_gateway_resource" "create_user" {
  rest_api_id = aws_api_gateway_rest_api.portal.id
  parent_id   = aws_api_gateway_rest_api.portal.root_resource_id
  path_part   = "createUser"
}

# --- GET /resource/{id} ------------------------------------------------------
resource "aws_api_gateway_method" "get_resource" {
  rest_api_id   = aws_api_gateway_rest_api.portal.id
  resource_id   = aws_api_gateway_resource.resource_id.id
  http_method   = "GET"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "get_resource" {
  rest_api_id             = aws_api_gateway_rest_api.portal.id
  resource_id             = aws_api_gateway_resource.resource_id.id
  http_method             = aws_api_gateway_method.get_resource.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.get_resource.invoke_arn
}

# --- POST /upload ------------------------------------------------------------
resource "aws_api_gateway_method" "upload" {
  rest_api_id   = aws_api_gateway_rest_api.portal.id
  resource_id   = aws_api_gateway_resource.upload.id
  http_method   = "POST"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "upload" {
  rest_api_id             = aws_api_gateway_rest_api.portal.id
  resource_id             = aws_api_gateway_resource.upload.id
  http_method             = aws_api_gateway_method.upload.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.upload_to_s3.invoke_arn
}

# --- POST /createUser --------------------------------------------------------
resource "aws_api_gateway_method" "create_user" {
  rest_api_id   = aws_api_gateway_rest_api.portal.id
  resource_id   = aws_api_gateway_resource.create_user.id
  http_method   = "POST"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "create_user" {
  rest_api_id             = aws_api_gateway_rest_api.portal.id
  resource_id             = aws_api_gateway_resource.create_user.id
  http_method             = aws_api_gateway_method.create_user.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.create_user.invoke_arn
}

# --- Deployment + stage ------------------------------------------------------
resource "aws_api_gateway_deployment" "portal" {
  rest_api_id = aws_api_gateway_rest_api.portal.id

  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_integration.get_resource.id,
      aws_api_gateway_integration.upload.id,
      aws_api_gateway_integration.create_user.id,
      aws_api_gateway_authorizer.lambda.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.portal.id
  deployment_id = aws_api_gateway_deployment.portal.id
  stage_name    = "prod"
}

# Throttling on every method (rate + burst) — gap #5 / A06.
resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.portal.id
  stage_name  = aws_api_gateway_stage.prod.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.api_throttle_rate_limit
    throttling_burst_limit = var.api_throttle_burst_limit
  }
}


# --- Permissions: let API Gateway invoke the authorizer + each function ------
resource "aws_lambda_permission" "authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.portal.execution_arn}/authorizers/${aws_api_gateway_authorizer.lambda.id}"
}

resource "aws_lambda_permission" "get_resource" {
  statement_id  = "AllowAPIGatewayInvokeGetResource"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_resource.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.portal.execution_arn}/*/GET/resource/*"
}

resource "aws_lambda_permission" "upload" {
  statement_id  = "AllowAPIGatewayInvokeUpload"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.upload_to_s3.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.portal.execution_arn}/*/POST/upload"
}

resource "aws_lambda_permission" "create_user" {
  statement_id  = "AllowAPIGatewayInvokeCreateUser"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.create_user.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.portal.execution_arn}/*/POST/createUser"
}