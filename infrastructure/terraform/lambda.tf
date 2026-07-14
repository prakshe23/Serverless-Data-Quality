locals {
  lambda_runtime = "python3.12"
  lambda_src     = "${path.module}/../../src/lambdas"

  # Environment shared by every function; per-function extras below.
  common_env = {
    RUNS_TABLE        = aws_dynamodb_table.runs.name
    METRICS_NAMESPACE = "DataQuality/${var.environment}"
  }

  # Every function except ingestion_trigger, which is declared separately:
  # it depends on the state machine, which depends on these functions, so
  # keeping it in this map would create a resource-graph cycle.
  lambda_functions = {
    schema_validator = {
      description = "Checks files against their dataset schema contract"
      timeout     = 60
      env = {
        CONFIG_BUCKET = aws_s3_bucket.config.bucket
      }
    }
    data_profiler = {
      description = "Computes completeness, uniqueness and column statistics"
      timeout     = 120
      env         = {}
    }
    pii_detector = {
      description = "Detects PII leakage with Amazon Comprehend"
      timeout     = 120
      env = {
        CONFIG_BUCKET = aws_s3_bucket.config.bucket
      }
    }
    anomaly_detector = {
      description = "Flags statistical outliers and volume drift vs run history"
      timeout     = 120
      env         = {}
    }
    quality_scorer = {
      description = "Aggregates check results into a weighted quality verdict"
      timeout     = 30
      env = {
        PASS_THRESHOLD = tostring(var.pass_threshold)
        WARN_THRESHOLD = tostring(var.warn_threshold)
      }
    }
    results_writer = {
      description = "Promotes passing files to curated and writes Athena metrics"
      timeout     = 60
      env = {
        LAKE_BUCKET = aws_s3_bucket.lake.bucket
      }
    }
    remediation = {
      description = "Quarantines failing files and alerts owners via SNS"
      timeout     = 60
      env = {
        LAKE_BUCKET     = aws_s3_bucket.lake.bucket
        ALERT_TOPIC_ARN = aws_sns_topic.quality_alerts.arn
      }
    }
    api_handler = {
      description = "Serves quality reports over API Gateway, queries Athena"
      timeout     = 29
      env = {
        ATHENA_DATABASE  = aws_glue_catalog_database.quality.name
        ATHENA_WORKGROUP = aws_athena_workgroup.quality.name
      }
    }
  }
}

data "archive_file" "common_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/layers/common"
  output_path = "${path.module}/.build/common_layer.zip"
}

resource "aws_lambda_layer_version" "common" {
  layer_name          = "${local.name_prefix}-common"
  filename            = data.archive_file.common_layer.output_path
  source_code_hash    = data.archive_file.common_layer.output_base64sha256
  compatible_runtimes = [local.lambda_runtime]
}

data "archive_file" "lambda" {
  for_each    = local.lambda_functions
  type        = "zip"
  source_dir  = "${local.lambda_src}/${each.key}"
  output_path = "${path.module}/.build/${each.key}.zip"
}

resource "aws_lambda_function" "functions" {
  for_each = local.lambda_functions

  function_name    = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  description      = each.value.description
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = local.lambda_runtime
  handler          = "handler.lambda_handler"
  timeout          = each.value.timeout
  memory_size      = var.lambda_memory_mb
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  layers           = [aws_lambda_layer_version.common.arn]

  environment {
    variables = merge(local.common_env, each.value.env)
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "ingestion_trigger" {
  type        = "zip"
  source_dir  = "${local.lambda_src}/ingestion_trigger"
  output_path = "${path.module}/.build/ingestion_trigger.zip"
}

resource "aws_lambda_function" "ingestion_trigger" {
  function_name    = "${local.name_prefix}-ingestion-trigger"
  description      = "Validates incoming raw objects and starts the quality workflow"
  role             = aws_iam_role.ingestion_trigger.arn
  runtime          = local.lambda_runtime
  handler          = "handler.lambda_handler"
  timeout          = 30
  memory_size      = 256
  filename         = data.archive_file.ingestion_trigger.output_path
  source_code_hash = data.archive_file.ingestion_trigger.output_base64sha256
  layers           = [aws_lambda_layer_version.common.arn]

  environment {
    variables = merge(local.common_env, {
      STATE_MACHINE_ARN = aws_sfn_state_machine.data_quality.arn
      RAW_PREFIX        = "raw/"
    })
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.ingestion_trigger]
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambda_functions
  name              = "/aws/lambda/${local.name_prefix}-${replace(each.key, "_", "-")}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "ingestion_trigger" {
  name              = "/aws/lambda/${local.name_prefix}-ingestion-trigger"
  retention_in_days = var.log_retention_days
}
