output "lambda_function_arn" {
  description = "ARN of the blog image processor Lambda function"
  value       = aws_lambda_function.processor.arn
}

output "lambda_function_name" {
  description = "Name of the blog image processor Lambda function"
  value       = aws_lambda_function.processor.function_name
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.lambda.name
}
