locals {
  dummy_image = "${aws_ecr_repository.scrapers.repository_url}:latest"
  
  common_env_vars = {
    DYNAMODB_TABLE = aws_dynamodb_table.ingestion_control.name
    S3_BUCKET_NAME = aws_s3_bucket.landing_zone.id
  }
}

# 1. Lambda CAD
resource "aws_lambda_function" "inf_cad" {
  function_name = "cvm-scraper-inf-cad"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  image_uri     = local.dummy_image
  timeout       = 900
  memory_size   = 1024

  image_config {
    command = ["scraper/inf_cad/inf_cad.lambda_handler"]
  }

  environment { variables = local.common_env_vars }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

# 2. Lambda CDA
resource "aws_lambda_function" "inf_cda" {
  function_name = "cvm-scraper-inf-cda"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  image_uri     = local.dummy_image
  timeout       = 900
  memory_size   = 1024

  image_config {
    command = ["scraper/inf_cda/inf_cda.lambda_handler"]
  }

  environment { variables = local.common_env_vars }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

# 3. Lambda Daily (Informe Diário)
resource "aws_lambda_function" "inf_daily" {
  function_name = "cvm-scraper-inf-daily"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  image_uri     = local.dummy_image
  timeout       = 900
  memory_size   = 1024

  image_config {
    command = ["scraper/inf_daily/inf_daily.lambda_handler"]
  }

  environment { variables = local.common_env_vars }

  lifecycle {
    ignore_changes = [image_uri]
  }
}