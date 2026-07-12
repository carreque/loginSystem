variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name; used for resource naming and tagging."
  type        = string
  default     = "employee-portal-auth"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "portal_origin" {
  description = "Front-end portal origin allowed by CORS (e.g. https://portal.example.com)."
  type        = string
  default     = "http://localhost:3000"
}

variable "callback_urls" {
  description = "Allowed OAuth callback URLs for the Cognito app client."
  type        = list(string)
  default     = ["http://localhost:3000/callback"]
}

variable "logout_urls" {
  description = "Allowed OAuth logout URLs for the Cognito app client."
  type        = list(string)
  default     = ["http://localhost:3000/logout"]
}

variable "log_level" {
  description = "Log level for Lambda functions."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of DEBUG, INFO, WARNING, ERROR."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention, in days."
  type        = number
  default     = 30
}

variable "access_token_validity_minutes" {
  description = "Cognito access token validity, in minutes (5 min - 24 h)."
  type        = number
  default     = 60

  validation {
    condition     = var.access_token_validity_minutes >= 5 && var.access_token_validity_minutes <= 1440
    error_message = "access_token_validity_minutes must be between 5 and 1440."
  }
}

variable "api_throttle_rate_limit" {
  description = "API Gateway steady-state requests per second (usage plan)."
  type        = number
  default     = 50
}

variable "api_throttle_burst_limit" {
  description = "API Gateway burst request limit (usage plan)."
  type        = number
  default     = 100
}
