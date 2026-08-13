# Executive Summary

## One-Sentence Description

A production-grade Python/FastAPI application that transcribes meetings, extracts structured action items and decisions using multi-provider LLMs with automatic failover, and evaluates quality — all with multi-tenant isolation, async processing, and comprehensive observability.

---

## The Problem It Solves

**User Problem**: Meetings generate endless information (action items, decisions, ownership) that gets lost in notes, chat, or email.

**Technical Problem**: Building a system that reliably:
1. Transcribes diverse audio/video formats
2. Extracts structured data from unstructured speech
3. Maintains quality and consistency
4. Scales to multiple teams/organizations
5. Tolerates failures in external APIs
6. Tracks costs and usage
7. Provides visibility into what went wrong

---

## What It Does

### User-Facing Flow
1. Upload a meeting recording (audio or video)
2. System transcribes it
3. System extracts action items, decisions, sentiment
4. User sees structured results
5. User can review, export, or act on results

### Behind the Scenes
1. Async job queuing (202 Accepted response)
2. Multi-provider LLM routing with automatic fallback
3. Structured output validation
4. Quality evaluation (Is the extraction faithful to the recording?)
5. Persistent storage with full audit trail
6. Per-tenant isolation (multi-tenancy)

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI Web App                                                 │
├─────────────────────────────────────────────────────────────────┤
│ • HTTP endpoints (async routes)                                 │
│ • JWT authentication                                            │
│ • Request validation (Pydantic)                                │
│ • Rate limiting middleware                                      │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ├──► Redis (Cache, Semantic Cache, Rate Limit)
                   │
                   ├──► Celery Job Queue
                   │    └──────────────────────────┐
                   │                               │
                   └──► SQLite/PostgreSQL          │ Job Processing
                        (persistent state)        │
                                                  ▼
                        ┌──────────────────────────────────────┐
                        │ Celery Worker                       │
                        ├──────────────────────────────────────┤
                        │ Transcription (Groq Whisper)        │
                        │ LLM Extraction (multi-provider)     │
                        │ Evaluation (metrics + LLM judge)    │
                        │ Result persistence                  │
                        └──────────────────────────────────────┘
```

---

## Key Characteristics

### Reliability
- **[Observable]** Circuit breaker pattern: Groq → OpenAI → Anthropic → Gemini
- **[Observable]** Retry logic with exponential backoff
- **[Observable]** Idempotent job processing
- **[Inferred]** Designed for high-stakes production (meetings are important)

### Scalability
- **[Observable]** Async request handling (FastAPI + Uvicorn)
- **[Observable]** Background job processing (Celery workers)
- **[Observable]** Multi-tenant isolation (queries filtered by tenant_id)
- **[Observable]** Redis caching (semantic similarity cache)

### Security
- **[Observable]** JWT authentication for every protected endpoint
- **[Observable]** Role-based access control (RBAC): admin, member, viewer
- **[Observable]** Tenant scoping (complete data isolation)
- **[Observable]** Password hashing (bcrypt)
- **[Observable]** Rate limiting per tenant

### Quality Assurance
- **[Observable]** Structured output validation (Pydantic schemas)
- **[Observable]** LLM-based quality evaluation (judge pattern)
- **[Observable]** Deterministic metrics (faithfulness, recall)
- **[Observable]** Low-scoring sample export for benchmarking

---

## Core Capabilities

| Capability | Implementation | Notes |
|------------|-----------------|-------|
| **Transcription** | Groq Whisper API | Speech-to-text; primary provider |
| **Extraction** | Multi-provider LLM + Pydantic | Structured output; auto-failover |
| **Quality Check** | LLM-as-Judge + lexical metrics | Verify extraction faithfulness |
| **Multi-tenancy** | Tenant-scoped DB queries + JWT | Complete isolation |
| **Async Processing** | Celery + Redis | Non-blocking user experience |
| **Caching** | Redis semantic cache | Reduce LLM API costs |
| **Observability** | OpenTelemetry + Prometheus | Track requests, errors, latency |
| **Authentication** | JWT + bcrypt | Industry standard |
| **Rate Limiting** | Token bucket (Redis) | Prevent abuse |

---

## Technology Stack

```
Application Layer:   FastAPI (async web framework)
Job Scheduling:      Celery (task broker)
Message Broker:      Redis (job queue, cache)
Database:            SQLAlchemy ORM (SQLite/PostgreSQL)
Data Validation:     Pydantic (structured output)
LLM Integration:     Groq, OpenAI, Anthropic, Google APIs
Vector Search:       sentence-transformers + Redis
Authentication:      PyJWT + passlib
Observability:       OpenTelemetry + Prometheus
Testing:             pytest (13 comprehensive test modules)
```

---

## Development Maturity

This is **NOT** a prototype or proof-of-concept.

Evidence:
- ✅ Multi-tenant architecture (production requirement)
- ✅ Comprehensive security (auth, RBAC, rate limiting)
- ✅ Fault tolerance (circuit breaker, failover, retries)
- ✅ Quality evaluation (metrics + LLM judge)
- ✅ Observability (tracing, metrics, logging)
- ✅ 13 test modules (not ad-hoc tests)
- ✅ Clean working tree (not WIP)

This is a **production-ready MVP** that could be deployed and scaled.

---

## Core Design Principles

### 1. Separation of Concerns
- Web layer (FastAPI) separate from job processing (Celery)
- LLM integration abstracted (easy to add providers)
- Evaluation logic isolated (can be extended independently)

### 2. Async-First Architecture
- Non-blocking web layer (users get immediate response)
- Background processing (Celery workers handle heavy lifting)
- Result polling (client retrieves results when ready)

### 3. Fail-Safe Defaults
- Circuit breaker prevents cascading failures
- Fallback providers prevent single points of failure
- Retries with backoff for transient errors

### 4. Multi-Tenancy Built-In
- Not bolted on afterward
- Every query filtered by tenant_id
- Separate JWT tokens per user
- Per-tenant rate limits

### 5. Quality Over Speed
- Structured output validation (errors caught early)
- Evaluation pipeline (assess extraction quality)
- Dataset export (enable continuous improvement)

---

## Important Decisions & Tradeoffs

| Decision | Rationale | Tradeoff |
|----------|-----------|----------|
| Async architecture | Scalability, responsiveness | Complexity of distributed system |
| Multi-provider LLM | Fault tolerance, cost optimization | Must manage multiple APIs |
| Structured output | Determinism, validation | Less flexible than free-form text |
| Quality evaluation | Detect problems early | Additional compute cost |
| Multi-tenancy | Market requirement | Query complexity, more tests |
| Redis everywhere | Performance, simplicity | Operational dependency |

---

## What You Should Know

### Before Reading the Code
- Basic FastAPI knowledge (async Python web framework)
- Understanding of async/await in Python
- REST API concepts
- Basic database concepts (ORM)
- Familiarity with task queues (Celery) helpful but not required

### After Reading This Documentation
- How the system accepts, processes, and returns meeting data
- Why reliability and quality are built into the architecture
- How multi-tenant isolation prevents data leaks
- What happens when an API fails
- How to extend or modify each component
- What could go wrong and how to fix it

---

## Quick Comparison

If you've worked with similar systems:

| System Type | This Repository | Typical Example |
|-------------|-----------------|-----------------|
| **Web Framework** | FastAPI (async) | Django (sync) |
| **Job Queue** | Celery (distributed) | APScheduler (local) |
| **Cache** | Redis (distributed) | Python dict (in-memory) |
| **Auth** | JWT (stateless) | Sessions (stateful) |
| **Scalability** | Horizontal (add workers) | Vertical (bigger server) |

---

## What Makes This Interesting

From a software engineering perspective, this repository demonstrates:

1. **Production-grade architecture** - Not a tutorial project
2. **Real tradeoffs** - Every decision has a reason
3. **Practical patterns** - Patterns you'll see in real systems
4. **Quality focus** - Evaluation built into the pipeline
5. **Multi-tenancy** - Complex but common in SaaS
6. **Fault tolerance** - Handles cascading failures
7. **Comprehensive testing** - 13 test modules, not 3
8. **Observable systems** - Tracing and metrics built in

This is a system worth learning from because it makes no shortcuts and handles the hard parts correctly.

---

**Next Step**: Read [System Mental Model](03-system-mental-model.md) to understand how all pieces fit together.
