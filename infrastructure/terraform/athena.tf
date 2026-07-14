resource "aws_athena_workgroup" "quality" {
  name          = local.name_prefix
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    # Athena has no free tier ($5/TB scanned); this cap bounds the worst
    # case to about $0.0005 per query.
    bytes_scanned_cutoff_per_query = 104857600 # 100 MiB

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

resource "aws_athena_named_query" "daily_scores" {
  name        = "${local.name_prefix}-daily-scores"
  workgroup   = aws_athena_workgroup.quality.name
  database    = aws_glue_catalog_database.quality.name
  description = "Average quality score per dataset per day"
  query       = <<-SQL
    SELECT dataset,
           date_trunc('day', from_iso8601_timestamp(finished_at)) AS day,
           avg(overall_score) AS avg_score,
           count(*) AS runs,
           sum(CASE WHEN verdict = 'FAILED' THEN 1 ELSE 0 END) AS failed_runs
    FROM metrics
    GROUP BY 1, 2
    ORDER BY 2 DESC, 1
  SQL
}

resource "aws_athena_named_query" "worst_dimensions" {
  name        = "${local.name_prefix}-worst-dimensions"
  workgroup   = aws_athena_workgroup.quality.name
  database    = aws_glue_catalog_database.quality.name
  description = "Which quality dimension drags each dataset down the most"
  query       = <<-SQL
    SELECT dataset,
           avg(schema_score)  AS schema,
           avg(profile_score) AS profile,
           avg(pii_score)     AS pii,
           avg(anomaly_score) AS anomaly
    FROM metrics
    WHERE from_iso8601_timestamp(finished_at) > current_timestamp - interval '30' day
    GROUP BY 1
    ORDER BY 1
  SQL
}
