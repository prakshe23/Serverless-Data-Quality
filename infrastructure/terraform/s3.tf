# Data lake bucket. Zones are prefixes:
#   raw/<dataset>/...        incoming files (EventBridge watches this)
#   curated/<dataset>/...    files that passed quality checks
#   quarantine/<dataset>/... files that failed
#   metrics/year=/month=/day=/  quality reports, cataloged by Glue for Athena
resource "aws_s3_bucket" "lake" {
  bucket        = "${local.name_prefix}-lake-${local.account_id}"
  force_destroy = var.environment != "prod"
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 rather than KMS: encrypted at rest with no per-request KMS charges.
resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# EventBridge needs bucket notifications enabled to receive object events.
resource "aws_s3_bucket_notification" "lake" {
  bucket      = aws_s3_bucket.lake.id
  eventbridge = true
}

# Configuration bucket: schema contracts live at schemas/<dataset>.json.
resource "aws_s3_bucket" "config" {
  bucket        = "${local.name_prefix}-config-${local.account_id}"
  force_destroy = var.environment != "prod"
}

resource "aws_s3_bucket_versioning" "config" {
  bucket = aws_s3_bucket.config.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket                  = aws_s3_bucket.config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Athena query results.
resource "aws_s3_bucket" "athena_results" {
  bucket        = "${local.name_prefix}-athena-results-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    id     = "expire-results"
    status = "Enabled"
    filter {}
    expiration {
      days = 14
    }
  }
}
