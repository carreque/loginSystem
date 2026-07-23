resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${var.project_name}-authorizer"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "get_resource" {
  name              = "/aws/lambda/${var.project_name}-get-resource"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "upload_to_s3" {
  name              = "/aws/lambda/${var.project_name}-upload-to-s3"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "create_user" {
  name              = "/aws/lambda/${var.project_name}-create-user"
  retention_in_days = var.log_retention_days
}

# --- Alarm on authorizer denials (the handler logs "denying request") --------
resource "aws_cloudwatch_log_metric_filter" "auth_deny" {
  name           = "${var.project_name}-authorizer-deny"
  log_group_name = aws_cloudwatch_log_group.authorizer.name
  pattern        = "denying request"

  metric_transformation {
    name          = "AuthorizerDeny"
    namespace     = "${var.project_name}/Auth"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "auth_deny" {
  alarm_name          = "${var.project_name}-authorizer-deny-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 300
  threshold           = 10
  statistic           = "Sum"
  namespace           = "${var.project_name}/Auth"
  metric_name         = "AuthorizerDeny"
  treat_missing_data  = "notBreaching"
}

# --- CloudTrail: control-plane audit (AdminCreateUser, group changes, ...) ----
resource "aws_s3_bucket" "trail" {
  bucket        = "${var.project_name}-trail-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "trail" {
  bucket                  = aws_s3_bucket.trail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "trail" {
  statement {
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.trail.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.trail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  bucket = aws_s3_bucket.trail.id
  policy = data.aws_iam_policy_document.trail.json
}

resource "aws_cloudtrail" "main" {
  name                          = "${var.project_name}-trail"
  s3_bucket_name                = aws_s3_bucket.trail.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true

  depends_on = [aws_s3_bucket_policy.trail]
}