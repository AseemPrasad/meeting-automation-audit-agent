# Architecture Overview

Formal architectural patterns and high-level design.

---

## Architectural Style

This is a **Microservices-Inspired Monolith** with **Async Task Queue** pattern.

### Why Not "Microservices"?
- Single codebase (monolith)
- Single database (no per-service DB)
- Single deployment unit

### Why "Microservices-Inspired"?
- Loosely coupled components (LLM, RAG, eval are independent)
- Each subsystem has clear interface
- Could be extracted to separate services later
- Event-driven via Celery (message broker between layers)

**[Inferred]** Designed to scale within a monolith, then split into services if needed.

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│ Presentation Layer                                  │
│ ├─ FastAPI app.py                                  │
│ ├─ REST endpoints (api/v1/endpoints/)               │
│ └─ HTML templates (templates/index.html)            │
├─────────────────────────────────────────────────────┤
│ Middleware Layer                                    │
│ ├─ Authentication (JWT validation)                 │
│ ├─ Rate limiting (token bucket)                    │
│ ├─ Request tracing (OpenTelemetry)                 │
│ └─ CORS, compression, etc.                         │
├─────────────────────────────────────────────────────┤
│ Service Layer                                       │
│ ├─ LLM Service (router, providers, circuit breaker)│
│ ├─ Embedding Service (vectors)                     │
│ ├─ Cache Service (semantic cache)                  │
│ ├─ Transcription Service (Groq Whisper)            │
│ └─ Evaluation Service (metrics, judge, export)     │
├─────────────────────────────────────────────────────┤
│ Business Logic Layer                                │
│ ├─ Celery workflows (transcript_workflow.py)       │
│ ├─ Agentic extraction (agents/)                    │
│ ├─ RAG pipeline (rag/)                             │
│ └─ Validation logic (Pydantic schemas)             │
├─────────────────────────────────────────────────────┤
│ Data Access Layer                                   │
│ ├─ SQLAlchemy ORM (database.py)                    │
│ ├─ Models (job.py, user.py, cache.py)              │
│ └─ Repository pattern (implicit via ORM)           │
├─────────────────────────────────────────────────────┤
│ Infrastructure Layer                                │
│ ├─ Database (SQLite/PostgreSQL)                    │
│ ├─ Cache (Redis)                                   │
│ ├─ Queue (Redis + Celery)                          │
│ └─ External APIs (Groq, OpenAI, Anthropic, etc.)  │
└─────────────────────────────────────────────────────┘
```

---

## Component Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     FastAPI Web App                      │
│  Receives requests, validates, routes, returns responses │
└─────────────────────────┬────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐      ┌────────┐      ┌─────────────┐
    │   Auth  │      │  Jobs  │      │   Middleware│
    │ Endpoint│      │Endpoint│      │  (Rate Limit│
    │         │      │        │      │   Auth...)  │
    └────┬────┘      └────┬───┘      └─────────────┘
         │                │
         │ (JWT issued)   │ (Jobs enqueued)
         │                │
         ▼                ▼
    ┌─────────────────────────────────────┐
    │         Redis                       │
    │  ├─ Job Queue (Celery)             │
    │  ├─ Semantic Cache                 │
    │  ├─ Rate Limit Counters            │
    │  └─ Circuit Breaker State          │
    └────────┬───────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────┐
    │    Celery Workers (Background)   │
    │  Process queued jobs in parallel │
    │                                  │
    │  ┌──────────────────────────┐   │
    │  │ Transcript Workflow       │   │
    │  │ 1. Transcribe (Groq)      │   │
    │  │ 2. Extract (LLM Router)   │   │
    │  │ 3. Evaluate (Judge+Metrics│   │
    │  │ 4. Persist results        │   │
    │  └────────┬─────────────────┘   │
    │           │                      │
    │  ┌────────┴──────────────────┐  │
    │  ▼                           ▼  │
    │ ┌──────────────────┐  ┌──────┐ │
    │ │ LLM Router       │  │Eval  │ │
    │ │ ├─ Groq          │  │Pipe  │ │
    │ │ ├─ OpenAI        │  │line  │ │
    │ │ ├─ Anthropic     │  │      │ │
    │ │ └─ Gemini        │  └──────┘ │
    │ │ + Circuit Breaker│           │
    │ └──────────────────┘           │
    └──────────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────┐
    │   SQLite/PostgreSQL          │
    │  ├─ User records             │
    │  ├─ Job records              │
    │  └─ Benchmark dataset        │
    └──────────────────────────────┘

    ┌──────────────────────────────┐
    │  External LLM APIs           │
    │  ├─ Groq (primary)           │
    │  ├─ OpenAI (fallback 1)      │
    │  ├─ Anthropic (fallback 2)   │
    │  └─ Gemini (fallback 3)      │
    └──────────────────────────────┘
```

---

## Concurrency Model

### FastAPI: Async Request Handling
```python
# Every endpoint is async
@app.post("/api/v1/transcripts/process")
async def process_transcript(file: UploadFile):
    # Non-blocking I/O
    # Can handle thousands of concurrent requests
    return {"job_id": job_id}  # Return immediately
```

**Characteristics**:
- Event loop based (asyncio)
- Non-blocking I/O
- Many concurrent requests per thread
- Workers: Uvicorn processes (configurable, usually 4-8)

### Celery: Distributed Task Queue
```python
# Tasks are enqueued, processed asynchronously
@celery_app.task
def process_transcript(job_id: str):
    # Blocking I/O is OK here
    # Long-running operations
    # Retries, timeouts handled
    ...
```

**Characteristics**:
- Independent worker processes
- Work-stealing queue
- Multiple workers can process in parallel
- Redis broker for communication
- Each task runs independently

### Interaction Pattern
```
Request → Enqueue → Return 202
         ↓
        Redis Queue
         ↓
    Celery Worker
         ↓
      Process Job
         ↓
      Update Database
         ↓
Client polls for results
```

**Result**: Horizontal scalability. Add more Celery workers to increase throughput.

---

## Dependency Injection

### FastAPI Dependencies
```python
# Security dependency
async def get_current_user(token: str) -> User:
    # Injected into every protected route
    ...

@app.get("/jobs")
async def list_jobs(user: User = Depends(get_current_user)):
    # user is automatically provided
    ...
```

**Pattern**: Dependency injection via FastAPI's `Depends()`.

**Benefit**: Security logic is centralized, tested once, used everywhere.

### Database Sessions
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    # db session provided, closed automatically
    ...
```

**Pattern**: Context manager for resource cleanup.

### Service Injection (Implicit)
```python
# Services are singletons, accessed via imports
from worker.services.llm.router import llm_router

@celery_app.task
def extract_content(job_id: str):
    # llm_router is singleton, shared across tasks
    response = await llm_router.query(prompt)
```

**Pattern**: Module-level singletons. Not explicit DI, but pragmatic.

---

## Communication Patterns

### Request-Response (Synchronous)
```
FastAPI Route
    ├─ Query database
    ├─ Call external API (with timeout)
    └─ Return JSON response
```

**Used for**: Authentication, job polling, metadata retrieval.

**Characteristics**: Fast, simple, blocks if external service is slow.

### Message Queue (Asynchronous)
```
FastAPI Route
    └─ Enqueue Celery task
       ↓
    Redis Queue
       ↓
    Celery Worker
       ├─ Process
       └─ Store result
       
    (Caller moves on immediately)
```

**Used for**: Long-running jobs (transcription, extraction).

**Characteristics**: Decoupled, scalable, non-blocking.

### Event-Based (Implicit)
```
Job completion
    └─ Database updated
    
Polling client
    ├─ Checks database
    └─ Sees new status
```

**Pattern**: Polling (not pub/sub).

**Characteristics**: Simple, eventual consistency.

---

## API Architecture

### REST Principles
- **Verb**: HTTP methods (GET, POST, PUT, DELETE)
- **Noun**: Resource paths (/jobs, /users, /auth)
- **Status**: HTTP status codes (200, 201, 202, 400, 401, 403, 429, 500)
- **Representation**: JSON

### API Versioning
```
/api/v1/transcripts/process
       ↑
       └─ Version in URL (allows v2, v3 later)
```

**Strategy**: URL versioning.

**Benefit**: Can deprecate old versions, clients don't auto-upgrade.

### Response Patterns

**Immediate Success**:
```json
POST /api/v1/transcripts/process
Response: 202 Accepted
{
  "job_id": "uuid",
  "status": "PENDING",
  "message": "Processing started"
}
```

**Polling Success**:
```json
GET /api/v1/jobs/{job_id}
Response: 200 OK
{
  "status": "COMPLETED",
  "results": {
    "action_items": [...],
    "decisions": [...],
    "sentiment": 0.75
  }
}
```

**Error Response**:
```json
Response: 400 Bad Request or 500 Internal Server Error
{
  "detail": "Error message",
  "error_code": "optional"
}
```

---

## Error Handling Architecture

### Error Classification

| Type | Example | Handling |
|------|---------|----------|
| Validation Error | Invalid file type | 400 Bad Request (client error) |
| Authentication Error | Invalid JWT | 401 Unauthorized |
| Authorization Error | User lacks role | 403 Forbidden |
| Rate Limit | Too many requests | 429 Too Many Requests |
| Not Found | Job doesn't exist | 404 Not Found |
| Server Error | LLM API down | 500 Internal Server Error (with retry) |
| Timeout | Request takes >30s | 504 Gateway Timeout |

### Error Propagation

```
Client Error (validation)
    └─ Caught at route handler
    └─ Return immediately (400)

External API Error (Groq down)
    ├─ Caught in service layer
    ├─ Try fallback provider
    ├─ If all fail: Update job status to FAILED
    └─ Client polls and sees error

Internal Error (database crash)
    ├─ Logged with full stack trace
    ├─ Return generic "Internal Error" message
    └─ Operator investigates logs
```

**Principle**: [Observable] Errors are caught at appropriate layers, not bubbled.

---

## Transaction Management

### Database Transactions
```python
# SQLAlchemy handles transaction boundaries
db = Session()
try:
    job = Job(...)
    db.add(job)
    db.commit()  # Atomic write
except Exception:
    db.rollback()  # Undo on error
finally:
    db.close()
```

**Characteristics**: ACID guarantees for database operations.

### Job Idempotency
```python
# Celery retries can cause duplicate processing
# Solution: check if job already completed before processing
if job.status == "COMPLETED":
    return  # Already processed

job.status = "PROCESSING"
db.commit()
# Now process...
```

**Pattern**: Idempotent task design. Safe to retry.

---

## Scalability Considerations

### Horizontal Scaling
```
Load Balancer
    ├─ FastAPI (instance 1)
    ├─ FastAPI (instance 2)
    └─ FastAPI (instance 3)
            │
            └──→ Shared Redis
                 Shared Database

Celery Workers (separate machines)
    ├─ Worker 1
    ├─ Worker 2
    └─ Worker N
            │
            └──→ Same Redis
                 Same Database
```

**Pattern**: Stateless services. Scale by adding instances.

### Rate Limiting at Scale
```
Tenant A: 120 requests/min limit
Tenant B: 1000 requests/min limit (paying customer)

Redis tracks:
  rate_limit:A:/api/v1/transcripts/process
  rate_limit:B:/api/v1/transcripts/process
```

**Benefit**: Different tiers have different limits. No cross-contamination.

### Job Queue Backlog
```
Requests arrive faster than Celery can process?
    ├─ Jobs queue up in Redis
    ├─ New workers pick up jobs
    └─ Eventually catch up

No data loss: Redis persists queue
```

**Characteristic**: Queue is durable. Can survive application restarts.

---

## Key Architectural Decisions

### Decision 1: Async Architecture for Web Layer
**What**: FastAPI + Uvicorn (async/await)

**Why**: [Observable]
- Handle thousands of concurrent requests per server
- Ideal for I/O-bound operations (database, Redis, HTTP calls)
- Matches Python's asyncio ecosystem

**Tradeoff**: Complexity. Requires async-aware code.

---

### Decision 2: Celery for Long-Running Work
**What**: Background job queue

**Why**: [Observable]
- Don't block HTTP requests for 30+ second operations
- Retry failed jobs automatically
- Scale workers independently from web servers

**Tradeoff**: Distributed system complexity. New failure modes (queue empty, worker down).

---

### Decision 3: Multi-Provider LLM Router
**What**: Try Groq, then OpenAI, then Anthropic, then Gemini

**Why**: [Observable]
- Groq is fast and cheap (primary)
- OpenAI is reliable (fallback)
- Anthropic has strong capabilities (fallback)
- Gemini is free tier (last resort)

**Rationale**: [Inferred] Maximize uptime (any provider going down doesn't break service) and cost-efficiency (cheapest provider first).

**Tradeoff**: Complexity. Must handle 4 different APIs.

---

### Decision 4: Semantic Caching
**What**: Check Redis for similar transcripts before calling LLM

**Why**: [Inferred]
- Same meeting processed twice? Use cached result.
- Save API costs (LLM call ~ $0.05, cache miss ~ $0.001).
- Improve performance (sub-millisecond vs. 5-10 seconds).

**Tradeoff**: Complexity. Must manage embedding similarity, cache eviction.

---

### Decision 5: SQLite for Development, PostgreSQL for Production
**What**: Database URL configurable

**Why**: [Observable]
- SQLite: Zero-config for developers (file-based DB)
- PostgreSQL: Scalable for production (connection pooling, replication)

**Rationale**: [Inferred] Reduce local setup friction while maintaining production compatibility.

**Tradeoff**: ORM must be compatible with both. SQLAlchemy handles it.

---

## Non-Functional Characteristics

### Performance
- **Transcription**: 20-30 seconds (depends on audio length)
- **Extraction**: 5-10 seconds (LLM latency)
- **Evaluation**: 2-5 seconds (metrics + judge)
- **Polling**: <100 ms (database query)

### Reliability
- **Provider Availability**: 99.9%+ (multiple fallbacks)
- **Data Durability**: Database write = persistent (ACID)
- **Queue Durability**: Redis persistence (can recover jobs after restart)

### Security
- **Authentication**: JWT (stateless)
- **Authorization**: RBAC (admin/member/viewer)
- **Data Isolation**: Multi-tenant (tenant_id on all queries)
- **Rate Limiting**: Per-tenant token bucket

### Observability
- **Logging**: Application logs + structured logs
- **Tracing**: OpenTelemetry (end-to-end request tracing)
- **Metrics**: Prometheus (request count, latency, errors)
- **Job Status**: Polling via GET /jobs/{job_id}

---

**Next Step**: Read [Component Architecture](05-component-architecture.md) for deep dives into each subsystem.
