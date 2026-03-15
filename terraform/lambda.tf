data "aws_s3_bucket" "content" {
  bucket = var.bucket_name
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/blog-image-processor"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "lambda" {
  name = "blog-image-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

}

resource "aws_iam_role_policy" "lambda" {
  name = "blog-image-processor-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "arn:aws:s3:::${var.bucket_name}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "processor" {
  function_name    = "blog-image-processor"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = var.lambda_memory
  timeout          = var.lambda_timeout
  role             = aws_iam_role.lambda.arn
  filename         = "${path.module}/../lambda/package.zip"
  source_code_hash = filebase64sha256("${path.module}/../lambda/package.zip")

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      POWERTOOLS_SERVICE_NAME = "blog-image-processor"
      LOG_LEVEL               = "INFO"
      BASE_URL                = var.base_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = data.aws_s3_bucket.content.arn
}

resource "aws_s3_bucket_notification" "image_upload" {
  bucket = data.aws_s3_bucket.content.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.processor.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_suffix       = ".jpg"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.processor.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_suffix       = ".jpeg"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.processor.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_suffix       = ".png"
  }

  depends_on = [aws_lambda_permission.s3]
}
