resource "aws_s3_bucket" "landing_zone" {
  bucket        = "cvm-landing-zone-${var.environment}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "landing_zone_block" {
  bucket = aws_s3_bucket.landing_zone.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "versioning_example" {
  bucket = aws_s3_bucket.landing_zone.id
  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_caller_identity" "current" {}


