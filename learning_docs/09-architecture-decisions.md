# Architecture Decisions

Why each major choice was made. Tradeoffs and alternatives considered.

---

## Decision 1: Async Architecture (FastAPI + Uvicorn)

### What
Use async/await Python (FastAPI) instead of synchronous frameworks (Django, Flask).

### Evidence
- Every route is `async def`
- Uses `await` for I/O operations
- Event loop handles concurrency

### Likely Rationale
[Inferred]
1. **Scalability**: Handle 1000s of concurrent connections per server
2. **I/O efficiency**: Don't block thread while waiting for database/Redis
3. **Python ecosystem**: asyncio is standard, many libraries support async
4. **Cost efficiency**: Need fewer servers to handle same load

### Alternatives
1. **Django (sync)** - Traditional, simpler, less scalable
2. **Tornado** - Older async framework
3. **Gevent** - Lighter async alternative
4. **Node.js** - Async-first language (JavaScript)

### Advantages
- ✅ High concurrency per server
- ✅ Responsive (non-blocking)
- ✅ Cost-effective
- ✅ Modern Python standard

### Disadvantages
- ❌ Complexity: Requires async-aware code throughout
- ❌ Learning curve: Async/await concepts
- ❌ Debugging: Harder to trace async execution
- ❌ Compatibility: Not all libraries support async

### Tradeoff
**Complexity vs. Scalability**. Extra complexity buys significant scaling benefits.

### When to Reconsider
- If traffic is low (synchronous would suffice)
- If you have blocking operations that can't be async (CPU-intensive)
- If team prefers simplicity over scale

---

## Decision 2: Celery + Redis for Async Jobs

### What
Use Celery (task queue) + Redis (message broker) for long-running operations instead of processing in FastAPI.

### Evidence
- `worker/workflows/transcript_workflow.py` - Celery task
- `worker/core/celery_app.py` - Celery configuration
- Job endpoints return 202 Accepted (async pattern)

### Likely Rationale
[Inferred]
1. **Non-blocking web**: Don't wait 30+ seconds for transcription
2. **Retries**: Celery handles retry logic automatically
3. **Scalability**: Add more workers when backlog grows
4. **Separation of concerns**: Web servers separate from workers

### Alternatives
1. **APScheduler** - Simpler, but limited to single machine
2. **Celery without queue** - Just use threading
3. **Temporal/Cadence** - More complex, better for workflows
4. **Serverless (Lambda)** - Managed, pay-per-invocation

### Advantages
- ✅ Scalable (add workers)
- ✅ Reliable (retries, persistence)
- ✅ Decoupled (web ≠ worker)
- ✅ Observable (can monitor queue)

### Disadvantages
- ❌ Operational complexity: Redis + workers to manage
- ❌ Distributed system problems: timing, ordering
- ❌ Debugging: Harder to trace async tasks
- ❌ Cost: Infrastructure for job queue

### Tradeoff
**Operational Complexity vs. Scalability**. Extra infrastructure buys ability to process large workload.

### When to Reconsider
- If all jobs are < 1 second (just process in FastAPI)
- If you don't need retries
- If you prefer simpler deployment (no worker servers)

---

## Decision 3: Multi-Provider LLM Router with Failover

### What
Support Groq (primary) → OpenAI → Anthropic → Gemini with automatic fallback.

### Evidence
- `worker/services/llm/router.py` - Failover logic
- `worker/services/llm/providers/` - 4 provider adapters
- Circuit breaker enabled for each

### Likely Rationale
[Inferred]
1. **Cost optimization**: Groq cheapest, pay for expensive providers only when needed
2. **Reliability**: Any single provider down doesn't break service
3. **Flexibility**: Can choose provider by cost/quality/speed
4. **Market testing**: See which providers customers prefer

### Alternatives
1. **Single provider (Groq only)** - Cheapest, simplest, fragile
2. **Single provider (OpenAI)** - Most reliable, most expensive
3. **Manual routing** - Let client choose provider
4. **Load balancing** - Round-robin between providers
5. **Hybrid approach** - Use multiple simultaneously, pick best result

### Advantages
- ✅ Cost-efficient (cheapest first)
- ✅ Resilient (any provider down is OK)
- ✅ Transparent to user (automatic failover)
- ✅ Flexibility (can add/remove providers)

### Disadvantages
- ❌ Complexity: 4 different APIs to manage
- ❌ Quality variance: Different providers, different results
- ❌ Testing burden: Test all providers, all combinations
- ❌ Operational overhead: Monitor all APIs

### Tradeoff
**Complexity vs. Reliability**. Extra complexity buys significant reliability and cost benefits.

### When to Reconsider
- If one provider is sufficient (OpenAI)
- If complexity is not worth reliability gain
- If you need consistent results (different providers differ)

---

## Decision 4: Multi-Tenancy (Tenant-Scoped Data)

### What
Complete data isolation: every query filters by `tenant_id`.

### Evidence
- Every model has `tenant_id` column
- Every query filters by tenant: `Job.tenant_id == user.tenant_id`
- Rate limits are per-tenant
- JWT includes tenant_id

### Likely Rationale
[Inferred]
1. **Market**: SaaS product (multiple organizations)
2. **Cost**: Single database cheaper than per-tenant database
3. **Operations**: Easier to manage than separate instances
4. **Data isolation**: Security requirement

### Alternatives
1. **No multi-tenancy** - Single organization per instance
2. **Row-level security (RLS)** - Database enforces tenant scoping
3. **Database per tenant** - Complete isolation, expensive
4. **Hybrid**: Shared write DB, separate read replicas per tenant

### Advantages
- ✅ Scalable (one database for all)
- ✅ Operationally simple
- ✅ Cost-efficient
- ✅ Shared data (semantic cache benefits all tenants)

### Disadvantages
- ❌ Complexity: Must remember tenant filter on every query
- ❌ Security risk: Forgetting tenant filter = data leak
- ❌ Query complexity: Every WHERE clause needs tenant condition
- ❌ Debugging: Harder to test (multiple contexts)

### Tradeoff
**Complexity vs. Cost**. Extra complexity saves operational cost.

### When to Reconsider
- If you only serve one organization
- If tenants need complete isolation (regulatory)
- If you have many tenants with different schemas

---

## Decision 5: Structured Output Validation (Pydantic)

### What
Validate LLM output against Pydantic schemas. Fail extraction if LLM returns invalid JSON.

### Evidence
- `worker/schemas/transcript.py` - Pydantic models
- `MeetingAnalysisResponse` validates extraction
- Validation happens in workflow before saving

### Likely Rationale
[Inferred]
1. **Determinism**: Same extraction run produces same result
2. **Quality**: Catch LLM hallucinations early
3. **Reliability**: Type-safe data in rest of system
4. **Observability**: Know exact schema of results

### Alternatives
1. **No validation** - Accept any LLM output
2. **Lenient validation** - Accept partial results
3. **LLM-enforced JSON** - Use JSON mode/strict schema from LLM API
4. **Post-processing**: Clean up LLM output afterwards

### Advantages
- ✅ Type-safe (Python knows structure)
- ✅ Catches errors early (before persisting)
- ✅ Generates API docs automatically (FastAPI)
- ✅ Deterministic (no variance)

### Disadvantages
- ❌ Strict: Rejected if even one field wrong
- ❌ Fragility: If LLM format changes, breaks
- ❌ Requires coordination: Schema must match LLM prompt
- ❌ Overhead: Validation happens on every run

### Tradeoff
**Flexibility vs. Reliability**. Strict validation catches errors early, but requires perfect LLM output.

### When to Reconsider
- If you need flexible schemas
- If LLM output varies significantly
- If you want to accept partial results

---

## Decision 6: SQLite for Dev, PostgreSQL for Prod

### What
Database URL configurable. Use SQLite locally, PostgreSQL in production.

### Evidence
- `DATABASE_URL` environment variable
- Default: `sqlite:///./jobs.db`
- Production: `postgresql://...`

### Likely Rationale
[Inferred]
1. **Developer experience**: SQLite needs no setup
2. **Production-ready**: PostgreSQL scales to millions
3. **Compatibility**: SQLAlchemy ORM works with both
4. **Cost**: PostgreSQL pay-per-use in cloud

### Alternatives
1. **SQLite everywhere** - Simple, but doesn't scale
2. **PostgreSQL everywhere** - Scales, but complex local setup
3. **In-memory database** - Fast tests, but no persistence
4. **Docker Compose** - Pre-built PostgreSQL for local dev

### Advantages
- ✅ Zero-config local dev (SQLite)
- ✅ Scales in production (PostgreSQL)
- ✅ Reduces friction (no Docker required)
- ✅ Same ORM code

### Disadvantages
- ❌ Feature mismatch: SQLite lacks some PostgreSQL features
- ❌ Testing: Subtle differences between SQLite/PostgreSQL
- ❌ Configuration: More environment variables
- ❌ Silent failures: May work in dev, fail in prod

### Tradeoff
**Configuration Complexity vs. Developer Experience**. Extra config buys frictionless development.

### When to Reconsider
- If features differ too much between SQLite/PostgreSQL
- If you want to run PostgreSQL locally
- If you don't need SQLite benefits

---

## Decision 7: JWT for Stateless Authentication

### What
Use JWT tokens instead of server-side sessions.

### Evidence
- `worker/core/security.py:create_access_token()`
- Token signed with SECRET_KEY
- No session storage required

### Likely Rationale
[Inferred]
1. **Scalability**: No session server needed (stateless)
2. **Distributed**: Works across multiple web servers
3. **Standard**: JWT is industry standard
4. **Mobile-friendly**: Clients pass token in header

### Alternatives
1. **Server sessions** - Store in database/Redis (stateful)
2. **OAuth 2.0** - Delegate to external provider
3. **API keys** - Long-lived, different purpose
4. **mTLS** - Certificate-based (complex)

### Advantages
- ✅ Stateless (no session server)
- ✅ Scalable (works across load balancer)
- ✅ Standard (industry norm)
- ✅ Explicit (token included in every request)

### Disadvantages
- ❌ Token theft: If leaked, attacker has access until expiry
- ❌ No revocation: Can't instantly invalidate token
- ❌ Size: Larger than session cookie (included in every request)
- ❌ Complexity: Must handle token expiry

### Tradeoff
**Security vs. Scalability**. JWT sacrifices instant revocation for scalability.

### When to Reconsider
- If you need to instantly revoke access (include blacklist)
- If you want server control (use sessions)
- If you have low scale (sessions are fine)

---

## Decision 8: Redis Everywhere (Cache, Queue, Rate Limit)

### What
Use Redis as: message queue (Celery), cache (semantic cache), rate limit store.

### Evidence
- `REDIS_URL` environment variable
- Celery broker
- Semantic cache implementation
- Rate limit counter storage

### Likely Rationale
[Inferred]
1. **Performance**: Redis is fast (in-memory)
2. **Operational simplicity**: One tool for three jobs
3. **Durability**: Can configure persistence (RDB, AOF)
4. **Features**: Built-in data structures (sorted sets, hashes)

### Alternatives
1. **Separate tools**: RabbitMQ (queue) + Memcached (cache) + database (rate limit)
2. **Database for all**: PostgreSQL for everything (slower)
3. **In-memory queue**: Threading queue (single machine only)
4. **Cloud services**: AWS SQS (queue), ElastiCache (cache)

### Advantages
- ✅ Simple: One tool, one setup
- ✅ Fast: In-memory performance
- ✅ Flexible: Works for queue, cache, counters
- ✅ Observable: Can inspect state

### Disadvantages
- ❌ Single point of failure: Redis down = no queue/cache/rate limit
- ❌ Memory-bound: Can't exceed RAM
- ❌ Persistence overhead: AOF/RDB slower than in-memory
- ❌ Operational burden: Must manage Redis separately

### Tradeoff
**Reliability vs. Simplicity**. Single Redis simplifies ops, but adds risk.

### When to Reconsider
- If Redis reliability is critical (use cluster/sentinel)
- If you have massive data (exceeds RAM)
- If you want separate tools (fault isolation)

---

## Decision 9: Semantic Caching (Vector Similarity)

### What
Cache LLM results using embedding similarity, not just exact hash.

### Evidence
- `worker/services/cache/semantic_cache.py`
- Embeddings stored with results
- Similarity threshold check (95%)

### Likely Rationale
[Inferred]
1. **Cost savings**: Same meeting transcribed twice = use cache
2. **Performance**: Avoid expensive LLM call
3. **User experience**: Results return faster
4. **Intelligence**: Similarity catches paraphrases

### Alternatives
1. **No caching** - Call LLM every time (expensive)
2. **Exact hash caching** - Only identical transcripts use cache
3. **Time-based caching** - Cache everything, expire after time
4. **User-managed caching** - Let client handle

### Advantages
- ✅ Cost reduction (avoid LLM calls)
- ✅ Speed (sub-millisecond vs. 5-10 seconds)
- ✅ Semantic (catches similar transcripts)
- ✅ Observability (cache hit/miss metrics)

### Disadvantages
- ❌ Complexity: Must compute embeddings
- ❌ Overhead: Extra latency to check cache
- ❌ Memory: Store all embeddings
- ❌ Stale results: Cached results may be outdated

### Tradeoff
**Complexity vs. Cost**. Extra complexity saves on LLM API costs.

### When to Reconsider
- If LLM cost is not significant
- If results must be fresh (no caching)
- If you have memory constraints

---

## Decision 10: Quality Evaluation Pipeline

### What
Score every extraction with metrics + LLM judge. Export low-scoring samples.

### Evidence
- `worker/eval/pipeline.py` - Orchestrator
- `worker/eval/metrics.py` - Deterministic scoring
- `worker/eval/judge.py` - LLM judge
- `worker/eval/dataset_exporter.py` - Export low scores

### Likely Rationale
[Inferred]
1. **Quality assurance**: Detect failures automatically
2. **Continuous improvement**: Build benchmark dataset
3. **No human review**: Scalable QA
4. **Root cause analysis**: Know which extractions fail

### Alternatives
1. **No evaluation** - Trust LLM output (risky)
2. **Random sampling** - Review 1% of results (misses patterns)
3. **Human review** - Manual review (expensive, slow)
4. **A/B testing** - Compare model versions (requires new model)

### Advantages
- ✅ Automatic QA (no human needed)
- ✅ Scalable (runs with every job)
- ✅ Data-driven (benchmark dataset for improvement)
- ✅ Transparent (know extraction quality)

### Disadvantages
- ❌ Compute cost: Running eval pipeline
- ❌ Overhead: Slows down job completion
- ❌ Metrics limited: Can't detect all errors
- ❌ LLM judge cost: Extra LLM call

### Tradeoff
**Cost vs. Quality**. Evaluation adds cost but detects problems early.

### When to Reconsider
- If evaluation cost exceeds benefit
- If you trust LLM output implicitly
- If you have human reviewers

---

## Summary: Key Decision Patterns

| Decision | Style | Rationale |
|----------|-------|-----------|
| Async (FastAPI) | Performance | Handle high concurrency |
| Celery + Redis | Scalability | Don't block web layer |
| Multi-provider LLM | Reliability | Any provider failure OK |
| Multi-tenancy | Business | SaaS requirement |
| Pydantic validation | Reliability | Type-safe results |
| SQLite + PostgreSQL | UX | Zero-config dev + production scale |
| JWT | Scalability | Stateless auth |
| Redis everywhere | Simplicity | One tool for many jobs |
| Semantic caching | Cost | Reduce LLM API spend |
| Quality eval | Quality | Detect failures automatically |

**Pattern**: [Observable] Every decision trades **Complexity for Benefits**.

---

**Next Step**: Read [Alternatives & Tradeoffs](10-alternatives-tradeoffs.md) to explore what could have been different.
