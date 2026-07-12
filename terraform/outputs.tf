# Outputs are added as resources land in later phases, e.g.:
#   - user_pool_id / app_client_id      (Phase 4, cognito.tf)
#   - api_invoke_url                     (Phase 6, apigateway.tf)
#   - resource_bucket_name               (Phase 7, s3_cloudfront.tf)
#   - cloudfront_domain_name             (Phase 7, s3_cloudfront.tf)
#
# Intentionally empty during Phase 1 scaffolding.
