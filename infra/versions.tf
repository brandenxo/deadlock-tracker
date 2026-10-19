terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.58"
    }
  }

  # The bucket, key, and selected Region are supplied later through
  # backend.hcl so environment-specific values are not committed here.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  # Account-regional S3 bucket names must end with:
  # <account-id>-<region>-an
  bucket_namespace_suffix = "${data.aws_caller_identity.current.account_id}-${var.region}-an"
  data_bucket_name        = "${var.project_name}-data-${local.bucket_namespace_suffix}"
  site_bucket_name        = "${var.project_name}-site-${local.bucket_namespace_suffix}"
}
