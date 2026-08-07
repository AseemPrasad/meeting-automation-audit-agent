"""Transcript processing workflow executed by the Celery worker.

This mirrors the LLM logic from the original synchronous /process route but
runs it in the background with automatic retries (exponential backoff + jitter).
"""
import json
import os
import re

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy.orm import Session

from worker.core.celery_app import celery_app
from worker.core.database import SessionLocal
from worker.models.job import Job
from worker.services.llm.router import LLMRouter

load_dotenv()

# LLM gateway with multi-provider failover. Degrades to Groq (the existing
# pipeline) when no other provider keys are configured, preserving behavior.
llm_router = LLMRouter.from_env()

# Groq client still used for transcription (Whisper).
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Transient failures that justify a retry
RETRYABLE_EXCEPTIONS = (Exception,)


def _update_job_status(db: Session, job_id: str, status: str, **kwargs) -> None:
    """Update a job row and commit. Missing row -> silently ignored."""
    job = db.get(Job, job_id)
    if job is None:
        return
    for key, value in kwargs.items():
        setattr(job, key, value)
    job.status = status
    db.commit()


def _transcribe(client: Groq, file_path: str) -> str:
    """Transcribe audio via Groq Whisper."""
    with open(file_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            file=f, model="whisper-large-v3"
        )
    return transcript.text


def _extract_tasks_decisions(client: Groq, text: str) -> dict:
    """Extract structured tasks/decisions via the multi-provider LLM gateway.

    Falls back automatically across configured providers (circuit-breaker
    aware). When only GROQ_API_KEY is present, this is functionally identical
    to the original direct Groq call (same model, same prompt, same JSON parse).
    """
    prompt = f"""
You are an AI meeting assistant. Extract tasks and decisions from the transcript below.
Respond ONLY with valid JSON in this exact format:

{{
    "summary": "...",
    "tasks": ["...", "..."],
    "decisions": ["...", "..."]
}}

Transcript:
{text}
"""
    ai_output = llm_router.generate(prompt, temperature=0.2)

    parsed = {"summary": "", "tasks": [], "decisions": []}
    try:
        match = re.search(r"\{.*\}", ai_output, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        pass
    return parsed


@celery_app.task(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,          # exponential backoff
    retry_backoff_max=60,        # cap at 60s
    retry_jitter=True,           # add jitter to avoid thundering herd
    max_retries=5,
    acks_late=True,
    ignore_result=False,
)
def process_transcript(self, job_id: str, file_path: str) -> dict:
    """Process a transcript file: transcribe -> extract -> persist result."""
    db: Session = SessionLocal()
    try:
        _update_job_status(db, job_id, "PROCESSING")

        text = _transcribe(client, file_path)
        analysis = _extract_tasks_decisions(client, text)

        payload = {"transcript": text, "analysis": analysis}
        _update_job_status(
            db, job_id, "COMPLETED", result_payload=json.dumps(payload)
        )
        return payload
    except Exception as exc:
        _update_job_status(db, job_id, "FAILED", error=str(exc))
        # Re-raise so Celery applies the retry/backoff policy
        raise self.retry(exc=exc)
    finally:
        db.close()
        if os.path.exists(file_path):
            os.remove(file_path)

