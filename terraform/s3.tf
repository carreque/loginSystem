data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "resource" {
  bucket = "${var.project_name}-resources-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "resource" {
  bucket                  = aws_s3_bucket.resource.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "resource" {
  bucket = aws_s3_bucket.resource.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "resource" {
  bucket = aws_s3_bucket.resource.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_cloudfront_origin_access_control" "resource" {
  name                              = "${var.project_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Bucket readable only by this CloudFront distribution.
data "aws_iam_policy_document" "bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.resource.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.resource.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "resource" {
  bucket = aws_s3_bucket.resource.id
  policy = data.aws_iam_policy_document.bucket.json
}