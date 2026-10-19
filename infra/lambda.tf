resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/aws/lambda/${var.project_name}-pipeline"
  retention_in_days = 14 # Lambda's default would be "never expire"
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pipeline" {
  name               = "${var.project_name}-pipeline"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

# Least privilege: its own log group, and only the prefixes it owns in the data bucket.
data "aws_iam_policy_document" "pipeline" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.pipeline.arn}:*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "curated/*"]
    }
  }
  statement {
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/raw/*",
      "${aws_s3_bucket.data.arn}/curated/*",
    ]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/data/summary.json"]
  }
}

resource "aws_iam_role_policy" "pipeline" {
  role   = aws_iam_role.pipeline.id
  policy = data.aws_iam_policy_document.pipeline.json
}

resource "aws_lambda_function" "pipeline" {
  function_name    = "${var.project_name}-pipeline"
  role             = aws_iam_role.pipeline.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"] # must match the wheels tools/build_lambda.sh downloads
  handler          = "pipeline.lambda_handler.handler"
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)

  memory_size = 3008 # DuckDB needs the RAM; CPU also scales with memory
  timeout     = 600
  ephemeral_storage {
    size = 4096 # /tmp holds the window's raw Parquet while DuckDB reads it
  }
  # Never two runs at once, so no locking code is needed.
  reserved_concurrent_executions = 1

  environment {
    variables = {
      DT_BUCKET          = aws_s3_bucket.data.bucket
      DT_DOWNLOAD_CAP_MB = tostring(var.download_cap_mb)
      DT_WINDOW_DAYS     = tostring(var.ingestion_window_days)
    }
  }

  depends_on = [aws_cloudwatch_log_group.pipeline, aws_iam_role_policy.pipeline]
}

# Scheduler invokes asynchronously. No automatic retries: the next hourly run is the retry.
resource "aws_lambda_function_event_invoke_config" "pipeline" {
  function_name                = aws_lambda_function.pipeline.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}

output "pipeline_function" {
  value = aws_lambda_function.pipeline.function_name
}
