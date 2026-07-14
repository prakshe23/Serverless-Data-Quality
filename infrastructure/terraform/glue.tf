resource "aws_glue_catalog_database" "quality" {
  name        = replace("${local.name_prefix}-quality", "-", "_")
  description = "Data quality metrics and curated datasets"
}

# The metrics table is declared here instead of being discovered by a
# crawler: the schema is fixed (results_writer writes it), the Glue Data
# Catalog itself is free, and partition projection means Athena resolves
# year=/month=/day= partitions without any crawler runs at all.
resource "aws_glue_catalog_table" "metrics" {
  name          = "metrics"
  database_name = aws_glue_catalog_database.quality.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"            = "json"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2025,2035"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "storage.location.template" = "s3://${aws_s3_bucket.lake.bucket}/metrics/year=$${year}/month=$${month}/day=$${day}/"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lake.bucket}/metrics/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "run_id"
      type = "string"
    }
    columns {
      name = "dataset"
      type = "string"
    }
    columns {
      name = "source_key"
      type = "string"
    }
    columns {
      name = "verdict"
      type = "string"
    }
    columns {
      name = "overall_score"
      type = "double"
    }
    columns {
      name = "schema_score"
      type = "double"
    }
    columns {
      name = "profile_score"
      type = "double"
    }
    columns {
      name = "pii_score"
      type = "double"
    }
    columns {
      name = "anomaly_score"
      type = "double"
    }
    columns {
      name = "row_count"
      type = "bigint"
    }
    columns {
      name = "finished_at"
      type = "string"
    }
  }
}

# Optional: catalog the curated zone with a scheduled crawler. Crawler runs
# are billed per DPU-hour (no free tier), so this is off by default.
resource "aws_glue_crawler" "curated" {
  count = var.enable_curated_crawler ? 1 : 0

  name          = "${local.name_prefix}-curated"
  database_name = aws_glue_catalog_database.quality.name
  role          = aws_iam_role.glue_crawler[0].arn
  table_prefix  = "curated_"

  s3_target {
    path = "s3://${aws_s3_bucket.lake.bucket}/curated/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }

  schedule = "cron(45 6 * * ? *)" # once a day
}
