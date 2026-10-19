# Email-only cost alert; it doesn't cap anything. Actual guardrails: download cap,
# Lambda timeout, concurrency 1, Athena scan cutoff, and any spend limit configured in
# AWS Settings.
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

# Fires on any failed invocation: source errors, schema drift, failed validation,
# timeouts, OOM. Details are in the run_failed log events.
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

# Catches the case the errors alarm can't: no invocations at all (schedule disabled or
# broken, persistent throttling). Three empty hours trips it. Only exists while the
# schedule is enabled, since otherwise silence is expected.
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
  treat_missing_data  = "breaching" # missing data = no runs
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Saved Logs Insights query listing recent run outcomes.
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
