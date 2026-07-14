resource "aws_glue_catalog_database" "quality" {
  name        = replace("${local.name_prefix}-quality", "-", "_")
  description = "Data quality metrics and curated datasets"
}

# Catalogs the JSON quality reports written by the results_writer Lambda
# (metrics/year=/month=/day=/<run_id>.json) so Athena can query trends.
resource "aws_glue_crawler" "metrics" {
  name          = "${local.name_prefix}-metrics"
  database_name = aws_glue_catalog_database.quality.name
  role          = aws_iam_role.glue_crawler.arn
  table_prefix  = ""

  s3_target {
    path = "s3://${aws_s3_bucket.lake.bucket}/metrics/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version = 1.0
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
  })

  # Hourly is plenty: partitions only change once a day, new files within a
  # partition are picked up automatically by Athena.
  schedule = "cron(15 * * * ? *)"
}

# Catalogs the curated zone so promoted files are immediately queryable.
resource "aws_glue_crawler" "curated" {
  name          = "${local.name_prefix}-curated"
  database_name = aws_glue_catalog_database.quality.name
  role          = aws_iam_role.glue_crawler.arn
  table_prefix  = "curated_"

  s3_target {
    path = "s3://${aws_s3_bucket.lake.bucket}/curated/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }

  schedule = "cron(45 * * * ? *)"
}
