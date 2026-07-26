# Zip each function directory. The authorizer also needs PyJWT, supplied via a
# shared layer built beforehand (see README "build" note):
#   pip install -r ../src/common/requirements.txt -t terraform/build/layer/python
data "archive_file" "authorizer" {
  type        = "zip"
  source_dir  = "${path.module}/../src/authorizer"
  output_path = "${path.module}/build/authorizer.zip"
}

data "archive_file" "get_resource" {
  type        = "zip"
  source_dir  = "${path.module}/../src/get_resource"
  output_path = "${path.module}/build/get_resource.zip"
}

data "archive_file" "upload_to_s3" {
  type        = "zip"
  source_dir  = "${path.module}/../src/upload_to_s3"
  output_path = "${path.module}/build/upload_to_s3.zip"
}

data "archive_file" "create_user" {
  type        = "zip"
  source_dir  = "${path.module}/../src/create_user"
  output_path = "${path.module}/build/create_user.zip"
}

# The resource Lambdas import the shared `common` package; bundle it as a layer.
data "archive_file" "common_layer" {
  type        = "zip"
  source_dir  = "${path.module}/build/layer"
  output_path = "${path.module}/build/common-layer.zip"
}

resource "aws_lambda_layer_version" "deps" {
  layer_name          = "${var.project_name}-deps"
  filename            = data.archive_file.common_layer.output_path
  source_code_hash    = data.archive_file.common_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

resource "aws_lambda_function" "authorizer" {
  function_name    = "${var.project_name}-authorizer"
  role             = module.iam.authorizer_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.authorizer.output_path
  source_code_hash = data.archive_file.authorizer.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]
  timeout          = 10

  environment {
    variables = {
      USER_POOL_ID  = aws_cognito_user_pool.main.id
      APP_CLIENT_ID = aws_cognito_user_pool_client.portal.id
      LOG_LEVEL     = var.log_level
    }
  }
}

resource "aws_lambda_function" "get_resource" {
  function_name    = "${var.project_name}-get-resource"
  role             = module.iam.get_resource_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.get_resource.output_path
  source_code_hash = data.archive_file.get_resource.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]
  timeout          = 10

  environment {
    variables = {
      RESOURCE_BUCKET = aws_s3_bucket.resource.id
      LOG_LEVEL       = var.log_level
    }
  }
}

resource "aws_lambda_function" "upload_to_s3" {
  function_name    = "${var.project_name}-upload-to-s3"
  role             = module.iam.create_resource_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.upload_to_s3.output_path
  source_code_hash = data.archive_file.upload_to_s3.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]
  timeout          = 10

  environment {
    variables = {
      RESOURCE_BUCKET = aws_s3_bucket.resource.id
      LOG_LEVEL       = var.log_level
    }
  }
}

resource "aws_lambda_function" "create_user" {
  function_name    = "${var.project_name}-create-user"
  role             = module.iam.create_user_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.create_user.output_path
  source_code_hash = data.archive_file.create_user.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]
  timeout          = 10

  environment {
    variables = {
      USER_POOL_ID = aws_cognito_user_pool.main.id
      LOG_LEVEL    = var.log_level
    }
  }
}