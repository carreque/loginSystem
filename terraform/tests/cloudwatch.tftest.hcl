# Phase 8 (gap #6): per-Lambda log groups with retention, an alarm on authorizer
# denials, and a multi-region CloudTrail with log-file validation for the
# control-plane audit trail. IAM roles/bucket policies in the root config render
# assume/policy JSON from aws_iam_policy_document; under a bare mock that JSON is
# invalid and fails provider validation, so give those docs a valid empty-policy
# default (same as s3.tftest.hcl). This test asserts only on the observability stack.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "observability_stack_is_wired" {
  command = plan

  # --- Every Lambda log group sets retention (no indefinite retention) ---------
  assert {
    condition     = aws_cloudwatch_log_group.authorizer.retention_in_days == var.log_retention_days
    error_message = "authorizer log group must set retention_in_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.get_resource.retention_in_days == var.log_retention_days
    error_message = "get_resource log group must set retention_in_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.upload_to_s3.retention_in_days == var.log_retention_days
    error_message = "upload_to_s3 log group must set retention_in_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.create_user.retention_in_days == var.log_retention_days
    error_message = "create_user log group must set retention_in_days"
  }

  # --- Denials the authorizer logs are turned into a metric and alarmed --------
  assert {
    condition     = aws_cloudwatch_log_metric_filter.auth_deny.pattern == "denying request"
    error_message = "metric filter must match the authorizer's 'denying request' log line"
  }
  assert {
    condition     = aws_cloudwatch_log_metric_filter.auth_deny.metric_transformation[0].name == "AuthorizerDeny"
    error_message = "metric filter must emit the AuthorizerDeny metric"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.auth_deny.metric_name == "AuthorizerDeny"
    error_message = "alarm must watch the AuthorizerDeny metric"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.auth_deny.comparison_operator == "GreaterThanThreshold"
    error_message = "alarm must fire when denials exceed the threshold"
  }

  # --- CloudTrail: multi-region, tamper-evident control-plane audit ------------
  assert {
    condition     = aws_cloudtrail.main.is_multi_region_trail == true
    error_message = "CloudTrail must be multi-region"
  }
  assert {
    condition     = aws_cloudtrail.main.include_global_service_events == true
    error_message = "CloudTrail must include global service events (e.g. IAM/Cognito)"
  }
  assert {
    condition     = aws_cloudtrail.main.enable_log_file_validation == true
    error_message = "CloudTrail must enable log-file validation (tamper detection)"
  }

  # --- The trail's own bucket is not public -----------------------------------
  assert {
    condition     = aws_s3_bucket_public_access_block.trail.block_public_acls == true
    error_message = "trail bucket block_public_acls must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.trail.block_public_policy == true
    error_message = "trail bucket block_public_policy must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.trail.ignore_public_acls == true
    error_message = "trail bucket ignore_public_acls must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.trail.restrict_public_buckets == true
    error_message = "trail bucket restrict_public_buckets must be true"
  }
}
