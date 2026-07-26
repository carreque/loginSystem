# Phase 7 (gap #4, second half): the S3 origin is served only through CloudFront
# via Origin Access Control, over HTTPS. IAM roles/bucket policies in the root
# config render assume/policy JSON from aws_iam_policy_document; under a bare mock
# that JSON is invalid and fails provider validation, so give those docs a valid
# empty-policy default (same as s3.tftest.hcl). This test asserts only on the OAC
# and the distribution structure.
#
# NOTE: the "only this CloudFront distribution may read the bucket" control lives
# in data.aws_iam_policy_document.bucket.json, which depends on the not-yet-created
# aws_cloudfront_distribution.resource.arn and therefore does NOT render at plan
# (see Session 4). Its *content* (the cloudfront.amazonaws.com principal + the
# AWS:SourceArn condition) is not asserted here; only the OAC/distribution wiring is.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "origin_served_only_via_oac_over_https" {
  command = plan

  # --- Origin Access Control is configured for a SigV4-signed S3 origin --------
  assert {
    condition     = aws_cloudfront_origin_access_control.resource.origin_access_control_origin_type == "s3"
    error_message = "OAC origin type must be s3"
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.resource.signing_behavior == "always"
    error_message = "OAC signing_behavior must be 'always' (every request signed)"
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.resource.signing_protocol == "sigv4"
    error_message = "OAC signing_protocol must be sigv4"
  }

  # NOTE: whether the distribution's origin is bound to this OAC cannot be
  # asserted at plan — origin_access_control_id resolves to
  # aws_cloudfront_origin_access_control.resource.id, a computed attribute that is
  # unknown until apply (Terraform reports "Unknown condition value"). Asserting it
  # would require command = apply. The OAC config above is the plan-knowable control.

  # --- Viewers are forced onto HTTPS ------------------------------------------
  assert {
    condition     = aws_cloudfront_distribution.resource.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "viewer_protocol_policy must redirect viewers to HTTPS"
  }
}
