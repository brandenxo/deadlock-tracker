# Your own domain (optional): set domain_name in terraform.tfvars.
#
# CloudFront only accepts certificates from AWS Certificate Manager (ACM) in us-east-1,
# whatever Region the rest of the stack uses, hence the aliased provider. The project's
# Region policy allows ACM there for exactly this reason; nothing else is created in it.
# ACM proves you own the domain with a DNS record: `terraform apply` prints it
# (dns_validation_records), you add it at your DNS provider (Cloudflare, with the proxy
# OFF), and the apply waits until ACM sees it. Certificates from ACM are free and renew
# themselves as long as that record stays in place.

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
    create_before_destroy = true # a renamed domain gets its new cert before the old goes
  }
}

resource "aws_acm_certificate_validation" "site" {
  count           = local.use_domain ? 1 : 0
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.site[0].arn
  # No validation_record_fqdns: the DNS record lives outside AWS, so just wait for ACM.
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
