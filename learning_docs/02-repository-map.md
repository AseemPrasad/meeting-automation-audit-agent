# Repository Map

Complete inventory and explanation of every significant file and directory.

---

## Directory Tree Overview

```
meeting-automation-mvp/
├── app.py                              [ENTRY POINT]
├── requirements.txt                    [DEPENDENCIES]
├── .env                                [CONFIGURATION]
├── .gitignore                          [GIT CONFIG]
├── jobs.db                             [SQLITE DATABASE]
│
├── templates/
│   └── index.html                      [WEB UI]
├── static/
│   └── style.css                       [WEB UI STYLES]
│
├── tests/                              [TEST SUITE - 13 modules]
│   ├── test_agents.py
│   ├── test_security.py
│   ├── test_eval_pipeline.py
│   ├── test_router.py
│   ├── test_pipeline.py
│   ├── test_retriever.py
│   ├── test_structured_output.py
│   ├── test_semantic_cache.py
│   ├── test_circuit_breaker.py
│   ├── test_indexer.py
│   ├── test_pricing_usage.py
│   ├── test_chunker.py
│   ├── test_reranker.py
│   └── __init__.py
│
└── worker/                             [MAIN APPLICATION PACKAGE]
    ├── __init__.py
    │
    ├── core/                           [INFRASTRUCTURE & CONFIG]
    │   ├── celery_app.py               [CELERY SETUP]
    │   ├── database.py                 [DATABASE ORM]
    │   ├── security.py                 [AUTH & RBAC]
    │   └── telemetry.py                [OBSERVABILITY]
    │
    ├── models/                         [DATABASE MODELS]
    │   ├── job.py                      [JOB PERSISTENCE]
    │   ├── user.py                     [USER & TENANT]
    │   └── cache.py                    [CACHE METADATA]
    │
    ├── api/
    │   └── v1/
    │       └── endpoints/              [REST API ROUTES]
    │           ├── jobs.py             [JOB ENDPOINTS]
    │           └── auth.py             [AUTH ENDPOINTS]
    │
    ├── middleware/                     [REQUEST PROCESSING]
    │   ├── rate_limit.py               [RATE LIMITING]
    │   └── metrics.py                  [OBSERVABILITY]
    │
    ├── workflows/                      [CELERY TASKS]
    │   └── transcript_workflow.py       [MAIN ORCHESTRATION]
    │
    ├── services/                       [BUSINESS LOGIC]
    │   ├── llm/                        [LLM GATEWAY]
    │   │   ├── router.py               [FAILOVER LOGIC]
    │   │   ├── base.py                 [ABSTRACT BASE]
    │   │   ├── config.py               [CONFIGURATION]
    │   │   ├── pricing.py              [COST ESTIMATION]
    │   │   ├── usage.py                [TOKEN ESTIMATION]
    │   │   ├── circuit_breaker.py      [FAULT TOLERANCE]
    │   │   ├── prompting.py            [PROMPT TEMPLATES]
    │   │   └── providers/              [API ADAPTERS]
    │   │       ├── groq.py
    │   │       ├── openai.py
    │   │       ├── anthropic.py
    │   │       └── gemini.py
    │   │
    │   ├── embeddings/                 [VECTOR EMBEDDINGS]
    │   │   └── vector_provider.py
    │   │
    │   └── cache/                      [SEMANTIC CACHE]
    │       └── semantic_cache.py
    │
    ├── rag/                            [RETRIEVAL-AUGMENTED GENERATION]
    │   ├── chunker.py                  [TEXT SPLITTING]
    │   ├── indexer.py                  [VECTOR + LEXICAL INDEX]
    │   ├── retriever.py                [HYBRID SEARCH]
    │   ├── reranker.py                 [RELEVANCE RANKING]
    │   └── pipeline.py                 [RAG ORCHESTRATION]
    │
    ├── agents/                         [AGENTIC EXTRACTION]
    │   ├── graph.py                    [DAG EXECUTOR]
    │   ├── state.py                    [AGENT STATE]
    │   └── nodes/                      [PROCESSING NODES]
    │       ├── cleaner.py
    │       ├── extractor.py
    │       ├── auditor.py
    │       └── inspector.py
    │
    ├── eval/                           [QUALITY EVALUATION]
    │   ├── pipeline.py                 [ORCHESTRATOR]
    │   ├── metrics.py                  [DETERMINISTIC SCORING]
    │   ├── judge.py                    [LLM-AS-JUDGE]
    │   └── dataset_exporter.py         [BENCHMARK EXPORT]
    │
    ├── schemas/                        [DATA MODELS]
    │   ├── transcript.py               [OUTPUT SCHEMA]
    │   └── agent.py                    [AGENT SCHEMA]
    │
    └── __init__.py
```

---

## Root Level Files

### `app.py` [ENTRY POINT]
**Purpose**: FastAPI application factory and route mounting

**Key Contents**:
- `FastAPI()` app instantiation
- Middleware registration (rate limiting, metrics)
- Router mounting (auth routes, job routes)
- Synchronous `/process` endpoint (backward compatibility)

**Significance**: Entry point for the entire application. Everything flows from here.

**Lines of Code**: ~100

**Read this first**: This is where you start to understand the overall structure.

---

### `requirements.txt`
**Purpose**: Python package dependencies

**Key Dependencies**:
```
fastapi              # Web framework
uvicorn             # ASGI server
celery              # Job scheduling
redis               # Cache & queue
sqlalchemy          # Database ORM
pydantic            # Data validation
groq                # Transcription & LLM
openai              # Fallback LLM provider
anthropic           # Fallback LLM provider
google-generativeai # Fallback LLM provider
instructor          # Structured output
pyjwt               # JWT auth
passlib[bcrypt]     # Password hashing
python-dotenv       # Environment variables
opentelemetry-*     # Observability
sentence-transformers # Embeddings
```

**Significance**: Shows the technology choices. Notice multi-provider LLM support and comprehensive observability.

---

### `.env`
**Purpose**: Environment variable configuration

**Key Variables**:
```
# LLM Providers
GROQ_API_KEY                     # Required
OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY  # Optional

# Infrastructure
REDIS_URL                        # Default: redis://localhost:6379
DATABASE_URL                     # Default: sqlite:///./jobs.db

# Authentication
SECRET_KEY                       # JWT signing key
JWT_EXPIRES_MINUTES             # Default: 60

# Rate Limiting
RATE_LIMIT_PER_MINUTE           # Default: 120

# Circuit Breaker Tuning
LLM_CIRCUIT_ERROR_THRESHOLD     # Errors before open
LLM_CIRCUIT_WINDOW_SECONDS      # Time window
LLM_CIRCUIT_COOLDOWN_SECONDS    # Recovery time
```

**Significance**: Configuration is externalized (12-factor app principle). All secrets and settings are environment-driven.

---

### `.gitignore`
**Notable Entries**:
```
venv/
__pycache__/
*.pyc
jobs.db              # Don't commit local SQLite
.env                 # Don't commit secrets
temp/
```

---

### `jobs.db`
**Purpose**: SQLite database for local development

**Significance**: In production, replaced with PostgreSQL via `DATABASE_URL`. This is why initialization is idempotent.

---

## Worker Package Structure

### `worker/core/` [INFRASTRUCTURE]

#### `celery_app.py`
**Purpose**: Celery configuration and task registration

**What It Does**:
- Creates Celery app instance
- Configures Redis broker
- Registers task routes
- Sets up serialization

**Key Concept**: Centralized Celery configuration. Tasks are registered here.

**References**: Used by job endpoints to enqueue tasks.

---

#### `database.py`
**Purpose**: SQLAlchemy ORM setup and database initialization

**What It Does**:
- Creates SQLAlchemy engine from `DATABASE_URL`
- Establishes session factory
- Defines `init_db()` for creating tables
- Provides `get_db()` dependency for routes

**Key Concept**: Session management is centralized. FastAPI routes get sessions via dependency injection.

**Idempotency**: `init_db()` uses `create_all()` which only creates missing tables.

---

#### `security.py`
**Purpose**: Authentication, authorization, and password utilities

**Key Functions**:
- `hash_password()` - bcrypt hashing
- `verify_password()` - Constant-time comparison
- `create_access_token()` - JWT creation
- `verify_token()` - JWT validation
- `get_current_user()` - FastAPI dependency for auth
- `require_role()` - RBAC decorator

**Significance**: Security is centralized. Every protected endpoint uses these utilities.

**Pattern**: Dependency injection for FastAPI (get_current_user is a route parameter).

---

#### `telemetry.py`
**Purpose**: OpenTelemetry instrumentation setup

**What It Does**:
- Configures tracing providers
- Instruments FastAPI requests
- Sets up metric exporters
- Provides decorators for manual instrumentation

**Significance**: Observability is built-in from the start, not added later.

---

### `worker/models/` [DATABASE MODELS]

#### `job.py`
**Purpose**: ORM model for job persistence

**Key Fields**:
- `id` (UUID) - Unique job identifier
- `tenant_id` - Tenant scoping
- `status` (PENDING, PROCESSING, COMPLETED, FAILED)
- `result_payload` - Serialized extraction results
- `error` - Error message if failed
- `timestamps` - created_at, started_at, completed_at

**Significance**: Job state is persistent. Enables retry, audit trail, and polling.

**Design**: Status is an enum, not free-form string (prevents typos).

---

#### `user.py`
**Purpose**: ORM model for users and tenant association

**Key Fields**:
- `id` - User identifier
- `email` - Unique per tenant
- `password_hash` - Bcrypt hash
- `tenant_id` - Tenant scoping
- `role` - admin, member, or viewer
- `is_active` - Soft delete support

**Significance**: Multi-tenancy is modeled at the database layer. Every user belongs to a tenant.

---

#### `cache.py`
**Purpose**: ORM model for cache metadata

**Key Fields**:
- `text_hash` - SHA256 hash of input text
- `cache_hits`, `cache_misses` - Statistics
- `last_accessed` - For LRU eviction

**Significance**: Allows observability into cache performance. Not strictly necessary but shows monitoring mindset.

---

### `worker/api/v1/endpoints/` [REST API]

#### `jobs.py`
**Purpose**: Job processing endpoints

**Endpoints**:
```
POST /api/v1/transcripts/process
├─ Input: audio file + metadata
├─ Output: 202 Accepted + job_id
└─ Action: Enqueue Celery task

GET /api/v1/jobs/{job_id}
├─ Input: job_id
├─ Output: 200 OK + status + results (if ready)
└─ Action: Query database
```

**Significance**: Implements the 202 async pattern. User gets immediate response; results arrive later.

**Pattern**: FastAPI async routes that interact with Celery.

---

#### `auth.py`
**Purpose**: Authentication endpoints

**Endpoints**:
```
POST /api/v1/auth/register
├─ Input: email + password
├─ Output: JWT token
└─ Action: Create user, hash password, issue token

POST /api/v1/auth/login
├─ Input: email + password
├─ Output: JWT token (if credentials valid)
└─ Action: Verify password, issue token

GET /api/v1/auth/me
├─ Input: JWT token
├─ Output: Current user info
└─ Requirement: Authenticated
```

**Significance**: Stateless authentication (JWT). No server-side sessions.

**Pattern**: Standard OAuth-like flow adapted for API.

---

### `worker/middleware/` [REQUEST PROCESSING]

#### `rate_limit.py`
**Purpose**: Per-tenant rate limiting

**Implementation**: Token bucket algorithm
- Redis as primary (distributed)
- In-memory dict as fallback (if Redis unavailable)

**Mechanism**:
- Key: `rate_limit:{tenant_id}:{endpoint}`
- Tokens: Replenish at configured rate
- Rejection: 429 Too Many Requests

**Significance**: Prevents abuse without modifying application code.

---

#### `metrics.py`
**Purpose**: Request/response observability

**What It Tracks**:
- Request duration
- Response status
- Error rates
- Cache hits/misses

**Significance**: Enables operational visibility. Required for debugging and optimization.

---

### `worker/workflows/` [CELERY TASKS]

#### `transcript_workflow.py`
**Purpose**: Main business logic orchestration

**Celery Task Flow**:
```
@celery_app.task
process_transcript()
├─ 1. Transcribe audio (Groq Whisper)
├─ 2. Extract structured data (LLM Router)
├─ 3. Evaluate quality (Metrics + Judge)
├─ 4. Export low-scoring samples (Benchmarking)
└─ 5. Persist result to database
```

**Significance**: Heart of the system. This is where the actual work happens.

**Pattern**: Celery task = pure function that reads from DB, calls APIs, writes results.

---

### `worker/services/llm/` [LLM GATEWAY]

#### `router.py`
**Purpose**: Multi-provider LLM orchestration with failover

**Key Logic**:
```python
Primary:     Groq (fast, cheap)
Fallback 1:  OpenAI (reliable)
Fallback 2:  Anthropic (quality)
Fallback 3:  Gemini (last resort)
```

**Features**:
- Automatic failover on error
- Circuit breaker (open after repeated failures)
- Cost estimation
- Token tracking

**Significance**: Reliability. If one provider fails, others take over automatically.

---

#### `base.py`
**Purpose**: Abstract base class for LLM providers

**Interface**:
```python
class LLMProvider:
    async def query()        # Send prompt, get response
    async def structured()   # Query with schema validation
    async def stream()       # Streaming responses
    estimate_tokens()        # Cost calculation
```

**Pattern**: Strategy pattern. Easy to add new providers.

---

#### `providers/`
**Purpose**: Adapter implementations for each LLM

**groq.py**:
- Uses Groq API
- Supports JSON mode
- Function calling support

**openai.py**:
- Uses OpenAI API
- Strict JSON schema validation
- Fallback for structured output

**anthropic.py**:
- Uses Claude API
- Structured output via tool use
- Strong text understanding

**gemini.py**:
- Uses Google Gemini API
- JSON mode
- Free tier available

**Significance**: Pluggable providers. Each adapter handles provider-specific quirks.

---

#### `circuit_breaker.py`
**Purpose**: Fault tolerance mechanism

**States**:
- **CLOSED**: Requests pass through (normal)
- **OPEN**: Requests fail fast (provider down)
- **HALF_OPEN**: Try again after cooldown

**Transition Logic**:
```
CLOSED --[consecutive errors]--> OPEN
OPEN  --[cooldown complete]----> HALF_OPEN
HALF_OPEN --[success]----------> CLOSED
HALF_OPEN --[failure]----------> OPEN
```

**Significance**: Prevents thundering herd. If Groq is down, don't hammer it.

---

#### `pricing.py`
**Purpose**: Cost estimation

**What It Does**:
- Token counting (heuristic estimation)
- Rate lookup ($/1M tokens per provider)
- Cost calculation (tokens × rate)

**Significance**: Budget tracking. Know your spend before it explodes.

---

### `worker/rag/` [RETRIEVAL-AUGMENTED GENERATION]

#### `chunker.py`
**Purpose**: Split transcript into searchable chunks

**Method**: Overlapping sliding window
- Chunk size: Configurable (e.g., 512 tokens)
- Overlap: 50% (preserves context at boundaries)

**Why**: Raw transcript is too large for vector search. Chunks are digestible.

---

#### `indexer.py`
**Purpose**: Build searchable indexes

**Two Indexes**:
1. **Dense**: Vector embeddings (semantic search)
2. **Sparse**: BM25 (lexical search)

**Significance**: Hybrid search catches both semantic and keyword matches.

---

#### `retriever.py`
**Purpose**: Find relevant chunks given a query

**Algorithm**:
1. Search both dense and sparse indexes
2. Merge results (BM25 + vector similarity)
3. Return top-k chunks

**Use Case**: If extraction is uncertain about context, retrieve relevant parts.

---

#### `reranker.py`
**Purpose**: Re-rank retrieval results by relevance

**Method**: Cross-encoder model (more accurate than bi-encoder)

**Significance**: Prevents garbage-in, garbage-out. Only return truly relevant chunks.

---

### `worker/agents/` [AGENTIC EXTRACTION]

#### `graph.py`
**Purpose**: DAG (directed acyclic graph) executor

**What It Does**:
1. Define processing nodes (functions)
2. Define edges (dependencies)
3. Execute nodes in dependency order
4. Handle human-in-the-loop pauses

**Significance**: Enables complex multi-step extraction with checkpoints.

---

#### `state.py`
**Purpose**: Mutable state passed between nodes

**Fields**:
- `transcript` - Raw text
- `extracted_items` - Extracted action items
- `decisions` - Extracted decisions
- `quality_score` - Confidence
- `human_review_needed` - Flag for manual review

**Pattern**: Passing mutable object through pipeline (vs. return values).

---

#### `nodes/`
**Purpose**: Individual processing steps

**cleaner.py**: Normalize text (remove filler words, etc.)

**extractor.py**: Extract tasks and decisions (calls LLM)

**auditor.py**: Validate extracted data (checks consistency)

**inspector.py**: Quality assessment (confidence scoring)

---

### `worker/eval/` [QUALITY EVALUATION]

#### `pipeline.py`
**Purpose**: Orchestrate quality evaluation

**Steps**:
1. Run deterministic metrics (faithfulness, recall)
2. Run LLM-as-Judge (semantic validation)
3. Export low-scoring samples
4. Return combined score

**Significance**: Quality is measured, not assumed. Low scores trigger investigation.

---

#### `metrics.py`
**Purpose**: Deterministic quality scoring

**Metrics**:
- **Faithfulness**: Does extracted text appear in transcript?
- **Recall**: What % of ground truth did we extract?
- **Overall**: Weighted combination

**Why Deterministic**: No variance between runs. Reproducible assessment.

---

#### `judge.py`
**Purpose**: LLM-based quality judgment

**What It Does**:
1. Prompt LLM: "Is this extraction faithful to the transcript?"
2. LLM returns: score + reasoning
3. Fall back to lexical if LLM fails

**Significance**: Semantic understanding. Catches nuanced errors.

---

#### `dataset_exporter.py`
**Purpose**: Export low-scoring samples for improvement

**What It Does**:
1. Find extractions with score < threshold
2. Save: transcript + extraction + correct answer
3. Create benchmark dataset

**Significance**: Enables continuous improvement. Data for fine-tuning.

---

### `worker/schemas/` [DATA MODELS]

#### `transcript.py`
**Purpose**: Pydantic models for extraction output

**Key Models**:
```python
class ActionItem(BaseModel):
    task: str
    assignee: str
    deadline: date
    priority: Literal["high", "medium", "low"]

class KeyDecision(BaseModel):
    decision: str
    rationale: str
    impact: str

class MeetingAnalysisResponse(BaseModel):
    action_items: list[ActionItem]
    decisions: list[KeyDecision]
    sentiment: float  # 0-1
    summary: str
```

**Significance**: Structure is enforced. LLM output is validated against schema.

---

#### `agent.py`
**Purpose**: Pydantic models for agent processing

**Models**: Augment transcript.py with agent-specific fields

**Significance**: Type safety throughout the pipeline.

---

## Tests Directory

### Test Structure
```
tests/
├── test_agents.py              # Agent node validation
├── test_security.py            # Auth, RBAC, rate limits
├── test_eval_pipeline.py       # Evaluation logic
├── test_router.py              # LLM failover
├── test_pipeline.py            # Workflow orchestration
├── test_retriever.py           # RAG retrieval
├── test_structured_output.py   # Pydantic validation
├── test_semantic_cache.py      # Cache behavior
├── test_circuit_breaker.py     # Fault tolerance
├── test_indexer.py             # Indexing logic
├── test_pricing_usage.py       # Cost estimation
├── test_chunker.py             # Text splitting
├── test_reranker.py            # Relevance ranking
└── __init__.py
```

**Coverage**: ~2000 total lines of test code
- Unit tests (isolated components)
- Integration tests (full workflows)
- Security tests (auth, isolation)

**Significance**: Not afterthought. Tests are comprehensive and well-organized.

---

## Frontend Files

### `templates/index.html`
**Purpose**: Web UI homepage

**Features**: Form to upload audio, display results, trigger jobs

**Note**: Minimal frontend (MVP focus). Real product would expand this.

---

### `static/style.css`
**Purpose**: Styling

**Note**: Basic styling, not a design showcase.

---

## Configuration Files

### Not Present (But Might Exist)
- `docker-compose.yml` - Not in repo (but described in README)
- `Dockerfile` - Not in repo
- `.github/workflows/` - No CI/CD automation shown
- `alembic/` - No database migrations

**Significance**: These would be added for production deployment.

---

## Key Insights from Repository Layout

### 1. Layered Architecture
Clear separation:
- **API Layer** (`api/`) - HTTP handling
- **Service Layer** (`services/`) - Business logic
- **Model Layer** (`models/`) - Data persistence
- **Workflow Layer** (`workflows/`) - Orchestration

### 2. Concerns Isolated by Directory
- LLM logic together (`services/llm/`)
- RAG logic together (`rag/`)
- Agent logic together (`agents/`)
- Evaluation together (`eval/`)

**Principle**: [Observable] Everything that changes together lives together.

### 3. Infrastructure Centralized
- Database (`core/database.py`)
- Caching (`services/cache/`)
- Security (`core/security.py`)
- Observability (`core/telemetry.py`)

**Principle**: [Observable] Cross-cutting concerns are shared, not duplicated.

### 4. Tests Mirror Structure
Test files match source structure:
- `test_agents.py` tests `agents/`
- `test_router.py` tests `services/llm/router.py`

**Principle**: [Observable] Easy to find what's being tested.

### 5. No Main Business Logic in Routes
Routes are thin:
```python
@router.post("/jobs")
async def create_job(job_id):
    # Minimal logic here
    celery_app.send_task("process_transcript", [job_id])
    return {"job_id": job_id}
```

**Principle**: [Observed] Logic lives in services and workflows, not routes.

---

**Next Step**: Read [System Mental Model](03-system-mental-model.md) to understand data and control flow.
