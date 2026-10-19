# Two private buckets. Nothing is public: browsers reach data/summary.json and the site
# only through CloudFront (cdn.tf).
#
#   data bucket: raw/            projected source objects (expire after the window)
#                curated/        Parquet for ad-hoc Athena queries
#                data/           summary.json, the only thing the dashboard reads
#                athena-results/
#   site bucket: the built React app
#
# Both live in the account regional namespace (names end in -<account>-<region>-an), so
# no other AWS account can ever create a bucket with these names.

resource "aws_s3_bucket" "data" {
  bucket           = local.data_bucket_name
  bucket_namespace = "account-regional"
}

resource "aws_s3_bucket" "site" {
  bucket           = local.site_bucket_name
  bucket_namespace = "account-regional"
  force_destroy    = true # rebuilt from source on every deploy
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
