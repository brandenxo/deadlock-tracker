# Optional custom domain, enabled by setting domain_name in terraform.tfvars.
#
# CloudFront requires its ACM certificate in us-east-1, so this file uses a second
# provider pinned there. The project's Region SCP explicitly allows acm:* in us-east-1;
# nothing else is created in that Region.
#
# Validation is DNS-based and the zone lives in Cloudflare, not Route 53: add the CNAME
# from the dns_validation_records output there (proxy off) and the apply waits for it.
# Keep that record; ACM renews the certificate through it.

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = { Project = var.project_name, ManagedBy = "terraform" }
  }
}

locals {
  use_domain = var.domain_name != ""
}

resource "aws_acm_certificate" "site" {
  count             = local.use_domain ? 1 : 0
  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true # no HTTPS gap when the domain changes
  }
}

resource "aws_acm_certificate_validation" "site" {
  count           = local.use_domain ? 1 : 0
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.site[0].arn
  # Record lives in Cloudflare, so there are no FQDNs to pass; this only waits.
  timeouts {
    create = "2h"
  }
}

output "dns_validation_records" {
  description = "Add each as a CNAME at your DNS provider (once)."
  value = local.use_domain ? [
    for o in aws_acm_certificate.site[0].domain_validation_options : {
      type  = o.resource_record_type
      name  = o.resource_record_name
      value = o.resource_record_value
    }
  ] : []
}
