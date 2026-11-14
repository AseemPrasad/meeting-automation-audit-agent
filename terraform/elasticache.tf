resource "aws_elasticache_subnet_group" "redis" {
  name       = "auditagent-${var.environment}-redis-subnets"
  subnet_ids = []
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "auditagent-${var.environment}-redis"
  engine               = "redis"
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = []
}

