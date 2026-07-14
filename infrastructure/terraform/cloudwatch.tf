# Alarm when any dataset records a failed run.
resource "aws_cloudwatch_metric_alarm" "quality_failures" {
  alarm_name          = "${local.name_prefix}-failures"
  alarm_description   = "A file failed data quality checks"
  namespace           = "DataQuality/${var.environment}"
  metric_name         = "Failed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.quality_alerts.arn]
}

# Alarm on workflow crashes (distinct from quality failures).
resource "aws_cloudwatch_metric_alarm" "workflow_errors" {
  alarm_name          = "${local.name_prefix}-workflow-errors"
  alarm_description   = "Data quality Step Functions executions are failing"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.data_quality.arn
  }

  alarm_actions = [aws_sns_topic.quality_alerts.arn]
}

locals {
  # Only shown when per-dimension metrics are enabled (they cost extra
  # custom metrics; see var.emit_dimension_metrics).
  dimension_widget = {
    type   = "metric"
    x      = 12
    y      = 6
    width  = 12
    height = 6
    properties = {
      title  = "Dimension scores"
      region = var.aws_region
      stat   = "Average"
      period = 3600
      metrics = [
        ["DataQuality/${var.environment}", "Score.schema"],
        [".", "Score.profile"],
        [".", "Score.pii"],
        [".", "Score.anomaly"]
      ]
      yAxis = { left = { min = 0, max = 1 } }
    }
  }
}

resource "aws_cloudwatch_dashboard" "quality" {
  dashboard_name = "${local.name_prefix}-overview"

  dashboard_body = jsonencode({
    widgets = concat([
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Overall quality score"
          region = var.aws_region
          stat   = "Average"
          period = 3600
          metrics = [
            ["DataQuality/${var.environment}", "OverallScore"]
          ]
          yAxis = { left = { min = 0, max = 1 } }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Failed files"
          region = var.aws_region
          stat   = "Sum"
          period = 3600
          metrics = [
            ["DataQuality/${var.environment}", "Failed"]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Workflow executions"
          region = var.aws_region
          stat   = "Sum"
          period = 3600
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", aws_sfn_state_machine.data_quality.arn],
            [".", "ExecutionsSucceeded", ".", "."],
            [".", "ExecutionsFailed", ".", "."]
          ]
        }
      }
    ], var.emit_dimension_metrics ? [local.dimension_widget] : [])
  })
}
