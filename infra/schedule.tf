resource "aws_scheduler_schedule" "hourly" {
  name = "${var.project_name}-hourly"
  # Hourly at :45. Upstream's hourly file (ending ~:15) lands in the manifest around
  # :35; running at :15 would always be an hour behind.
  schedule_expression          = "cron(45 * * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.pipeline.arn
    role_arn = aws_iam_role.scheduler.arn
    retry_policy {
      maximum_retry_attempts = 2 # delivery retries, not run retries
    }
  }
}

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition { # confused-deputy guard
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project_name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.pipeline.arn
    }]
  })
}
