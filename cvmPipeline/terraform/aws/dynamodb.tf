resource "aws_dynamodb_table" "ingestion_control" {
  name         = "cvm_ingestion_control_${var.environment}"
  billing_mode = "PAY_PER_REQUEST" # On-Demand para custo zero sem uso

  hash_key  = "dataset_type"
  range_key = "ano_mes"

  attribute {
    name = "dataset_type"
    type = "S"
  }

  attribute {
    name = "ano_mes"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}