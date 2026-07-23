module "iam" {
  source                     = "./modules/iam"
  project_name               = var.project_name
  bucket_arn                 = aws_s3_bucket.resource.arn
  user_pool_arn              = aws_cognito_user_pool.main.arn
  authorizer_log_group_arn   = aws_cloudwatch_log_group.authorizer.arn
  get_resource_log_group_arn = aws_cloudwatch_log_group.get_resource.arn
  upload_to_s3_log_group_arn = aws_cloudwatch_log_group.upload_to_s3.arn
  create_user_log_group_arn  = aws_cloudwatch_log_group.create_user.arn
}