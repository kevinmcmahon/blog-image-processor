variable "bucket_name" {
  description = "S3 bucket for blog images"
  type        = string
  default     = "kevfoo-content"
}

variable "base_url" {
  description = "CDN base URL for HTML snippets"
  type        = string
  default     = "https://cache.kevfoo.com"
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}
