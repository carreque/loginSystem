# Values needed after `terraform apply` to seed users and run live end-to-end
# tests (login -> access token -> authorized API call).

output "user_pool_id" {
  description = "Cognito user pool ID (for AdminCreateUser / AdminAddUserToGroup)."
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_arn" {
  description = "Cognito user pool ARN."
  value       = aws_cognito_user_pool.main.arn
}

output "app_client_id" {
  description = "Cognito app client ID; also the `aud` the authorizer verifies."
  value       = aws_cognito_user_pool_client.portal.id
}

output "token_issuer" {
  description = "Expected `iss` claim / JWKS base URL for the user pool."
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}

output "api_invoke_url" {
  description = "Base invoke URL of the deployed stage (append /resource/{id}, /upload, /createUser)."
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "resource_bucket_name" {
  description = "S3 bucket backing POST /upload; must not be publicly readable."
  value       = aws_s3_bucket.resource.bucket
}

output "cloudfront_domain_name" {
  description = "CloudFront domain fronting the resource bucket (the only public read path)."
  value       = aws_cloudfront_distribution.resource.domain_name
}

output "lambda_function_names" {
  description = "Deployed Lambda names, for tailing CloudWatch logs after a live test."
  value = {
    authorizer   = aws_lambda_function.authorizer.function_name
    get_resource = aws_lambda_function.get_resource.function_name
    upload_to_s3 = aws_lambda_function.upload_to_s3.function_name
    create_user  = aws_lambda_function.create_user.function_name
  }
}
