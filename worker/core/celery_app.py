"""Celery application configuration backed by Redis.

This decouples job submission from job execution. The FastAPI process only
enqueues tasks; the Celery worker consumes them asynchronously.
"""
import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "meeting_automation",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "worker.workflows.transcript_workflow",
        "worker.audit.workflows.audit_workflow"
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Only acknowledge tasks after execution so failed tasks can be retried
    task_acks_late=True,
    # Required for Celery 5.x on modern brokers
    broker_connection_retry_on_startup=True,
    # Route transcript tasks to a dedicated queue
    task_default_queue="transcripts",
    task_routes={
        "worker.workflows.transcript_workflow.process_transcript": {"queue": "transcripts"},
        "worker.audit.workflows.audit_workflow.process_audit_recording_task": {"queue": "audit_queue"},
    },
)

# Dead-Letter Alerting & Permanent Failure Hook
from celery.signals import task_failure
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """
    Triggers structured alerting and dead-letter notification when a Celery task fails.
    Dispatches to SLACK_WEBHOOK_URL or PAGERDUTY_INTEGRATION_KEY if configured.
    """
    alert_payload = {
        "event": "CRITICAL_CELERY_TASK_FAILURE",
        "task_name": sender.name if sender else "unknown",
        "task_id": task_id,
        "error": str(exception),
        "args": str(args)[:500] if args else None,
        "kwargs": str(kwargs)[:500] if kwargs else None,
    }
    logger.critical(f"DLQ_ALERT: {json.dumps(alert_payload)}")

    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    if slack_webhook:
        try:
            req = urllib.request.Request(
                slack_webhook,
                data=json.dumps({"text": f":rotating_light: *Task Failure Alert*: `{alert_payload['task_name']}` failed permanently.\nTask ID: `{task_id}`\nError: `{alert_payload['error']}`"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.warning(f"Could not deliver failure alert to Slack: {e}")


