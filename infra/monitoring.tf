# Budgets only NOTIFY; they don't stop spending. The real limits are the download cap,
# the Lambda timeout, reserved concurrency 1, and the Athena per-query scan cutoff.
# (A spend limit in AWS Settings, if you set one, is the hard stop.)
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project_name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Any failed run (source error, schema change, validation failure, timeout).
# Find the cause in Logs Insights: filter event = "run_failed".
resource "aws_cloudwatch_metric_alarm" "pipeline_errors" {
  alarm_name          = "${var.project_name}-pipeline-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.pipeline.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# The silent failure: nothing runs at all (schedule broken, function throttled), so there
# are no errors to count. Alarm when there were no invocations for three hours. Only
# while the schedule is on, or it would alarm the whole time it's deliberately off.
resource "aws_cloudwatch_metric_alarm" "pipeline_not_running" {
  count               = var.schedule_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-pipeline-not-running"
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = aws_lambda_function.pipeline.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching" # no data at all means no runs
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Saved Logs Insights query: every run outcome, newest first. One click in the console.
resource "aws_cloudwatch_query_definition" "runs" {
  name            = "${var.project_name}/runs"
  log_group_names = [aws_cloudwatch_log_group.pipeline.name]
  query_string    = <<-EOT
    fields @timestamp, event, error_class, error, covered_dates, seconds
    | filter event in ["run_failed", "published", "heroes_unavailable"]
    | sort @timestamp desc
    | limit 50
  EOT
}
