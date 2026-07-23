data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Scoped CloudWatch Logs statement, reused per role against that function's group.
locals {
  log_actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
}

# --- authorizer-role: logs only ----------------------------------------------
resource "aws_iam_role" "authorizer" {
  name               = "${var.project_name}-authorizer-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "authorizer" {
  statement {
    actions   = local.log_actions
    resources = ["${var.authorizer_log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "authorizer" {
  name   = "authorizer-inline"
  role   = aws_iam_role.authorizer.id
  policy = data.aws_iam_policy_document.authorizer.json
}

# --- get-resource-role: s3:GetObject + logs ----------------------------------
resource "aws_iam_role" "get_resource" {
  name               = "${var.project_name}-get-resource-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "get_resource" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    actions   = local.log_actions
    resources = ["${var.get_resource_log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "get_resource" {
  name   = "get-resource-inline"
  role   = aws_iam_role.get_resource.id
  policy = data.aws_iam_policy_document.get_resource.json
}

# --- create-resource-role: s3:PutObject + logs (used by upload_to_s3) --------
resource "aws_iam_role" "create_resource" {
  name               = "${var.project_name}-create-resource-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "create_resource" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    actions   = local.log_actions
    resources = ["${var.upload_to_s3_log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "create_resource" {
  name   = "create-resource-inline"
  role   = aws_iam_role.create_resource.id
  policy = data.aws_iam_policy_document.create_resource.json
}

# --- create-user-role: AdminCreateUser + AdminAddUserToGroup + logs ----------
resource "aws_iam_role" "create_user" {
  name               = "${var.project_name}-create-user-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "create_user" {
  statement {
    actions   = ["cognito-idp:AdminCreateUser", "cognito-idp:AdminAddUserToGroup"]
    resources = [var.user_pool_arn]
  }
  statement {
    actions   = local.log_actions
    resources = ["${var.create_user_log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "create_user" {
  name   = "create-user-inline"
  role   = aws_iam_role.create_user.id
  policy = data.aws_iam_policy_document.create_user.json
}