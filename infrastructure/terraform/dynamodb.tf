# Single-table design for run records and per-dataset history.
# See src/layers/common/python/dq_common/runs.py for the access patterns.
resource "aws_dynamodb_table" "runs" {
  name      = "${local.name_prefix}-runs"
  hash_key  = "pk"
  range_key = "sk"

  # Provisioned capacity inside the always-free tier (25 RCU/WCU per
  # account); on-demand billing has no free tier.
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5

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
