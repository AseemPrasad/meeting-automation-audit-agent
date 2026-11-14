resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "auditagent/${var.environment}/credentials"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "initial_template" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    GROQ_API_KEY          = "replace_with_live_groq_key"
    STRIPE_API_KEY        = "replace_with_live_stripe_key"
    STRIPE_WEBHOOK_SECRET = "replace_with_live_stripe_whsec"
    DATABASE_URL          = "postgresql://audit_admin:password@host:5432/meeting_automation"
    REDIS_URL             = "redis://host:6379/0"
  })
}

# Least-Privilege IAM Policy for Application Workloads (EKS IRSA or ECS Task Role)
resource "aws_iam_policy" "app_policy" {
  name        = "auditagent-${var.environment}-app-policy"
  description = "Allows S3 recording storage access and Secrets Manager resolution"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload"
        ]
        Resource = "${aws_s3_bucket.recordings.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.app_secrets.arn
      }
    ]
  })
}

