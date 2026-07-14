variable "project_name" {
  description = "Name used to prefix every resource."
  type        = string
  default     = "data-quality"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to deploy into. Comprehend must be available here."
  type        = string
  default     = "us-east-1"
}

variable "alert_email" {
  description = "Email address subscribed to quality alerts. Empty disables the subscription."
  type        = string
  default     = ""
}

variable "pass_threshold" {
  description = "Overall score at or above which a file is PASSED."
  type        = number
  default     = 0.8
}

variable "warn_threshold" {
  description = "Overall score below which a file is FAILED (between warn and pass it is WARNED)."
  type        = number
  default     = 0.6
}

variable "lambda_memory_mb" {
  description = "Memory for the check Lambdas."
  type        = number
  default     = 512
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for all pipeline log groups."
  type        = number
  default     = 30
}
