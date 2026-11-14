# 08. Operations Runbook and Disaster Recovery

## Incident Response & Triage

### 1. Celery Dead-Letter Queue (DLQ) Alerts
When a background task exhausts its maximum retries (`max_retries=3`), Celery triggers `@task_failure.connect` and posts an incident alert to Slack / PagerDuty:

```json
{
  "event": "CRITICAL_CELERY_TASK_FAILURE",
  "task_name": "worker.audit.workflows.audit_workflow.process_audit_recording_task",
  "task_id": "8a719c23-4c91-450a-bc01-9214710129ad",
  "error": "GroqAPIError: Rate limit reached or upstream timeout"
}
```

#### Triage Procedure
1. **Locate the Job Record:**
   ```bash
   python -c "
   from worker.core.database import SessionLocal
   from worker.models.job import Job
   db = SessionLocal()
   job = db.query(Job).filter(Job.id == '8a719c23-4c91-450a-bc01-9214710129ad').first()
   print(job.status, job.error)
   "
   ```
2. **Inspect Upstream Circuit Breakers:**
   - If Groq Whisper or the LLM provider is throttling requests, the circuit breaker moves to `OPEN` status, protecting the application from cascading failures.
   - Wait for the cooldown window (60s) for the breaker to transition to `HALF-OPEN`.
3. **Manual Job Replay:**
   To re-queue a failed job without requiring customer re-upload:
   ```bash
   python -c "
   from worker.audit.workflows.audit_workflow import process_audit_recording_task
   process_audit_recording_task.delay(
       job_id='8a719c23-4c91-450a-bc01-9214710129ad',
       file_path='s3://auditagent-production-recordings/recordings/file.mp3',
       meeting_type='financial_advisory',
       tenant_id='org-apex-01'
   )
   "
   ```

---

## Secret Rotation Playbook

When rotating API keys, database credentials, or Stripe secrets:

1. **Update AWS Secrets Manager:**
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id auditagent/production/credentials \
     --secret-string file://new_secrets.json
   ```
2. **Graceful Cache Invalidation:**
   - `secrets_resolver.py` re-reads secrets automatically when workers recycle.
   - For an immediate reload across all container workers:
     ```bash
     docker compose -f deploy/docker-compose.prod.yml restart web worker
     ```

---

## Database Disaster Recovery & Backup

### 1. AWS RDS Automated Snapshots
- Automated daily snapshots with a 7-day retention period.
- Storage encryption enabled via AWS KMS.

### 2. Point-in-Time Recovery (PITR)
To restore a corrupted or accidentally deleted database to a specific second:
```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier auditagent-production-postgres \
  --target-db-instance-identifier auditagent-restored-postgres \
  --restore-time 2026-11-14T12:00:00.000Z \
  --db-subnet-group-name auditagent-production-db-subnets
```
Once the restored instance is available, update `DATABASE_URL` in AWS Secrets Manager.

---

## Zero-Downtime Deployment Playbook

To release new application code without dropping active customer uploads or worker transcription jobs:

1. **Step 1: Run Database Migrations:**
   ```bash
   python -m alembic upgrade head
   ```
2. **Step 2: Rolling Worker Refresh:**
   Restart Celery workers with `SIGTERM` or `celery multi restart`. Celery will complete in-flight tasks (`task_acks_late=True`) before shutting down and starting the new container image.
3. **Step 3: Rolling Web Gateway Refresh:**
   NGINX will route web requests to healthy Uvicorn backend instances while upgraded instances restart.

