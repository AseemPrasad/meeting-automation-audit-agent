output "s3_bucket_name" {
  description = "Recordings S3 bucket name"
  value       = aws_s3_bucket.recordings.id
}

output "rds_endpoint" {
  description = "Postgres primary database endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "secrets_arn" {
  description = "AWS Secrets Manager ARN"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

