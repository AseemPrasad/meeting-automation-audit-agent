# System Mental Model

How to think about this system as a unified whole.

---

## The Simplest Possible Explanation

You upload a meeting. You get back:
1. **What people said** (transcription)
2. **What people will do** (action items)
3. **What people decided** (decisions)

Behind the scenes, the system:
- Calls APIs (Groq Whisper, then an LLM)
- Handles failures (uses backup providers)
- Checks quality (makes sure answers are right)
- Tracks who can see what (multi-tenancy)
- Scales without blocking (async processing)

---

## The Model: Actors and Components

### Actors

#### Users (External)
- Upload recordings
- Authenticate with email/password
- Belong to a tenant (organization)
- Have roles (admin, member, viewer)

#### The Web App (FastAPI)
- Receives upload requests
- Validates JWT tokens
- Checks rate limits
- Queues jobs
- Returns job status

#### Celery Workers (Background)
- Process queued jobs
- Call external APIs
- Evaluate quality
- Store results

#### External Services
- **Groq API**: Transcription (primary)
- **LLM APIs**: GPT-4, Claude, Gemini (fallback)
- **Redis**: Queue, cache, rate limit store
- **Database**: Job and user storage

---

## Data Model Overview

```
┌─────────────────────────────────────────┐
│ User                                    │
├─────────────────────────────────────────┤
│ id (UUID)                              │
│ email                                  │
│ password_hash                          │
│ tenant_id → (Tenant)                   │
│ role: admin|member|viewer              │
└─────────────────────────────────────────┘
            │
            │ owns
            ▼
┌─────────────────────────────────────────┐
│ Job                                     │
├─────────────────────────────────────────┤
│ id (UUID)                              │
│ tenant_id                              │
│ status: PENDING|PROCESSING|COMPLETED   │
│ result_payload (JSON)                  │
│   └─ action_items[]                   │
│   └─ decisions[]                       │
│   └─ sentiment                         │
│ error (if failed)                      │
│ timestamps                             │
└─────────────────────────────────────────┘
```

**Key Principle**: Everything is tenant-scoped. A user in Tenant A cannot see jobs from Tenant B.

---

## Request Flow: The Happy Path

```
User Browser
│
├─1─ POST /api/v1/auth/login
│    Email + password
│    │
│    └──▶ Verify password, generate JWT
│          │
│          └──▶ Return JWT token
│
└─2─ POST /api/v1/transcripts/process
     JWT token + audio file
     │
     ├──▶ [FastAPI Route Handler]
     │    • Validate JWT (extract user, tenant)
     │    • Check rate limit (tenant-specific)
     │    • Validate file (is it audio?)
     │    • Create Job record (PENDING status)
     │    │
     │    ├──▶ [Enqueue Celery Task]
     │    │    │
     │    │    └──▶ Return 202 Accepted + job_id
     │    │
     │    └──▶ [Background: Celery Worker]
     │         • Transcribe (Groq Whisper)
     │         • Extract (LLM Router → structured output)
     │         • Evaluate (metrics + LLM judge)
     │         • Update Job (COMPLETED status + result_payload)
     │
     └─3─ GET /api/v1/jobs/{job_id}
          JWT token + job_id
          │
          └──▶ Query database (filtered by tenant_id)
               • If status == COMPLETED: Return results
               • If status == PENDING: Return status + ETA
               • If status == FAILED: Return error

User gets structured data:
{
  "action_items": [
    {"task": "...", "assignee": "...", "deadline": "..."}
  ],
  "decisions": [...],
  "sentiment": 0.75
}
```

---

## The Async Pattern Explained

### Why Async?

**Problem**: Processing a 1-hour meeting takes 30-60 seconds:
- Transcription: 20 seconds
- LLM extraction: 10 seconds
- Evaluation: 5 seconds

**Synchronous App** (bad):
```
POST /process
└─ Wait 35 seconds
   └─ Return result
   └─ User waits (or connection times out)
```

**This App** (good):
```
POST /process
├─ Create job
├─ Enqueue task
└─ Return 202 Accepted + job_id immediately

User polls: GET /jobs/{job_id}
├─ 1st poll (5 sec): {"status": "processing"}
├─ 2nd poll (10 sec): {"status": "processing"}
└─ 3rd poll (40 sec): {"status": "completed", "results": {...}}
```

**Benefit**: Web app responds instantly. Celery workers handle heavy lifting. Scales to thousands of concurrent uploads.

---

## The LLM Router: Resilience Pattern

### Single Provider (Fragile)

```
User Request
    │
    ├──▶ Groq API
    │    ├─ Success? Return
    │    └─ Failure? User error (503)
```

### Multi-Provider Router (Resilient)

```
User Request
    │
    ├──▶ Try Groq
    │    ├─ Success? Return
    │    └─ Failure? Continue...
    │
    ├──▶ Try OpenAI
    │    ├─ Success? Return
    │    └─ Failure? Continue...
    │
    ├──▶ Try Anthropic
    │    ├─ Success? Return
    │    └─ Failure? Continue...
    │
    └──▶ Try Gemini
         ├─ Success? Return
         └─ Failure? Return error
```

**Observable Evidence**:
- File: `worker/services/llm/router.py`
- Logic: Try each provider in order
- Fallback: Hard-coded order in config
- Circuit Breaker: After 3 failures, Groq gets 60-second timeout

**Result**: If Groq goes down, users don't notice. System transparently uses OpenAI instead.

---

## Multi-Tenancy: Complete Isolation

### The Problem It Solves

Company A and Company B both use this system. Must guarantee:
- Company A cannot see Company B's meetings
- Rate limits are per-company (Company A's heavy usage doesn't affect B)
- Authentication is per-company (same email allowed in A and B)

### How It Works

#### 1. Authentication Creates Tenant Context
```python
user = verify_jwt(token)
# Returns: User(id, tenant_id, role)
# Now we know which tenant this request is for
```

#### 2. Every Query is Filtered
```python
# ❌ BAD (ALL data exposed)
jobs = db.query(Job).all()

# ✅ GOOD (tenant-scoped)
jobs = db.query(Job).filter(Job.tenant_id == user.tenant_id).all()
```

#### 3. Rate Limits are Per-Tenant
```python
# Rate limit key includes tenant
redis_key = f"rate_limit:{user.tenant_id}:{endpoint}"
# Company A's limit is separate from Company B's
```

#### 4. RBAC (Role-Based Access Control)
```python
# Admin can do anything
if user.role == "admin":
    approve()

# Member can view their own jobs
elif user.role == "member":
    own_jobs = db.query(Job).filter(
        Job.tenant_id == user.tenant_id,
        Job.created_by == user.id
    )

# Viewer can only see jobs (no modify)
elif user.role == "viewer":
    check_permission("view_jobs")
```

**Result**: Complete data isolation. One database. Multiple organizations.

---

## Quality Evaluation Loop

### The Problem

LLMs sometimes hallucinate. Maybe the extraction is missing action items. How do you know if quality is good?

### The Solution: Dual Assessment

```
Extraction Result
    │
    ├──▶ Deterministic Metrics (FAST)
    │    • Faithfulness: Does extracted text appear in transcript?
    │    • Recall: What % of obvious items did we find?
    │    └─ Score: 0-1
    │
    └──▶ LLM-as-Judge (SLOWER)
         • Prompt LLM: "Is this extraction correct?"
         • LLM returns: score + reasoning
         • Fallback: Use deterministic score if LLM fails
         └─ Score: 0-1

    │
    ├──▶ Combined Score
    │
    └──▶ If score < threshold:
         Export to benchmark dataset (for future improvement)
```

**File**: `worker/eval/pipeline.py`

**Why This Matters**:
- Catch quality issues automatically
- Don't need human reviewers for every job
- Build dataset for continuous improvement
- Know which extractions are unreliable

---

## Caching: Cost Optimization

### The Problem

An LLM API call costs money:
- Groq: ~$0.02 per 1M input tokens
- OpenAI: ~$5 per 1M input tokens

If the same meeting is processed twice, pay twice.

### The Solution: Semantic Cache

```
First Request:
├─ Transcript hash
├─ Calculate embeddings
├─ Check Redis cache (miss)
└─ Call LLM
   └─ Store result in cache + embeddings

Second Request (same meeting):
├─ Transcript hash
├─ Calculate embeddings
├─ Check Redis cache (similar embeddings)
│  └─ Semantic similarity > 95%?
│     └─ Return cached result (no LLM call)
└─ Save $$$
```

**File**: `worker/services/cache/semantic_cache.py`

**Tradeoff**: Complexity vs. cost savings. For high-volume use, worth it.

---

## Error Handling: Layers of Defense

### Layer 1: Validation (Before Work)
```python
# Reject invalid requests early
if not file.endswith('.mp3'):
    raise ValidationError("Only MP3 supported")
```

### Layer 2: Authentication
```python
# Reject unauthenticated requests
if not token:
    raise AuthenticationError()
```

### Layer 3: Circuit Breaker
```python
# If provider is down, fail fast (don't retry)
if groq_circuit.is_open():
    raise CircuitBreakerOpen()
```

### Layer 4: Retry with Backoff
```python
# Transient errors get retried
@retry(max_attempts=3, backoff=exponential)
def call_llm():
    ...
```

### Layer 5: Fallback to Next Provider
```python
# If primary fails, use backup
try:
    return groq.query(prompt)
except:
    return openai.query(prompt)
```

### Layer 6: Graceful Degradation
```python
# If LLM judge fails, use deterministic metrics
try:
    return llm_judge(extraction)
except:
    return deterministic_metrics(extraction)
```

**Result**: System is resilient at every layer. Failures are handled, not fatal.

---

## The State of Things: Where Data Lives

```
┌─────────────────────────────────────────────────────────┐
│ Redis                                                   │
├─────────────────────────────────────────────────────────┤
│ • Job queue (Celery tasks)                             │
│ • Semantic cache (extracted results)                   │
│ • Rate limit counters (per tenant)                     │
│ • Circuit breaker state (per provider)                 │
│                                                         │
│ Volatile: Lost if Redis restarts                       │
│ Performance: Sub-millisecond access                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ SQLite / PostgreSQL                                     │
├─────────────────────────────────────────────────────────┤
│ • User records (auth data)                             │
│ • Job records (status + results)                       │
│ • Benchmark dataset (low-scoring extractions)          │
│                                                         │
│ Persistent: Survives restart                           │
│ Durability: Written to disk                            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Python Process Memory                                   │
├─────────────────────────────────────────────────────────┤
│ • In-memory rate limit fallback                        │
│ • Active Celery tasks                                  │
│ • OpenTelemetry buffer                                 │
│                                                         │
│ Ephemeral: Lost on crash                               │
│ Speed: Fastest access                                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ External APIs                                           │
├─────────────────────────────────────────────────────────┤
│ • Groq (transcription + LLM)                           │
│ • OpenAI (fallback LLM)                                │
│ • Anthropic (fallback LLM)                             │
│ • Google Gemini (fallback LLM)                         │
│                                                         │
│ Authoritative: Third-party owned                       │
│ Costs: Pay per call                                    │
└─────────────────────────────────────────────────────────┘
```

---

## Key Insights

### 1. Separation of Concerns is Strict
- Web layer (FastAPI) handles HTTP only
- Business logic layer (services) handles algorithms
- Data layer (SQLAlchemy) handles persistence
- Job layer (Celery) handles async work

Each layer can be tested independently.

### 2. Async is Everywhere
- Web requests are async (FastAPI)
- LLM calls are async (provider APIs)
- Job queue is async (Celery + Redis)
- Database queries could be async (but aren't)

**[Observable]** The system is designed for concurrency from the start.

### 3. Failure is Expected
- Every external API is expected to fail sometimes
- Circuit breaker prevents cascading failures
- Fallback providers handle single-provider outages
- Graceful degradation when features fail

**[Inferred]** The team expected to run this in production with unreliable dependencies.

### 4. Multi-Tenancy is Baked In
- Not retrofitted
- Every query is filtered by tenant
- Separate rate limits per tenant
- Separate user tables per tenant (via tenant_id column)

**[Observable]** This is designed as a SaaS product from the start.

### 5. Quality is Measured, Not Assumed
- Every extraction gets scored
- Low-scoring samples are exported
- Metrics are deterministic (no variance)
- LLM judgment provides semantic validation

**[Inferred]** The team knows that LLMs sometimes fail and built assessment into the pipeline.

---

## A Day in the Life: Detailed Example

### 9:00 AM: Alice's Day Starts

**Alice** works at Company A. She's a manager.

### 9:05 AM: Alice Uploads a Meeting

```
Browser
  │
  └─ POST /api/v1/transcripts/process
     Header: Authorization: Bearer eyJhbGc...
     Body: audio.mp3 (binary)
     
     ▼
     
     FastAPI Route: jobs.py:create_job()
     │
     ├─ Validate JWT
     │  • Decode token
     │  • Extract user_id, tenant_id
     │  • Result: User(id=123, tenant_id=AAA, role="member")
     │
     ├─ Check rate limit
     │  • Redis key: "rate_limit:AAA:/api/v1/transcripts/process"
     │  • Current: 45/120 requests this minute
     │  • Status: OK (continue)
     │
     ├─ Validate file
     │  • File type: audio/mpeg ✓
     │  • File size: 25 MB ✓
     │
     ├─ Create Job
     │  • INSERT into jobs table
     │  • id: uuid.uuid4()
     │  • tenant_id: AAA
     │  • status: "PENDING"
     │  • created_at: now()
     │
     ├─ Enqueue Task
     │  • Celery sends to Redis queue
     │  • Message: {"task": "process_transcript", "args": [job_id]}
     │
     └─ Return 202 Accepted
        {
          "job_id": "550e8400-e29b-41d4-a716-446655440000",
          "status": "PENDING",
          "message": "Transcription in progress. Check back in 30 seconds."
        }

Browser receives response immediately (10 ms).
Alice sees "Transcription in progress..." message.
```

### 9:06 AM: Behind the Scenes

```
Celery Worker
│
├─ Dequeue task from Redis
│  job_id: 550e8400-e29b-41d4-a716-446655440000
│
├─ Update Job
│  UPDATE jobs SET status='PROCESSING', started_at=now()
│
├─ Transcription: Groq Whisper
│  │
│  ├─ Read audio from S3 (or in-memory)
│  ├─ Call Groq API
│  └─ Result: Full transcript text (1200 words)
│     "Alice: We need to ship by Friday..."
│
├─ Extraction: LLM Router
│  │
│  ├─ Format prompt with transcript
│  │  "Extract action items from: Alice: We need to ship by Friday..."
│  │
│  ├─ Try Groq (primary)
│  │  └─ Success! Returns:
│  │     {
│  │       "action_items": [
│  │         {"task": "Ship feature", "assignee": "Bob", "deadline": "2026-08-15"}
│  │       ],
│  │       "decisions": [
│  │         {"decision": "Use React", "rationale": "team preference"}
│  │       ]
│  │     }
│  │  (If Groq failed, would try OpenAI, then Anthropic, then Gemini)
│  │
│  └─ Validate output against Pydantic schema
│     • All fields present? ✓
│     • Types correct? ✓
│     • Lengths reasonable? ✓
│
├─ Evaluation: Quality Check
│  │
│  ├─ Deterministic metrics
│  │  • Faithfulness: "ship feature" appears in transcript ✓ (100%)
│  │  • Recall: All obvious items found ✓ (95%)
│  │  • Overall: 0.95
│  │
│  └─ LLM Judge
│     • Prompt Claude: "Is this extraction faithful?"
│     • Claude: "Yes, everything is mentioned in the meeting." (0.98)
│     • Combined: 0.96
│
├─ Store Result
│  │
│  ├─ Serialize to JSON
│  ├─ UPDATE jobs
│  │  SET status='COMPLETED',
│  │      result_payload='{...}',
│  │      completed_at=now()
│  │
│  └─ Database record now contains extraction results
│
└─ Mark Task Complete
   Redis queue updated
```

### 9:06:45 AM: Alice Checks Status

```
Browser
  │
  └─ GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000
     Header: Authorization: Bearer eyJhbGc...
     
     ▼
     
     FastAPI Route: jobs.py:get_job()
     │
     ├─ Validate JWT
     │  • Extract user_id, tenant_id: AAA
     │
     ├─ Query Database
     │  SELECT * from jobs
     │  WHERE id = '550e8400-e29b-41d4-a716-446655440000'
     │  AND tenant_id = 'AAA'
     │  (Multi-tenancy ensures Alice only sees her jobs)
     │
     ├─ Return Result
     │  {
     │    "status": "COMPLETED",
     │    "results": {
     │      "action_items": [...],
     │      "decisions": [...],
     │      "sentiment": 0.75
     │    }
     │  }
     │
     └─ Browser renders
        Shows action items, decisions, sentiment score
        Alice can now:
        - Review extracted data
        - Export to CSV/JSON
        - Share with team
```

### Later: Bob (at Company B) Uploads the Same Meeting File

```
Wait... what happens?

Bob's request:
  ├─ tenant_id = BBB (Company B)
  ├─ Creates new Job
  │  (Bob has no access to Alice's job from Company A)
  ├─ Enqueues new Celery task
  └─ Processes independently

Database:
  Job for Alice:   tenant_id = AAA
  Job for Bob:     tenant_id = BBB
  
Query from Alice: Only sees AAA (multi-tenancy enforcement)
Query from Bob:   Only sees BBB (multi-tenancy enforcement)

→ Same meeting, separate processing, zero cross-pollution
```

---

## Summary: Mental Model

**The System is a Pipeline**:
1. Accept (HTTP) → Validate → Authenticate → Queue
2. Process (Background) → Transcribe → Extract → Evaluate
3. Return (Polling) → Status → Results → Persist

**The System is Resilient**:
1. Failures are expected
2. Multiple fallbacks at each stage
3. Graceful degradation

**The System is Isolated**:
1. Multi-tenancy by design
2. Rate limits per tenant
3. Role-based access control

**The System is Observable**:
1. Every job has status
2. Every extraction is evaluated
3. Metrics and traces available

---

**Next Step**: Read [Architecture Overview](04-architecture-overview.md) to understand the formal patterns.
