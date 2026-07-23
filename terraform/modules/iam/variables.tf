variable "project_name" {
  description = "Project name; prefixes the four execution-role names (e.g. \"<project>-authorizer-role\")."
  type        = string
}

variable "bucket_arn" {
  description = "ARN of the S3 resource bucket. Scopes s3:GetObject (get-resource) and s3:PutObject (create-resource) to \"<bucket_arn>/*\"."
  type        = string
}

variable "user_pool_arn" {
  description = "ARN of the Cognito user pool. Scopes the create-user role's AdminCreateUser / AdminAddUserToGroup actions to this pool."
  type        = string
}

variable "authorizer_log_group_arn" {
  description = "CloudWatch log group ARN for the authorizer Lambda; the authorizer role may only write logs here."
  type        = string
}

variable "get_resource_log_group_arn" {
  description = "CloudWatch log group ARN for the get_resource Lambda; scopes the get-resource role's log-write permission."
  type        = string
}

variable "upload_to_s3_log_group_arn" {
  description = "CloudWatch log group ARN for the upload_to_s3 Lambda; scopes the create-resource role's log-write permission."
  type        = string
}

variable "create_user_log_group_arn" {
  description = "CloudWatch log group ARN for the create_user Lambda; scopes the create-user role's log-write permission."
  type        = string
}
