# Single-table design for run records and per-dataset history.
# See src/layers/common/python/dq_common/runs.py for the access patterns.
resource "aws_dynamodb_table" "runs" {
  name         = "${local.name_prefix}-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }
}
