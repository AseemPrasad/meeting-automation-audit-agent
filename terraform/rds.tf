resource "aws_db_subnet_group" "rds" {
  name       = "auditagent-${var.environment}-db-subnets"
  subnet_ids = [] # populated with private VPC subnet IDs
}

resource "aws_db_instance" "postgres" {
  identifier        = "auditagent-${var.environment}-postgres"
  engine            = "postgres"
  engine_version    = "16.1"
  instance_class    = var.db_instance_class
  allocated_storage = 20
  max_allocated_storage = 100

  db_name  = "meeting_automation"
  username = "audit_admin"
  password = "CHANGE_IN_SECRETS_MANAGER" # Handled via dynamic secrets

  multi_az               = true
  publicly_accessible    = false
  storage_encrypted      = true
  deletion_protection    = true
  skip_final_snapshot    = false
  final_snapshot_identifier = "auditagent-${var.environment}-final-snap"
  backup_retention_period = 7

  vpc_security_group_ids = []
  db_subnet_group_name   = aws_db_subnet_group.rds.name
}

