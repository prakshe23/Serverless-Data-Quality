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

variable "workflow_type" {
  description = <<-EOT
    Step Functions workflow type. STANDARD is free-tier eligible (4,000
    state transitions/month, roughly 350 pipeline runs); EXPRESS is cheaper
    at high volume but has no free tier.
  EOT
  type        = string
  default     = "STANDARD"

  validation {
    condition     = contains(["STANDARD", "EXPRESS"], var.workflow_type)
    error_message = "workflow_type must be STANDARD or EXPRESS."
  }
}

variable "pii_detection_mode" {
  description = <<-EOT
    "comprehend" uses Amazon Comprehend (free for 12 months up to 50K units
    per month, then paid). "regex" uses built-in pattern matching with Luhn
    validation - less accurate, but free forever.
  EOT
  type        = string
  default     = "comprehend"

  validation {
    condition     = contains(["comprehend", "regex"], var.pii_detection_mode)
    error_message = "pii_detection_mode must be comprehend or regex."
  }
}

variable "enable_curated_crawler" {
  description = "Run a scheduled Glue crawler over curated/. Crawler runs are billed per DPU-hour (not free tier); the metrics table needs no crawler."
  type        = bool
  default     = false
}

variable "emit_dimension_metrics" {
  description = "Also publish per-dimension CloudWatch metrics (4 extra custom metrics per dataset; the always-free tier covers 10 total)."
  type        = bool
  default     = false
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
