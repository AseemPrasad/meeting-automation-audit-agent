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
from worker.schemas.transcript import MeetingAnalysisResponse
from worker.services.llm.router import LLMRouter

# Optional evaluation hook. Imported lazily via the package so that a failure
# in the evaluation layer can never break the transcript pipeline.
from worker.eval.pipeline import evaluate as _eval_pipeline

load_dotenv()

# LLM gateway with multi-provider failover. Degrades to Groq (the existing
# pipeline) when no other provider keys are configured, preserving behavior.
llm_router = LLMRouter.from_env()

# Groq client still used for transcription (Whisper).
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Transient failures that justify a retry
RETRYABLE_EXCEPTIONS = (Exception,)


def _run_evaluation(transcript: str, analysis: dict) -> dict:
    """Run the optional evaluation hook and return its report.

    Fully guarded: any failure in the evaluation layer is swallowed so the
    transcript pipeline is never affected. Returns an empty dict on error.
    """
    try:
        return _eval_pipeline(transcript, analysis)
    except Exception:
        return {}


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

    Uses ``generate_structured`` with the ``MeetingAnalysisResponse`` schema so
    the model output is validated deterministically. The returned dict is
    projected back to the original ``{summary, tasks, decisions}`` contract to
    avoid changing the downstream payload shape. A regex fallback is retained
    for resilience if schema validation exhausts retries.
    """
    prompt = f"""
You are an AI meeting assistant. Analyze the meeting transcript below and produce
a structured analysis. Extract:
- a short "summary" of the meeting
- "action_items": tasks/actions each with assignee, task, optional deadline and priority
- "key_decisions": decisions made, each with decision, optional impact and context
- "sentiment": optional sentiment analysis (overall_score in [-1,1] and per-speaker scores)

Transcript:
{text}
"""
    default = {"summary": "", "tasks": [], "decisions": []}
    try:
        result = llm_router.generate_structured(
            prompt, response_model=MeetingAnalysisResponse, temperature=0.2
        )
        return {
            "summary": result.summary,
            "tasks": [item.task for item in result.action_items],
            "decisions": [d.decision for d in result.key_decisions],
        }
    except Exception:
        # Fall back to the legacy regex/text parse so a schema issue never
        # silently drops previously-working behavior.
        ai_output = llm_router.generate(prompt, temperature=0.2)
        parsed = {"summary": "", "tasks": [], "decisions": []}
        try:
            match = re.search(r"\{.*\}", ai_output, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
        return parsed or default


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

        # Optional evaluation hook (never breaks the pipeline on failure).
        evaluation = _run_evaluation(text, analysis)

        payload = {"transcript": text, "analysis": analysis}
        if evaluation:
            payload["evaluation"] = evaluation
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

