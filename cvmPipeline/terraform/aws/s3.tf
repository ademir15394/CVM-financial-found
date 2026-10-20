resource "aws_s3_bucket" "cvm-data" {

    bucket = "cvm-data-${var.environment}-${data.aws_caller_identity.current.account_id}"
  
}

resource "aws_s3_account_public_access_block" "cvm-access" {

    block_public_acls       = false
    block_public_policy     = false
    ignore_public_acls      = false
    restrict_public_buckets = false

}

resource "aws_s3_bucket_versioning" "versioning_example" {
  bucket = aws_s3_bucket.cvm-data.id
  versioning_configuration {
    status = "Enabled"
  }
}