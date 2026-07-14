resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.name_prefix}-workflow"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "data_quality" {
  name     = "${local.name_prefix}-workflow"
  role_arn = aws_iam_role.sfn.arn
  type     = var.workflow_type

  definition = templatefile("${path.module}/templates/data_quality_workflow.asl.json", {
    schema_validator_arn = aws_lambda_function.functions["schema_validator"].arn
    data_profiler_arn    = aws_lambda_function.functions["data_profiler"].arn
    pii_detector_arn     = aws_lambda_function.functions["pii_detector"].arn
    anomaly_detector_arn = aws_lambda_function.functions["anomaly_detector"].arn
    quality_scorer_arn   = aws_lambda_function.functions["quality_scorer"].arn
    results_writer_arn   = aws_lambda_function.functions["results_writer"].arn
    remediation_arn      = aws_lambda_function.functions["remediation"].arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }
}
