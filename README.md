**Meeting Automation AI Agent 
**
An AI meeting-automation agent that converts recorded meetings into structured tasks and decisions, and automatically syncs them into Asana/Linear using LLM-based task extraction and transcription pipelines.

1. User uploads a meeting recording
2. App extracts tasks + decisions
3. App sends a simple summary via email

The Problem it solves,
Teams take notes during meetings but rarely turn them into action items, follow-ups, or project updates, leading to lost decisions.

The agent solves the problem smoothly with its designed workflow..
all the participants of the meeting get their actionable summary and tasks right after the meeting ends via mail

**TECH STACK **

python + FastAPI

openAI whisper for transcription 

meta llama 3.1 for task extraction 


AI agents can be made in less time with the rise of n8n
But I have used Python and FastAPI because it offers customization,flexibility,performance and scalability.
It gives a better edge over other technologies as it can handle complex ai logic and custom integrations.

---

## Distributed Async Workflow (Celery + Redis)

This project ships an optional distributed async layer that runs the long
LLM pipeline in the background so the web app never blocks on transcription
and extraction. It lives entirely under the `worker/` package and does not
touch the original synchronous `/process` route.

### Architecture

- `worker/core/celery_app.py` - Celery application bound to a Redis broker/backend.
- `worker/core/database.py` - SQLAlchemy engine/session (SQLite by default).
- `worker/models/job.py` - `jobs` table tracking job lifecycle (PENDING,
  PROCESSING, COMPLETED, FAILED) and the completed extraction payload.
- `worker/workflows/transcript_workflow.py` - the Celery task: transcribe ->
  extract -> persist result. Configured with exponential backoff + jitter retries.
- `worker/api/v1/endpoints/jobs.py` - new API:
  - `POST /api/v1/transcripts/process` - validate, persist as PENDING, enqueue,
    return `202 Accepted` with a `job_id`.
  - `GET /api/v1/jobs/{job_id}` - poll job status and fetch results on completion.
- `worker/services/llm/*` - a resilient LLM gateway with multi-provider
  failover (Groq, OpenAl, Anthropic, Google Gemini) guarded by a thread-safe
  circuit breaker. Falls back to Groq (the original pipeline) when only the
  Groq key is present, so behavior is preserved.

### Running

1. Start Redis, then a worker:
   `celery -A worker.core.celery_app.celery_app worker --queues=transcripts`
2. Run the web app normally:
   `uvicorn app:app`
3. Submit jobs via the new async API and poll their status with the job ID.

### Environment variables

Redis (defaults are shown):
- `REDIS_URL` (e.g. `redis://localhost:6379/0`)

LLM provider keys (the router fails over in this order where configured):
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Optional router tuning:
- `LLM_PRIMARY` and `LLM_FALLBACKS` (comma-separated) to choose provider order
- `LLM_CIRCUIT_ERROR_THRESHOLD`, `LLM_CIRCUIT_WINDOW_SECONDS`,
  `LLM_CIRCUIT_COOLDOWN_SECONDS`

### Deterministic Structured Output (Pydantic Schemas)

LLM extraction is enforced against typed Pydantic response models instead of
relying on regex over unstructured text:

- `worker/schemas/transcript.py` - the response contract
  (`MeetingAnalysisResponse`, `ActionItem`, `KeyDecision`, `SentimentAnalysis`).
- `worker/services/llm/base.py::generate_structured` - the shared default
  implementation: generates text, then validates it against the schema. A
  `StructuredOutputError` surfaces when validation fails (loud failures, no
  silent regex extraction).
- Native structured-output overrides where available: Groq (JSON mode) and
  OpenAI (strict JSON-schema `response_format`).
- The router exposes `generate_structured` with the same circuit-breaker /
  failover semantics as free-text generation.
- The workflow uses `generate_structured` and projects the result back to the
  legacy `{summary, tasks, decisions}` payload shape, keeping a regex fallback
  for resilience.

### Tests

```
python -m pytest tests/ -v
```
