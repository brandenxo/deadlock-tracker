output "dashboard_url" {
  value = local.use_domain ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "cloudfront_domain" {
  description = "Point your domain's CNAME record here."
  value       = aws_cloudfront_distribution.main.domain_name
}

output "distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "data_bucket" {
  value = aws_s3_bucket.data.bucket
}
