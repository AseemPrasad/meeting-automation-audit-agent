resource "aws_s3_bucket" "recordings" {
  bucket = "auditagent-${var.environment}-recordings"

  force_destroy = false
}

# Strict Zero-Trust Block of all public access
resource "aws_s3_bucket_public_access_block" "recordings_pab" {
  bucket = aws_s3_bucket.recordings.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-Side Encryption (AES256)
resource "aws_s3_bucket_server_side_encryption_configuration" "recordings_sse" {
  bucket = aws_s3_bucket.recordings.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 30-Day Auto-Expiration Lifecycle Rule (SOC2 & Privacy compliance)
resource "aws_s3_bucket_lifecycle_configuration" "recordings_lifecycle" {
  bucket = aws_s3_bucket.recordings.id

  rule {
    id     = "auto-delete-raw-audio-30-days"
    status = "Enabled"

    filter {
      prefix = "recordings/"
    }

    expiration {
      days = 30
    }
  }
}

# Web Presigned Direct-Upload CORS
resource "aws_s3_bucket_cors_configuration" "recordings_cors" {
  bucket = aws_s3_bucket.recordings.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["https://${var.domain_name}", "https://app.${var.domain_name}"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

