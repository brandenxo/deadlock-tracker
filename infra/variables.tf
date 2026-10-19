variable "region" {
  description = "AWS selected Region for all Regional project resources."
  type        = string
  default     = "us-east-2"

  validation {
    condition     = var.region == "us-east-2"
    error_message = "This AWS project is restricted to its selected Region, us-east-2."
  }
}

variable "project_name" {
  description = "Lowercase project identifier used in resource names and tags."
  type        = string
  default     = "deadlock-tracker"

  validation {
    condition = (
      length(var.project_name) >= 3 &&
      length(var.project_name) <= 30 &&
      can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.project_name))
    )
    error_message = "Project name must be 3-30 characters using lowercase letters, numbers, and internal hyphens only."
  }
}

variable "ingestion_window_days" {
  description = "Number of recent days retained for ingestion and dashboard analysis."
  type        = number
  default     = 7

  validation {
    condition = (
      var.ingestion_window_days >= 1 &&
      var.ingestion_window_days <= 90 &&
      floor(var.ingestion_window_days) == var.ingestion_window_days
    )
    error_message = "Ingestion window must be a whole number from 1 through 90."
  }
}

variable "alert_email" {
  description = "Receives budget and pipeline-failure emails (confirm the SNS email once)."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "Alert email must be a valid email address."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget alarm threshold, in US dollars."
  type        = number
  default     = 10
}

variable "schedule_enabled" {
  description = "Created off; turn on after a manual run has published a summary."
  type        = bool
  default     = false
}

variable "download_cap_mb" {
  description = "Most a single run may download from the source."
  type        = number
  default     = 300
}

variable "domain_name" {
  description = "Optional, e.g. deadlock.example.com. Leave empty to use the cloudfront.net address."
  type        = string
  default     = ""
}

variable "lambda_zip" {
  description = "Built by tools/build_lambda.sh."
  type        = string
  default     = "../build/pipeline.zip"
}
