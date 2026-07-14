data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Baseline every function gets: logs, X-Ray traces, custom metrics and the
# runs table. Per-function statements are layered on top below.
data "aws_iam_policy_document" "lambda_base" {
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${local.name_prefix}-*"]
  }

  statement {
    sid = "Tracing"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DataQuality/${var.environment}"]
    }
  }

  statement {
    sid = "RunsTable"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.runs.arn]
  }
}

locals {
  lake_objects   = "${aws_s3_bucket.lake.arn}/*"
  config_objects = "${aws_s3_bucket.config.arn}/*"

  # Extra IAM statements per function, merged onto the baseline.
  lambda_extra_statements = {
    schema_validator = [
      {
        actions   = ["s3:GetObject"]
        resources = [local.lake_objects, local.config_objects]
      },
    ]
    data_profiler = [
      {
        actions   = ["s3:GetObject"]
        resources = [local.lake_objects]
      },
    ]
    pii_detector = [
      {
        actions   = ["s3:GetObject"]
        resources = [local.lake_objects, local.config_objects]
      },
      {
        actions = [
          "comprehend:DetectPiiEntities",
          "comprehend:DetectDominantLanguage",
        ]
        resources = ["*"]
      },
    ]
    anomaly_detector = [
      {
        actions   = ["s3:GetObject"]
        resources = [local.lake_objects]
      },
    ]
    quality_scorer = []
    results_writer = [
      {
        actions   = ["s3:GetObject", "s3:PutObject"]
        resources = [local.lake_objects]
      },
    ]
    remediation = [
      {
        actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        resources = [local.lake_objects]
      },
      {
        actions   = ["sns:Publish"]
        resources = [aws_sns_topic.quality_alerts.arn]
      },
    ]
    api_handler = [
      {
        actions = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StopQueryExecution",
        ]
        resources = ["arn:aws:athena:${var.aws_region}:${local.account_id}:workgroup/${local.name_prefix}"]
      },
      {
        actions = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartitions",
        ]
        resources = [
          "arn:aws:glue:${var.aws_region}:${local.account_id}:catalog",
          aws_glue_catalog_database.quality.arn,
          "arn:aws:glue:${var.aws_region}:${local.account_id}:table/${aws_glue_catalog_database.quality.name}/*",
        ]
      },
      {
        # Athena reads source data and writes results with the caller's creds.
        actions   = ["s3:GetObject", "s3:ListBucket"]
        resources = [aws_s3_bucket.lake.arn, local.lake_objects]
      },
      {
        actions = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetBucketLocation",
          "s3:ListBucket",
          "s3:AbortMultipartUpload",
        ]
        resources = [aws_s3_bucket.athena_results.arn, "${aws_s3_bucket.athena_results.arn}/*"]
      },
    ]
  }
}

data "aws_iam_policy_document" "lambda" {
  for_each = local.lambda_functions

  source_policy_documents = [data.aws_iam_policy_document.lambda_base.json]

  dynamic "statement" {
    for_each = local.lambda_extra_statements[each.key]
    content {
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each           = local.lambda_functions
  name               = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.lambda_functions
  name     = "inline"
  role     = aws_iam_role.lambda[each.key].id
  policy   = data.aws_iam_policy_document.lambda[each.key].json
}

# --- Ingestion trigger (separate: needs StartExecution on the workflow) ---

data "aws_iam_policy_document" "ingestion_trigger" {
  source_policy_documents = [data.aws_iam_policy_document.lambda_base.json]

  statement {
    actions   = ["states:StartExecution"]
    resources = ["arn:aws:states:${var.aws_region}:${local.account_id}:stateMachine:${local.name_prefix}-workflow"]
  }
}

resource "aws_iam_role" "ingestion_trigger" {
  name               = "${local.name_prefix}-ingestion-trigger"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "ingestion_trigger" {
  name   = "inline"
  role   = aws_iam_role.ingestion_trigger.id
  policy = data.aws_iam_policy_document.ingestion_trigger.json
}

# --- Step Functions ---

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "sfn" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [for f in aws_lambda_function.functions : f.arn]
  }

  # Express workflow logging & tracing.
  statement {
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.name_prefix}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn" {
  name   = "inline"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

# --- Glue crawler (only when the optional curated crawler is enabled) ---

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_crawler" {
  count              = var.enable_curated_crawler ? 1 : 0
  name               = "${local.name_prefix}-glue-crawler"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  count      = var.enable_curated_crawler ? 1 : 0
  role       = aws_iam_role.glue_crawler[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_crawler_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn, local.lake_objects]
  }
}

resource "aws_iam_role_policy" "glue_crawler_s3" {
  count  = var.enable_curated_crawler ? 1 : 0
  name   = "s3-access"
  role   = aws_iam_role.glue_crawler[0].id
  policy = data.aws_iam_policy_document.glue_crawler_s3.json
}
