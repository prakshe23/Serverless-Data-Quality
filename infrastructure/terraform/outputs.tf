output "lake_bucket" {
  description = "Data lake bucket. Drop files under raw/<dataset>/ to run the pipeline."
  value       = aws_s3_bucket.lake.bucket
}

output "config_bucket" {
  description = "Upload schema contracts to schemas/<dataset>.json here."
  value       = aws_s3_bucket.config.bucket
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.data_quality.arn
}

output "api_endpoint" {
  description = "Quality reports REST API."
  value       = aws_apigatewayv2_api.quality.api_endpoint
}

output "runs_table" {
  value = aws_dynamodb_table.runs.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.quality.name
}

output "glue_database" {
  value = aws_glue_catalog_database.quality.name
}

output "alerts_topic_arn" {
  value = aws_sns_topic.quality_alerts.arn
}

output "dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.quality.dashboard_name}"
}
