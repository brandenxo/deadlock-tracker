resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/aws/lambda/${var.project_name}-pipeline"
  retention_in_days = 14 # auto-created groups never expire
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

# Scoped to its own log group and the data-bucket prefixes the pipeline writes.
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
  architectures    = ["x86_64"] # matches the DuckDB wheel in the zip
  handler          = "pipeline.lambda_handler.handler"
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)

  memory_size = 3008 # memory also sets the CPU share
  timeout     = 600
  ephemeral_storage {
    size = 4096 # raw Parquet and DuckDB spill space
  }
  # One run at a time; replaces any locking in the code.
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

# Async invokes from the scheduler. Retries are off since the next hourly run does the same work.
resource "aws_lambda_function_event_invoke_config" "pipeline" {
  function_name                = aws_lambda_function.pipeline.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}

output "pipeline_function" {
  value = aws_lambda_function.pipeline.function_name
}
