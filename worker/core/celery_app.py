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
    },
)

