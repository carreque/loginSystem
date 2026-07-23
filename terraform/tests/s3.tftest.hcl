# IAM roles/bucket policies in the root config render assume/policy JSON from
# aws_iam_policy_document; under a bare mock that JSON is invalid and fails
# provider validation. This test asserts only on the S3 bucket, so give those
# docs a valid empty-policy default. (Policy content is checked in iam.tftest.hcl.)
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "bucket_is_private_and_encrypted" {
  command = plan

  assert {
    condition     = aws_s3_bucket_public_access_block.resource.block_public_acls == true
    error_message = "block_public_acls must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.resource.block_public_policy == true
    error_message = "block_public_policy must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.resource.ignore_public_acls == true
    error_message = "ignore_public_acls must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.resource.restrict_public_buckets == true
    error_message = "restrict_public_buckets must be true"
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.resource.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "default encryption (AES256) must be enabled"
  }
  assert {
    condition     = aws_s3_bucket_versioning.resource.versioning_configuration[0].status == "Enabled"
    error_message = "versioning must be enabled"
  }
}
