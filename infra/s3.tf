# Both buckets are private; all public reads go through CloudFront (cdn.tf).
#
#   data bucket: raw/            trimmed source objects, expired after the window
#                curated/        date-partitioned Parquet for Athena
#                data/           summary.json, the dashboard's only input
#                athena-results/
#   site bucket: Vite build output
#
# Names use the account-regional namespace (-<account>-<region>-an suffix), which
# no other account can claim.

resource "aws_s3_bucket" "data" {
  bucket           = local.data_bucket_name
  bucket_namespace = "account-regional"
}

resource "aws_s3_bucket" "site" {
  bucket           = local.site_bucket_name
  bucket_namespace = "account-regional"
  force_destroy    = true # contents are disposable build output
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "raw-expires-after-window"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    expiration {
      days = var.ingestion_window_days + 3
    }
  }

  rule {
    id     = "athena-results-are-temporary"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }
}
