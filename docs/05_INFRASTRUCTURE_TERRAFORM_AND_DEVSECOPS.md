# 05. Infrastructure, Terraform and DevSecOps

## Overview
AuditAgent's infrastructure is defined declaratively using **Terraform (Infrastructure as Code)** for AWS cloud deployments and **Docker Compose** for local staging and isolated container orchestration.

---

## Terraform Cloud Topology (`terraform/`)

The Terraform modules provision a production-grade AWS environment configured for high availability, least privilege, and compliance data security:

```
terraform/
├── main.tf               # Provider configuration and global tags
├── variables.tf          # Configurable parameters (region, tier, domains)
├── s3.tf                 # Audio recordings bucket with private access block & lifecycle
├── rds.tf                # Multi-AZ PostgreSQL 16 database with auto-scaling storage
├── elasticache.tf        # Redis 7 cache and Celery broker cluster
├── iam_and_secrets.tf    # Least-privilege IAM policies and Secrets Manager
└── outputs.tf            # Connection endpoints and ARNs
```

### Module Specifications

#### 1. Private Audio Storage (`s3.tf`)
- **Bucket:** `auditagent-${environment}-recordings`
- **Zero-Trust Access Block:** Enables all four S3 Public Access Block settings (`block_public_acls`, `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`).
- **Server-Side Encryption:** Default encryption using AES-256 (`aws:kms` or `AES256`).
- **Lifecycle Expiration:** Automatically purges objects under the `recordings/` prefix after 30 days to enforce privacy retention policies.
- **CORS Configuration:** Strictly limits presigned direct-upload origins to trusted company web domains.

#### 2. Relational Database (`rds.tf`)
- **Engine:** PostgreSQL 16.1 (Multi-AZ enabled for automatic failover).
- **Instance Class:** `db.t4g.medium` (expandable).
- **Storage Autoscaling:** `allocated_storage = 20GB`, with automatic scaling up to `100GB`.
- **Encrypted Snapshots:** Automated daily backups with 7-day retention and storage-level encryption enabled.

#### 3. Distributed In-Memory Cache (`elasticache.tf`)
- **Engine:** Redis 7 with replication.
- **Node Type:** `cache.t4g.micro` (or production multi-node cluster).
- **Security:** Private subnet isolation, encrypted in-transit (TLS), and protected via dedicated security groups.

#### 4. Zero-Trust Cloud IAM & Secrets (`iam_and_secrets.tf`)
- **AWS Secrets Manager:** Centralized store for `GROQ_API_KEY`, `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, and `DATABASE_URL`.
- **Least-Privilege Policy:** Application workloads (via EKS IRSA or ECS Task Roles) receive read/write permissions **only** on the specific recordings bucket and read permissions on the single application secret ARN.

---

## Production Edge Reverse Proxy (`deploy/nginx/nginx.conf`)

FastAPI sits behind a hardened NGINX 1.25 reverse proxy:

```nginx
# Security Ciphers & TLS 1.3
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
ssl_prefer_server_ciphers on;

# Hardened Security Headers
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# Rate Limiting & Body Limits
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
client_max_body_size 100M;
```

- **Let's Encrypt Automation:** Routes `/.well-known/acme-challenge/` to a shared webroot volume serviced by the `certbot/certbot` container, enabling automatic SSL renewals without service interruption.

---

## Observability & APM Telemetry

### 1. Structured JSON Logging (`worker/core/logging_config.py`)
In production environments (`LOG_FORMAT=json`), all container output to `stdout` is serialized into single-line JSON:
```json
{
  "timestamp": "2026-11-14T14:45:00.123456Z",
  "level": "INFO",
  "logger": "worker.audit.workflows",
  "message": "Audit completed for job 9351c1ab-d65c-4ad4-b5de-aac84f134a6a",
  "module": "audit_workflow",
  "line": 182,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```
This enables zero-configuration ingestion into Datadog, AWS CloudWatch Insights, and Grafana Loki.

### 2. OpenTelemetry & Trace Sampling (`worker/core/telemetry.py`)
- **W3C Trace Header Injection:** Background Celery tasks inherit the trace ID of the incoming HTTP request (`inject_trace_headers()`), creating unified end-to-end request traces.
- **Ratio-Based Head Sampling:** Controlled via `OTEL_SAMPLING_RATIO` (e.g. `0.2` for 20% routine sampling), while error spans are captured at 100% to protect enterprise telemetry budgets.

