# Architectural Decisions - Deep Analysis

Senior architect's examination of why every significant design choice was made, what alternatives existed, and when the current approach would break.

---

# Decision 1: Async Architecture (FastAPI + Celery + Redis)

## WHY THIS?

### What the Repository Does
- Web requests return immediately (202 Accepted)
- Long-running work happens in background (Celery workers)
- Result available for polling via separate GET endpoint

### Where Implemented
- `app.py` - FastAPI application
- `worker/workflows/transcript_workflow.py` - Celery task orchestration
- `worker/core/celery_app.py` - Celery configuration
- `worker/middleware/rate_limit.py` - Works with async

### Problem It Solves
1. **Non-blocking web tier** - 10,000 concurrent uploads without blocking
2. **Decoupled processing** - Web and workers scale independently
3. **Resilience** - Worker crashes don't fail user requests
4. **Cost efficiency** - Can have many cheap worker instances

### Engineering Principle
**Separation of Concerns**: Request handling ≠ Processing

**Evidence in Repository**:
```python
# worker/api/v1/endpoints/jobs.py
@app.post("/transcripts/process")
async def create_job(file: UploadFile):
    # Enqueue, return immediately
    celery_app.send_task("process_transcript", args=[job_id])
    return {"job_id": job_id, "status": "PENDING"}  # 202 Accepted

# worker/workflows/transcript_workflow.py
@celery_app.task
def process_transcript(job_id):
    # Runs in separate process, takes 30-60 seconds
    # Web request already returned to user
```

---

## WHY NOT THAT?

### Alternative 1: Synchronous Processing (Django/Flask Traditional)

```python
@app.post("/transcripts/process")
def process_sync(file: UploadFile):
    transcript = groq.transcribe(file)  # Blocks 30 seconds
    extraction = llm.extract(transcript)  # Blocks 5-10 seconds
    return {"transcript": transcript, "results": extraction}  # Only after 40+ seconds
```

**How It Works**:
- Web server blocks while processing
- Thread/process occupied for entire duration
- Result returned immediately

**Advantages**:
- Simpler code (no queue, no workers)
- Immediate result (no polling)
- Easier to test (single flow)
- No infrastructure (no Redis, no workers)

**Disadvantages**:
- Blocking web server reduces concurrency
  - 100 concurrent users = 100 threads × 40s each = 4000 thread-seconds of latency
  - Server can handle ~10-20 concurrent uploads before timing out
- Connection timeout risk (clients give up after 30s)
- Web server crash = lost processing work
- Can't scale horizontally (workers can't share work)
- Database connection pool exhausted (threads hold DB connections)

**Complexity**: Lower
- No queue infrastructure
- No background workers
- No state management

**Performance**:
- Per-request latency: 40+ seconds (blocking)
- Throughput: 3-5 uploads/sec (single 8-core server)
- Scaling: Vertical only

**Scalability**:
- Hits ceiling at ~50 concurrent users
- Adding servers doesn't help (can't distribute blocking work)

**Maintainability**: Higher (simpler)

**Testability**: Easier (single flow)

**Operational**:
- No Redis, no Celery to manage
- Simpler deployment

---

### Alternative 2: WebSocket Streaming (Real-Time Updates)

```python
@app.websocket("/transcripts/process")
async def process_websocket(websocket: WebSocket):
    file = await websocket.receive_bytes()
    transcript = await groq.transcribe(file)
    await websocket.send_json({"type": "transcript", "data": transcript})
    
    extraction = await llm.extract(transcript)
    await websocket.send_json({"type": "extraction", "data": extraction})
```

**How It Works**:
- Persistent connection to client
- Updates streamed as available
- Real-time progress notifications

**Advantages**:
- Better UX (progress feedback, not polling)
- Fewer HTTP requests (push vs pull)
- Real-time status updates

**Disadvantages**:
- Complex connection management
- Harder to deploy (WebSocket proxying)
- More memory (persistent connections)
- Harder to scale (connection affinity)
- Harder to debug (stateful connections)
- Browser handling complexity (reconnect logic)

**Complexity**: Much higher

**Scalability**: Worse (stateful connections, can't load balance easily)

**Operational**: Complex (need sticky sessions or Redis for connection state)

---

### Alternative 3: Immediate Result with Background Improvement

```python
# Fast extraction, quality improvement in background
@app.post("/transcripts/process")
async def process_fast(file):
    # Quick extraction (local model or cached)
    quick_result = fast_extractor(file)
    
    # Enqueue for higher-quality extraction
    celery_app.send_task("improve_extraction", args=[job_id, quick_result])
    
    return {"results": quick_result, "improved_results_available": False}
```

**Advantages**:
- Immediate response with preliminary results
- Better UX (something to show right away)
- Can improve in background

**Disadvantages**:
- Two extraction paths (complexity)
- Quick extractor may be less accurate
- Complexity of merging results
- Still requires polling for final results

---

## TRADEOFF

**Current Design Gains**:
- Horizontal scalability (workers are stateless)
- High concurrency (handles 1000s of concurrent uploads)
- Resilience (worker crashes don't lose requests)
- Cost efficiency (cheap worker instances)
- Decoupled concerns (web ≠ processing)

**Current Design Sacrifices**:
- Infrastructure complexity (Redis, Celery, workers)
- Operational burden (manage queue depth, worker health)
- User experience (must poll for results, no real-time progress)
- Immediate results (40+ seconds to first result)
- Debugging complexity (distributed flow)

**Net Tradeoff**: Better scalability/reliability at cost of operational complexity and user experience

---

## FAILURE POINT

**When This Design Breaks**:

1. **Redis Failure**
   - Job queue becomes inaccessible
   - New uploads accepted but not processed
   - System degrades (accepts but doesn't process)

2. **All Workers Down**
   - Queue fills up with unprocessed jobs
   - Jobs eventually timeout
   - Result: User sees timeout, not failure

3. **Database Connection Pool Exhausted**
   - Workers can't acquire connections
   - Processing fails
   - Backlog builds

4. **Queue Backlog Overwhelms System**
   - 10,000 jobs queued
   - Workers process 100/min
   - 100 minutes until cleared
   - Memory exhausted if Redis can't handle queue size

5. **Client Polling Timeout**
   - User waits 45 seconds
   - Polling fails (network, browser)
   - Result stuck in database, user doesn't see it

---

## CHANGE CONDITION

**When to Replace This Design**:

1. **Real-Time Requirements**
   - Business requirement: results within 5 seconds
   - Current 30-40 second latency unacceptable
   - Consider: Streaming extraction, WebSocket, lambda

2. **Simplified Operations**
   - Team doesn't want to operate Redis/Celery
   - Consider: Moving to serverless (AWS Lambda, Google Functions)
   - Trade: Less control, less cost-effective

3. **Streaming Results Required**
   - Users need to see progress (transcription 50% done...)
   - Current polling too coarse-grained
   - Consider: WebSocket or Server-Sent Events

4. **Single-Machine Deployment**
   - Infrastructure doesn't support distributed system
   - Consider: Reverting to synchronous (and scaling vertically)

---

## SCALE CONDITION

**When Async Becomes Inappropriate**:

### Scale: 100 uploads/day (small startup)
- ✅ Async is overkill, but works fine
- Could use synchronous (but async doesn't hurt)

### Scale: 10,000 uploads/day (growth phase)
- ✅ Async necessary
- Single server can't handle
- Async allows horizontal scaling

### Scale: 100,000 uploads/day (enterprise)
- ✅ Async still works
- But new problems emerge:
  - Queue depth management (millions of jobs)
  - Worker resource allocation
  - Database connection pool exhaustion
  - Redis memory usage
  - Monitoring complexity

### Scale: 1,000,000 uploads/day (hyperscale)
- ⚠️ Async hits limits
- Issues:
  - Redis becomes bottleneck (single instance)
  - Celery management complex (thousands of workers)
  - Queue backlog (if extraction slower than ingestion)
  - Cost of workers dominates

**Scaling Point**: ~100,000 uploads/day
- Beyond this, need specialized solutions
- Consider: Message queues (Kafka, Pub/Sub)
- Consider: Serverless (no queue management)

---

## LEARNING QUESTION

**Question**: Your system is receiving 1000 uploads/min. Transcription takes 30 seconds per job. You have 20 workers, each can process 1 extraction per 10 seconds. Queue depth is growing 100 jobs/min. Uploads are succeeding (202 responses), but users polling for results get 404 (jobs not processed yet). 

Design a fix that:
1. Prevents queue overflow
2. Reduces queue depth
3. Gives users visibility

What trade-offs does each solution introduce?

**Answer Depends On**:
- Understanding queue bottleneck (transcription not extraction is bottleneck)
- Recognizing throughput mismatch (1000/min uploads, only 20*6=120 transcriptions/min possible)
- Solutions: backpressure (reject uploads), faster transcription (more providers), streaming (show progress)

---

# Decision 2: Multi-Provider LLM with Automatic Failover

## WHY THIS?

### What the Repository Does
- Tries Groq first (fast, cheap)
- Automatically falls back to OpenAI (slower, expensive)
- Further fallback to Anthropic, then Gemini
- Transparent to caller (automatic failover)
- Circuit breaker prevents repeated calls to failed provider

### Where Implemented
- `worker/services/llm/router.py` - Routing logic
- `worker/services/llm/circuit_breaker.py` - State management
- `worker/services/llm/providers/` - Provider implementations (groq.py, openai.py, anthropic.py, gemini.py)
- `worker/services/llm/pricing.py` - Cost tracking

### Problem It Solves
1. **Cost optimization**: Cheapest provider first
2. **Availability**: Any single provider failing doesn't break service
3. **Quality options**: Better providers available if needed
4. **Intelligence**: Choose provider based on context (not shown, but possible)

### Engineering Principle
**Resilience Through Redundancy**

**Evidence in Repository**:
```python
# worker/services/llm/router.py
async def query(self, prompt: str):
    for provider in [Groq, OpenAI, Anthropic, Gemini]:
        if provider.circuit.is_open():
            continue  # Skip failed providers
        
        try:
            return await provider.query(prompt)
        except Exception:
            provider.circuit.mark_failure()
            continue  # Try next provider
    
    raise AllProvidersFailedError()
```

---

## WHY NOT THAT?

### Alternative 1: Single Primary Provider (Groq Only)

```python
# Simple: Just use Groq
async def query(self, prompt):
    return await groq.chat.completions.create(model="mixtral", messages=[...])
```

**Advantages**:
- Simplicity (single provider, single API)
- Consistency (same model always)
- Cost predictability (fixed pricing)
- Easier to test (one provider to mock)

**Disadvantages**:
- If Groq down, entire system fails
- No fallback option
- Locked into Groq's model quality/speed
- Vulnerable to Groq API changes

**Complexity**: Minimal

**Scalability**: Fine (single provider, straightforward)

**Maintainability**: Easier (one API to maintain)

**Cost**: Lowest for typical usage

**Reliability**: Single point of failure

---

### Alternative 2: Load Balancing (Round-Robin)

```python
# Distribute requests evenly
PROVIDERS = [Groq, OpenAI, Anthropic, Gemini]
LAST_INDEX = 0

async def query(self, prompt):
    global LAST_INDEX
    LAST_INDEX = (LAST_INDEX + 1) % len(PROVIDERS)
    provider = PROVIDERS[LAST_INDEX]
    return await provider.query(prompt)
```

**Advantages**:
- Balanced load across providers
- No single provider overwhelmed
- Fault tolerance (any provider down, others handle)

**Disadvantages**:
- 75% of requests go to expensive providers (OpenAI, etc.)
- Cost is 3-4x higher than cost-first approach
- Wastes money
- Doesn't optimize for cost

**Cost**: 3-4x higher than current approach

---

### Alternative 3: Parallel Queries (Racing)

```python
# Call all providers in parallel, use fastest
results = await asyncio.gather(
    groq.query(prompt),
    openai.query(prompt),
    anthropic.query(prompt),
    gemini.query(prompt),
    return_exceptions=True
)
return first_non_exception(results)
```

**Advantages**:
- Fault tolerance (any provider works)
- Speed (use fastest response)
- Quality (can compare and pick best)

**Disadvantages**:
- 4x API costs (pay for all 4 calls)
- Massive waste if parallel queries redundant
- Complex result merging
- Billing complications

**Cost**: 4x current cost

**Reliability**: Excellent

**Complexity**: High

---

### Alternative 4: Per-Tenant Provider Selection

```python
# Let each tenant choose preferred provider
tenant_config = db.query(TenantConfig).filter(tenant_id=user.tenant_id)
provider = get_provider(tenant_config.preferred_provider)
return await provider.query(prompt)
```

**Advantages**:
- Customization (Tenant A wants OpenAI, Tenant B wants Groq)
- Tenant control over quality/cost tradeoff

**Disadvantages**:
- Loses automatic failover (if tenant's choice fails, they get error)
- Complexity (manage per-tenant settings)
- Some tenants overload expensive provider, waste money

---

## TRADEOFF

**Current Design Gains**:
- Cost optimization (cheapest provider first)
- Automatic failover (any provider can serve)
- Transparent (caller doesn't know/care which provider)
- Resilience (single provider down ≠ system down)

**Current Design Sacrifices**:
- Consistency (different providers may return different results)
- Latency variance (Groq fast, OpenAI slower, affects user experience)
- Debugging complexity (must trace which provider was used)
- Result variance (Groq "Ship this" vs Claude "Deploy this")

**Net Tradeoff**: Better reliability/cost at cost of consistency and debugging

---

## FAILURE POINT

**When This Breaks**:

1. **All Providers Down**
   - AllProvidersFailedError raised
   - Job marked FAILED
   - User gets error

2. **Groq Circuit Breaker Stuck OPEN**
   - Too aggressive error threshold
   - Groq transient error (1 second timeout) triggers
   - Circuit opens, blacklists Groq for 60 seconds
   - All requests go to expensive providers

3. **Result Inconsistency Causes Bugs**
   - Groq extracts action items slightly differently
   - Downstream logic breaks
   - Quality inconsistency

4. **Cost Spike from Fallbacks**
   - Groq experiences outage (unlikely but possible)
   - All traffic falls back to OpenAI
   - Bill increases 100x

---

## CHANGE CONDITION

**When to Replace This Design**:

1. **Consistency Requirement**
   - Business rule: Extraction must be identical every time
   - Consider: Force single provider (sacrifice cost/availability)

2. **Provider Preference Becomes Important**
   - Different tenants need different models
   - Consider: Per-tenant provider selection + fallback

3. **Cost Becomes Irrelevant**
   - Enterprise deployment (cost not a factor)
   - All requests use expensive provider (quality > cost)
   - Consider: Single high-quality provider

4. **Streaming Becomes Required**
   - Groq doesn't support streaming
   - Must use OpenAI (supports streaming)
   - Consider: Multiple providers per capability

---

## SCALE CONDITION

**When Multi-Provider Stops Working**:

### Scale: 100 requests/day
- ✅ Works fine, over-engineered

### Scale: 10,000 requests/day
- ✅ Optimal (costs matter, reliability matters)

### Scale: 100,000 requests/day
- ⚠️ Issues emerge:
  - Groq rate limits (has limits per account)
  - Need to distribute across multiple Groq accounts
  - OpenAI rate limits
  - Need better rate limit management

### Scale: 1,000,000 requests/day
- ❌ Breaks:
  - No single provider handles this volume
  - Must self-host LLM (vLLM, llama.cpp)
  - Or use multiple specialized providers
  - Cost optimization becomes critical (can't use expensive fallbacks)

**Scaling Point**: ~500,000 requests/day
- Single provider can't handle
- Need load balancing at provider level
- Need self-hosted or custom provider

---

## LEARNING QUESTION

**Question**: Your Groq account hits rate limit during peak traffic. The circuit breaker correctly identifies this and opens, routing to OpenAI. But OpenAI also has rate limits (per-second). 

Design how you'd:
1. Detect rate limiting vs other errors
2. Distinguish between temporary and permanent failures
3. Adjust circuit breaker strategy based on error type
4. What information would you track for each provider?

**Answer Tests Understanding Of**:
- Difference between rate limiting (temporary, recoverable) and errors (may be permanent)
- Circuit breaker tuning (different strategies for different error types)
- Observability (tracking what each provider is experiencing)

---

# Decision 3: Query-Level Multi-Tenancy (Not Row-Level Security)

## WHY THIS?

### What the Repository Does
- Every query includes `WHERE tenant_id = user.tenant_id`
- Enforced at application layer (SQLAlchemy ORM)
- Works with both SQLite and PostgreSQL
- Explicit in code (visible and auditable)

### Where Implemented
- `worker/core/security.py` - Extract tenant_id from JWT
- Every endpoint uses `Depends(get_current_user)`
- `worker/models/job.py` - Every query filters by tenant_id
- Database schema: Every table has tenant_id column

### Problem It Solves
1. **Multi-SaaS**: Multiple organizations in single database
2. **Cost efficiency**: Single database, single deployment
3. **Database agnostic**: Works with SQLite (no RLS) and PostgreSQL
4. **Explicit isolation**: Visible in code, easier to audit

### Engineering Principle
**Explicit Over Implicit** (Python Zen of Python)

**Evidence in Repository**:
```python
# worker/core/security.py
async def get_current_user(token: str):
    payload = jwt.decode(token, SECRET_KEY)
    user.tenant_id = payload["tenant_id"]
    return user

# Every route receives user with tenant_id
@app.get("/jobs")
async def list_jobs(user: User = Depends(get_current_user)):
    # user.tenant_id available here
    jobs = db.query(Job).filter(Job.tenant_id == user.tenant_id).all()
    # ↑ Explicit filter, visible in code
```

---

## WHY NOT THAT?

### Alternative 1: Row-Level Security (PostgreSQL RLS)

```sql
-- PostgreSQL RLS Policy
CREATE POLICY tenant_isolation ON jobs
  USING (tenant_id = current_user_tenant_id)
  WITH CHECK (tenant_id = current_user_tenant_id);
```

**How It Works**:
- Database enforces filtering automatically
- No application-level filter needed
- Even raw SQL queries filtered

**Advantages**:
- Database-enforced (can't be bypassed by app bug)
- Defense in depth (two layers of protection)
- Works even with raw SQL
- Simpler application code (no manual filtering)

**Disadvantages**:
- PostgreSQL-only (doesn't work with SQLite)
- Operational complexity (RLS must be enabled)
- Performance overhead (RLS checking adds latency)
- Debugging complexity (filters happen at database)
- Testing complexity (must test RLS policies separately)

**Complexity**: Higher (must understand RLS syntax)

**Performance**: Slight overhead from RLS evaluation

**Portability**: None (PostgreSQL only)

**Security**: Better (database-enforced)

**Maintainability**: More complex (must maintain SQL policies)

---

### Alternative 2: Per-Tenant Database

```
Tenant A: postgresql://host:5432/tenant_a
Tenant B: postgresql://host:5432/tenant_b
Tenant C: postgresql://host:5432/tenant_c
```

**How It Works**:
- Each tenant gets own database instance
- Complete isolation at database level
- No shared data possible

**Advantages**:
- Perfect isolation (database-level)
- Can customize schema per tenant
- Can set different backups/retention per tenant
- Failure isolation (Tenant A's DB crash doesn't affect B)

**Disadvantages**:
- Operational nightmare (N databases to manage)
- Very expensive (database per tenant)
- Scaling issues (can't analyze across tenants)
- Backup/recovery complex
- Migration complexity (adding new schema to all DBs)
- Cost: Database costs multiply by tenant count

**Complexity**: Very high

**Cost**: 10-100x higher (database per tenant)

**Scaling**: Poor (N databases hard to manage)

**Operability**: Nightmare (backup/restore all DBs)

---

### Alternative 3: In-Memory Filtering

```python
# Load ALL jobs, filter in Python
all_jobs = db.query(Job).all()  # Loads ENTIRE table
user_jobs = [j for j in all_jobs if j.tenant_id == user.tenant_id]
```

**Advantages**:
- No change to database queries
- Works with any database

**Disadvantages**:
- Loads entire table into memory (scales poorly)
- Filter happens after database, wastes network
- Performance disaster at scale
- Security risk (data in memory)

**Performance**: Terrible (O(n) memory, O(n) latency)

---

## TRADEOFF

**Current Design Gains**:
- Database portability (SQLite + PostgreSQL)
- Explicit security (visible in code)
- Auditability (can see where filtering happens)
- Simplicity (ORM handles filtering)
- Flexibility (can add application-level logic)

**Current Design Sacrifices**:
- Defense-in-depth (only application-level protection)
- Vulnerability to forgetful developers (forgetting filter = data leak)
- No SQL query-level protection (raw SQL bypasses filter)
- Code duplication (every query adds filter)

**Net Tradeoff**: Portability/simplicity at cost of security depth

---

## FAILURE POINT

**When This Breaks**:

1. **Forgetful Developer**
   ```python
   # WRONG: Missing tenant filter
   jobs = db.query(Job).all()  # Returns ALL jobs!
   ```
   - Returns all jobs (all tenants)
   - No database error (valid query)
   - Data leak occurs silently

2. **Raw SQL Query**
   ```python
   # WRONG: Raw SQL bypasses ORM filtering
   jobs = db.execute("SELECT * FROM jobs WHERE status='COMPLETED'")
   # No tenant filtering, all tenants' jobs returned
   ```

3. **Subquery Forgot Filter**
   ```python
   # WRONG: Subquery missing tenant filter
   subquery = db.query(Job).all()  # Missing filter
   filtered = [j for j in subquery if j.priority == 'high']
   ```

4. **API Cache Returning Cross-Tenant Data**
   ```python
   # WRONG: Cache key doesn't include tenant_id
   cache.get("jobs_completed")  # Returns any tenant's completed jobs
   ```

---

## CHANGE CONDITION

**When to Replace This Design**:

1. **Security Requirement**
   - Compliance mandate: Defense-in-depth required
   - Consider: Adding RLS on top of application filtering

2. **Multiple Database Platforms**
   - Must support database without RLS (SQLite, MySQL, etc.)
   - Current approach is necessary

3. **Raw SQL Queries Unavoidable**
   - Complex reporting requires raw SQL
   - Consider: RLS to protect even raw queries

4. **Audit Requirements**
   - Must prove isolation is enforced
   - Consider: Adding RLS as additional proof layer

---

## SCALE CONDITION

**When Query-Level Filtering Becomes Problematic**:

### Scale: 1 million jobs
- ✅ Works fine
- Index on (tenant_id, status) handles filtering

### Scale: 100 million jobs
- ✅ Still works
- Indexes must be carefully maintained

### Scale: 1 billion jobs
- ⚠️ Issues:
  - Index size matters
  - Query planning complexity
  - Need better partitioning strategy

**Scaling Point**: ~100 million records
- Must partition by tenant_id
- Each tenant gets own partition

---

## LEARNING QUESTION

**Question**: A developer writes this code:

```python
@app.get("/analytics/total-actions")
async def get_total_actions(user: User = Depends(get_current_user)):
    result = db.execute("SELECT COUNT(*) FROM action_items")
    return result[0]
```

This query doesn't have a tenant filter. The developer says "it's just a count, no sensitive data leaks."

1. Is the developer right or wrong?
2. What's the vulnerability?
3. How would you fix it?
4. Why does this matter architecturally?

**Answer Tests Understanding Of**:
- Information leakage (count itself is information)
- Implicit vs explicit security
- Why application-level filtering is insufficient
- RLS would prevent this bug

---

# Decision 4: Structured Output Validation (Pydantic Schemas)

## WHY THIS?

### What the Repository Does
- LLM output validated against Pydantic schema before storing
- Invalid output rejected (not stored)
- Errors caught early (before user sees them)
- Type-safe results (Python typing throughout)

### Where Implemented
- `worker/schemas/transcript.py` - Pydantic models
- `worker/workflows/transcript_workflow.py` - Validation happens before storage
- LLM prompt designed to match schema

### Problem It Solves
1. **Type safety**: Results are guaranteed to match schema
2. **Error detection**: Invalid output caught early
3. **Consistency**: All results same shape (easier downstream processing)
4. **Documentation**: Schema documents expected output format
5. **Composability**: Can confidently pass validated objects to other functions

### Engineering Principle
**Fail-Fast Validation** + **Type Safety**

**Evidence in Repository**:
```python
# worker/schemas/transcript.py
class ActionItem(BaseModel):
    task: str
    assignee: str
    deadline: Optional[date]
    priority: Literal["high", "medium", "low"]

class MeetingAnalysisResponse(BaseModel):
    action_items: List[ActionItem]
    decisions: List[KeyDecision]
    sentiment: float

# worker/workflows/transcript_workflow.py
response_dict = json.loads(llm_response)
extraction = MeetingAnalysisResponse(**response_dict)  # Validates schema
# If invalid: Pydantic raises ValidationError
# If valid: extraction is type-safe
```

---

## WHY NOT THAT?

### Alternative 1: No Validation (Accept Any LLM Output)

```python
# No validation, trust LLM output
response_dict = json.loads(llm_response)
return response_dict  # Could be any structure
```

**Advantages**:
- Simpler code (no validation)
- More flexible (accept any LLM output)
- Faster (no schema checking)
- LLM never rejected (no retries)

**Disadvantages**:
- Errors discovered by users (bad UX)
- Inconsistent data structure
- Impossible to add type hints
- Downstream code must handle any shape
- Silent errors (missing fields don't cause exceptions)

**Example Failure**:
```python
# LLM output missing deadline field
{"task": "Ship feature", "assignee": "Bob"}  # No deadline!

# Code assumes it exists
date_str = result["deadline"]  # KeyError!
```

---

### Alternative 2: Lenient Validation (Partial Acceptance)

```python
# Accept partially valid results
try:
    extraction = MeetingAnalysisResponse(**response_dict)
except ValidationError as e:
    # Use what we have, skip invalid fields
    extraction = {
        "action_items": response_dict.get("action_items", []),
        "decisions": response_dict.get("decisions", []),
        "sentiment": response_dict.get("sentiment", 0.5)  # Default
    }
```

**Advantages**:
- Partial results better than nothing
- Doesn't reject LLM output
- Some value extracted

**Disadvantages**:
- Inconsistent data (sometimes fields missing)
- Silent failures (developer doesn't know field was wrong)
- Downstream code must handle partial data
- Harder to debug (unclear why field missing)
- Quality metric (confidence) incorrectly high (data is incomplete)

---

### Alternative 3: Post-Processing Cleanup

```python
# Accept any LLM output, clean it up
def clean_extraction(raw_output):
    # Try to extract action_items even if wrong format
    action_items = []
    for item in raw_output.get("action_items", []):
        try:
            action_items.append(ActionItem(**item))
        except:
            pass  # Skip invalid items
    return {
        "action_items": action_items,
        "decisions": raw_output.get("decisions", []),
        ...
    }
```

**Advantages**:
- More forgiving (extracts what's possible)

**Disadvantages**:
- Complex cleanup logic
- Same issues as lenient validation
- Multiple places handle invalid data
- Harder to maintain
- Errors scattered throughout code

---

### Alternative 4: Manual Validation

```python
# Validate manually without Pydantic
def validate_extraction(output):
    if not isinstance(output.get("action_items"), list):
        raise ValueError("action_items must be list")
    
    for item in output["action_items"]:
        if not isinstance(item.get("task"), str):
            raise ValueError("task must be string")
        if not isinstance(item.get("assignee"), str):
            raise ValueError("assignee must be string")
        # ... check every field
    
    # ... repeat for decisions, sentiment, etc.
```

**Advantages**:
- Custom error messages possible
- Full control

**Disadvantages**:
- Verbose (200+ lines for complex schema)
- Easy to miss fields
- Duplicates Pydantic functionality
- Not type-safe (returns dict, not typed object)

---

## TRADEOFF

**Current Design Gains**:
- Type safety (Python type hints work)
- Early error detection (before storage)
- Consistent data structure (all results same shape)
- Clear error messages (Pydantic details what's wrong)
- Documentation (schema documents format)
- Composability (can pass to other type-safe functions)

**Current Design Sacrifices**:
- Flexibility (LLM output must match schema exactly)
- Adoption latency (LLM might output wrong format, needs retry)
- Debugging (must understand Pydantic errors)
- Strictness (any deviation causes rejection)

**Net Tradeoff**: Type safety/consistency at cost of flexibility

---

## FAILURE POINT

**When This Breaks**:

1. **LLM Outputs Wrong Format**
   ```
   Expected: {"task": "...", "assignee": "..."}
   Got: {"todo": "...", "owner": "..."}  # Wrong field names
   ```
   - ValidationError raised
   - Job marked FAILED
   - User gets error

2. **Schema Too Strict**
   ```python
   deadline: date  # If deadline is null, validation fails
   # Should be: deadline: Optional[date]
   ```

3. **LLM Interprets Schema Differently**
   - Prompt says: priority: Literal["high", "medium", "low"]
   - LLM outputs: priority: "CRITICAL" (not in allowed values)
   - Validation fails

4. **Backwards Incompatibility**
   - Schema changed (new required field)
   - Old LLM output now invalid
   - Batch jobs all fail

---

## CHANGE CONDITION

**When to Replace This Design**:

1. **Flexible Output Required**
   - Business rule: Accept any extraction, refine later
   - Consider: Lenient validation + human review

2. **LLM Compatibility**
   - LLM consistently outputs wrong format
   - Consider: Custom parser that maps wrong format to correct

3. **Schema Evolution Frequent**
   - Constantly adding/removing fields
   - Validation becomes maintenance burden
   - Consider: Flexible structure (but lose type safety)

4. **Performance Critical**
   - Validation adds latency
   - Consider: Async validation (validate after storing)

---

## SCALE CONDITION

**When Structured Validation Causes Issues**:

### Scale: 100 extractions/day
- ✅ Works fine, no issues

### Scale: 10,000 extractions/day
- ✅ Works fine
- Validation is cheap (microseconds)

### Scale: 1,000,000 extractions/day
- ✅ Still works (validation very fast)
- But: Failure rate might increase
- If 0.1% fail validation = 1000 jobs/day marked FAILED
- Requires process to investigate failures

**No Real Scale Limit**: Validation cost is negligible

---

## LEARNING QUESTION

**Question**: Your LLM occasionally outputs action items with slightly wrong format:

```
# Expected
{"action_items": [{"task": "...", "assignee": "..."}]}

# Sometimes LLM outputs
{"action_items": [{"description": "...", "responsible": "..."}]}
```

Pydantic rejects the second format. You lose 5% of extractions.

Design options:
1. Loosen the schema (make assignee/task optional, accept any fields)
2. Add custom parser that maps common aliases to correct fields
3. Fine-tune LLM to output correct format
4. Accept partial results, fill gaps with defaults

Explain trade-offs and which would you choose?

**Answer Tests Understanding Of**:
- Schema as contract vs schema as guideline
- Cost of validation vs cost of flexibility
- LLM output quality (can it be improved?)
- Operational trade-offs

---

# Decision 5: Semantic Caching (Vector Similarity)

## WHY THIS?

### What the Repository Does
- Cache transcripts using SHA256 hash (exact match)
- Additionally cache using embedding similarity (semantic match)
- Avoid expensive LLM calls for similar transcripts
- Reduce costs by 10-50% (depending on hit rate)

### Where Implemented
- `worker/services/cache/semantic_cache.py`
- Embeddings computed via `sentence-transformers`
- Stored in Redis with TTL
- Similarity threshold: ~0.95 (95% similar = cache hit)

### Problem It Solves
1. **Cost reduction**: LLM calls are expensive ($0.05-$5)
2. **Speed improvement**: Cache hit < 1ms vs 10s for LLM call
3. **Duplicate prevention**: Same meeting uploaded twice = one LLM call

### Engineering Principle
**Memoization at Semantic Level**

**Evidence in Repository**:
```python
# worker/services/cache/semantic_cache.py
def get_or_compute(self, text: str, compute_fn):
    # Exact match
    exact_hash = hash(text)
    if exact_hash in self.redis:
        return self.redis[exact_hash]
    
    # Semantic match
    embedding = self.embedding_model.encode(text)
    similar = self.redis_search(embedding, threshold=0.95)
    if similar:
        return similar
    
    # Cache miss: compute
    result = compute_fn(text)
    self.redis[exact_hash] = result
    return result
```

---

## WHY NOT THAT?

### Alternative 1: No Caching

```python
# Simple: Always call LLM
extraction = await llm_router.query(prompt)
```

**Advantages**:
- Simplicity (no cache infrastructure)
- No stale cache issues
- Always fresh results

**Disadvantages**:
- Higher costs (every request = LLM call)
- Slower (no cache hits)
- More API calls (might hit rate limits)
- Worse user experience (always 10 second latency)

**Cost**: 10-50% higher than cached approach

---

### Alternative 2: Exact Hash Only (No Semantic)

```python
# Cache by exact transcript hash
hash = sha256(transcript)
if hash in cache:
    return cache[hash]
```

**Advantages**:
- Simpler (no embeddings)
- Faster (no embedding computation)
- Fewer dependencies

**Disadvantages**:
- Only catches exact duplicates
- Similar transcripts miss cache
- Lower hit rate (5-10% vs 20-50%)
- Less value from caching

**Hit Rate**: 5-10% vs 20-50% with semantic

---

### Alternative 3: Time-Based Cache

```python
# Cache with TTL (e.g., 1 hour)
# Same transcript within 1 hour = cache hit
# Different transcript = always miss
```

**Advantages**:
- Simpler (no semantic matching)
- Automatic cleanup (TTL expires)

**Disadvantages**:
- Similar transcripts (different wording) miss cache
- Temporal dependency (results differ by time)
- Might return stale results
- Lower hit rate

---

### Alternative 4: Transcript Deduplication

```python
# Group similar transcripts
# Process once, share result
# Trade: Delay (wait for grouping)
```

**Advantages**:
- Higher cache hit for groups
- Batches work

**Disadvantages**:
- Complex (grouping logic)
- Latency (wait for batch)
- Doesn't help single requests

---

## TRADEOFF

**Current Design Gains**:
- Cost reduction (10-50% depending on duplicate rate)
- Speed improvement (cache hits are fast)
- Semantic understanding (catches paraphrases)
- No stale cache (embeddings capture meaning)

**Current Design Sacrifices**:
- Complexity (embeddings, Redis, similarity logic)
- Memory usage (store embeddings)
- Computational cost (embedding model)
- False positives (semantic similarity might match wrong transcripts)

**Net Tradeoff**: Cost savings at cost of complexity

---

## FAILURE POINT

**When This Breaks**:

1. **Cache Poisoning**
   ```
   Incorrect result cached with high confidence
   Similar transcripts get wrong result
   ```

2. **Embedding Model Biased**
   ```
   Embeddings don't capture meaningful differences
   Semantically different transcripts match
   Wrong result returned
   ```

3. **Threshold Too High**
   ```
   Threshold 0.95 = miss many similar transcripts
   Threshold 0.80 = false positives
   No sweet spot
   ```

4. **Cross-Tenant Cache Leak**
   ```
   Tenant A's transcript cached
   Similar transcript from Tenant B hits cache
   Gets Tenant A's results (data leak!)
   ```
   - Current code: Likely safe (assuming tenant filtering)
   - But: Risk if cache key doesn't include tenant_id

5. **Stale Cache**
   ```
   Extraction model updated
   Cached old results from old model
   Results inconsistent (new vs old)
   ```

---

## CHANGE CONDITION

**When to Replace This Design**:

1. **Cache Poisoning Risk Unacceptable**
   - Compliance: Can't use cached results (audit trail required)
   - Consider: Disable caching, accept higher cost

2. **Consistency Becomes Critical**
   - Every extraction must be identical (no cache variance)
   - Consider: Remove caching

3. **Embedding Model Too Biased**
   - Embeddings don't work for domain (meeting transcripts)
   - Consider: Different embedding model or no semantic cache

4. **Cost Not an Issue**
   - LLM cost < 1% of business
   - Simplicity preferred
   - Consider: Remove caching

---

## SCALE CONDITION

**When Semantic Caching Becomes Problematic**:

### Scale: 100 extractions/day
- ✅ Works, but overkill

### Scale: 10,000 extractions/day
- ✅ Optimal (costs matter, hit rate matters)

### Scale: 100,000 extractions/day
- ✅ Works
- But: Cache size matters
- If 50,000 unique transcripts: 50,000 embeddings × 384 dims × 4 bytes ≈ 75 MB (Redis memory)

### Scale: 1,000,000 extractions/day
- ⚠️ Issues:
  - Embedding vector size matters (384 dims vs 768 dims)
  - Redis memory cost increases
  - Similarity search gets slower (more vectors)
  - Embedding model latency (if not GPU-accelerated)

### Scale: 10,000,000 extractions/day
- ❌ Breaks:
  - Redis can't hold 10M embeddings
  - Embedding search becomes expensive
  - Need external vector database (Pinecone, Qdrant, Weaviate)

**Scaling Point**: ~1 million unique transcripts
- Beyond this, need dedicated vector database

---

## LEARNING QUESTION

**Question**: You notice your cache hit rate is only 3% even though 20% of transcripts are duplicates. The semantic similarity threshold is 0.95.

Debug: What could cause this?

Options:
1. Embedding model not trained on meeting transcripts
2. Different transcript preprocessing (one stripped, one not)
3. Cache TTL too short (expires before duplicate arrives)
4. Similarity threshold too strict (should be 0.90)
5. Embeddings corrupted (stored wrong format)

For each option, how would you verify?

**Answer Tests Understanding Of**:
- Debugging caching issues
- Understanding embeddings
- Threshold tuning trade-offs
- Observability (monitoring cache hit rate)

---

# Decision 6: Evaluation Pipeline (Dual Assessment)

## WHY THIS?

### What the Repository Does
- Every extraction scored by:
  1. Deterministic metrics (faithfulness, recall) - FAST
  2. LLM-as-Judge (semantic validation) - SLOWER
- Scores combined for final quality score
- Low scores (< 0.7) exported to benchmark dataset

### Where Implemented
- `worker/eval/pipeline.py` - Orchestrator
- `worker/eval/metrics.py` - Deterministic scoring
- `worker/eval/judge.py` - LLM-based scoring
- `worker/eval/dataset_exporter.py` - Export low-scoring samples

### Problem It Solves
1. **Quality visibility**: Know which extractions are bad
2. **Problem detection**: Catch hallucinations early
3. **Continuous improvement**: Low-scoring samples enable model improvement
4. **No manual review**: Automatic quality assessment at scale

### Engineering Principle
**Layered Assessment** + **Continuous Feedback Loop**

**Evidence in Repository**:
```python
# worker/eval/pipeline.py
def evaluate(extraction, transcript):
    # Fast metrics
    metric_score = metrics.evaluate(extraction, transcript)
    
    # Semantic judge
    judge_score = judge.evaluate(extraction, transcript)
    
    # Combine
    final_score = (metric_score + judge_score) / 2
    
    # Export if low
    if final_score < 0.7:
        dataset_exporter.export(extraction, transcript)
    
    return final_score
```

---

## WHY NOT THAT?

### Alternative 1: No Evaluation

```python
# Accept extraction as-is
return extraction
```

**Advantages**:
- Simplicity (no evaluation)
- No extra latency (no scoring)
- No extra LLM call (saves cost)

**Disadvantages**:
- No quality visibility
- Bad extractions not detected
- No feedback loop (can't improve)
- User gets bad results (bad UX)

**Result**: Silent failures, quality degradation

---

### Alternative 2: Deterministic Metrics Only

```python
# Just use fast metrics
score = metrics.evaluate(extraction, transcript)
```

**Advantages**:
- Fast (no extra LLM call)
- No cost (no judge API call)
- Good enough for most cases

**Disadvantages**:
- Limited accuracy (lexical matching only)
- Misses semantic errors
- LLM can hallucinate things not in transcript (metrics won't catch)

**Example Failure**:
```
Transcript: "We decided on React"
Extraction: "We decided on Node.js"  # Wrong!
Metrics: 67% match (decided, on, we = 3/4 words match)
Judge would catch: 0% match (completely wrong decision)
```

---

### Alternative 3: LLM Judge Only

```python
# Just use judge
score = judge.evaluate(extraction, transcript)
```

**Advantages**:
- Accurate (semantic understanding)

**Disadvantages**:
- Slow (another LLM call, 5-10 seconds)
- Expensive (judge API cost)
- Cascading failures (judge fails, can't score)
- 2x LLM cost per extraction

---

### Alternative 4: Sampling (Random Sample for Review)

```python
# Review only 1% of extractions
if random.random() < 0.01:
    judge_score = judge.evaluate(...)
else:
    score = metrics.evaluate(...)  # Trust metrics
```

**Advantages**:
- Reduces judge cost (only 1% of extractions judged)
- Catches some problems

**Disadvantages**:
- Misses errors in 99% of extractions
- Inconsistent scoring (some have judge, some don't)
- Can't reliably detect quality problems

---

## TRADEOFF

**Current Design Gains**:
- Quality visibility (score for every extraction)
- Problem detection (catch hallucinations)
- Feedback loop (benchmark dataset enables improvement)
- Layered assessment (metrics + semantic)
- Graceful degradation (if judge fails, use metrics)

**Current Design Sacrifices**:
- Extra latency (evaluation takes 7-15 seconds)
- Extra cost (LLM judge call)
- Complexity (two scoring systems)
- False positives (metrics might score low incorrectly)

**Net Tradeoff**: Quality visibility at cost of latency and cost

---

## FAILURE POINT

**When This Breaks**:

1. **Judge Model Biased**
   ```
   Judge always scores low (or high)
   Scores meaningless
   ```

2. **Metrics and Judge Disagree**
   ```
   Metrics: 0.9 (90% of words match)
   Judge: 0.1 (semantically wrong)
   Which is correct?
   ```

3. **Threshold Miscalibrated**
   ```
   Threshold 0.7: Too many exported (90% of extractions)
   Threshold 0.9: Too few (only clear failures)
   ```

4. **LLM Judge Fails Cascades**
   ```
   Judge API down
   Can't score any extraction
   All jobs fail
   ```
   - Current: Falls back to metrics ✓
   - Fallback must be robust

5. **Benchmark Dataset Quality**
   ```
   Low-scoring samples are mostly OK (judge was wrong)
   Fine-tuning on bad data makes model worse
   ```

---

## CHANGE CONDITION

**When to Replace This Design**:

1. **Speed Becomes Critical**
   - Latency requirement: < 45 seconds end-to-end
   - Current: ~60 seconds (transcription + extraction + evaluation)
   - Consider: Remove evaluation step

2. **Cost Becomes Prohibitive**
   - Judge cost > 10% of total
   - Consider: Sampling instead of evaluating all

3. **Benchmark Dataset Unused**
   - No model improvement happening
   - Consider: Remove export, simplify pipeline

4. **Judge Model Unavailable**
   - Judge provider discontinues service
   - Consider: Switch to metrics-only

---

## SCALE CONDITION

**When Evaluation Pipeline Becomes Problematic**:

### Scale: 100 extractions/day
- ✅ Works fine

### Scale: 10,000 extractions/day
- ✅ Works
- Evaluation cost: 10,000 × $0.01 (judge) = $100/day

### Scale: 100,000 extractions/day
- ✅ Works
- Evaluation cost: 100,000 × $0.01 = $1000/day
- But: Judge latency might compound
- If judge takes 10 seconds, 100,000 extractions need 100,000 * 10s = 1.2M seconds = 14 days processing
- Need parallel judges (throughput)

### Scale: 1,000,000 extractions/day
- ⚠️ Issues:
  - Judge cost: $10,000/day (expensive)
  - Judge throughput: Need many parallel judge calls
  - Benchmark dataset: 10,000+ low-scoring samples/day
  - Dataset becomes too large, slow to fine-tune on

### Scale: 10,000,000 extractions/day
- ❌ Breaks:
  - Judge cost: $100,000+/day (prohibitive)
  - Benchmark dataset: 100,000+ low-scoring samples/day (too large)
  - Consider: Sampling instead of all

**Scaling Point**: ~1,000,000 extractions/day
- Beyond this, need to sample for judge (not evaluate all)

---

## LEARNING QUESTION

**Question**: Your benchmark dataset has 50,000 low-scoring samples (score < 0.7). You fine-tune your extraction model on this data.

After deployment, you notice:
- Extraction quality DECREASED
- Model now scores even lower

Debug: What could cause this?

Possibilities:
1. Dataset contains incorrect labels (judge was wrong, marked good as bad)
2. Dataset is biased (only hard cases, not representative)
3. Dataset is too small (50K insufficient for fine-tuning)
4. Over-fitting (model memorized bad patterns)
5. Judge score is different from human quality (optimization metric wrong)

How would you verify each? What does this teach about feedback loops?

**Answer Tests Understanding Of**:
- Feedback loops and bias
- Dataset quality vs quantity
- Importance of labels
- Continuous improvement requires validation

---

# Decision 7: Monolithic Architecture (Not Microservices)

## WHY THIS?

### What the Repository Does
- Single FastAPI application
- Single database
- Single codebase
- Deployed as one unit
- All features in one process

### Where Implemented
- `app.py` - Single FastAPI app
- `worker/` - All services in single package
- `docker-compose.yml` (if exists) - Single container for app

### Problem It Solves
1. **Simplicity**: Single deployment, simpler DevOps
2. **Consistency**: Shared code, consistent behavior
3. **Development speed**: Easier to make changes across features
4. **Testing**: Simpler integration tests (single process)
5. **Cost**: Lower infrastructure cost

### Engineering Principle
**Simplicity Until Complexity Demands Otherwise**

---

## WHY NOT THAT?

### Alternative 1: Microservices (One Service Per Feature)

```
Microservices:
├─ Transcription Service (receives audio)
├─ Extraction Service (receives transcript)
├─ Evaluation Service (receives extraction)
├─ Cache Service (manages semantic cache)
├─ Job Manager Service (tracks status)
└─ Gateway (routes requests)
```

**Advantages**:
- Independent scaling (extract service scales separately)
- Technology freedom (each service picks own tech)
- Team independence (teams own services)
- Fault isolation (one service down, others work)
- Independent deployment (update extraction without touching transcription)

**Disadvantages**:
- Operational complexity (5+ services to deploy, monitor, scale)
- Debugging difficulty (distributed tracing needed)
- Network latency (service-to-service calls)
- Data consistency (distributed transactions)
- Versioning complexity (API versions between services)
- DevOps overhead (more to manage)

**Complexity**: Very high

**Operational Cost**: 5-10x higher

**Infrastructure**: More servers, more monitoring

**Deployment**: Harder (coordinated releases)

---

### Alternative 2: Service-Oriented (3 Large Services)

```
SOA:
├─ Processing Service (transcription + extraction)
├─ Quality Service (evaluation)
└─ Core Service (auth, jobs, cache)
```

**Advantages**:
- Better isolation than monolith
- Still relatively simple

**Disadvantages**:
- API versioning between services
- Deployment coordination
- Operational overhead
- Development complexity (services must agree on contracts)

---

### Alternative 3: Serverless (AWS Lambda, Google Functions)

```
Serverless:
├─ transcribe() Lambda function
├─ extract() Lambda function
├─ evaluate() Lambda function
└─ orchestration via Step Functions
```

**Advantages**:
- No infrastructure management
- Scale automatically
- Pay-per-execution (no idle cost)

**Disadvantages**:
- Cold start latency (first invocation slow)
- Vendor lock-in (AWS-specific)
- Debugging complexity
- Cost unpredictable (could spike)
- Limited customization

---

## TRADEOFF

**Current Design (Monolith) Gains**:
- Simplicity (single deployment)
- Debuggability (single process to trace)
- Consistency (shared code)
- Development speed (one repo, one codebase)
- Cost (minimal infrastructure)
- Testability (integration tests simple)

**Current Design Sacrifices**:
- Scalability (can't scale features independently)
- Fault isolation (one feature down = whole system might degrade)
- Team autonomy (shared codebase, shared deployment)
- Technology flexibility (stuck with FastAPI, Python)

**Net Tradeoff**: Simplicity/cost at cost of scalability/independence

---

## FAILURE POINT

**When Monolith Breaks**:

1. **Scalability Limit**
   ```
   Transcription is bottleneck (slow)
   Can't scale transcription without scaling entire app
   Waste resources scaling extraction (already fast)
   ```

2. **Resource Contention**
   ```
   Extraction uses 100% CPU
   Transcription waits for CPU
   Overall throughput limited
   ```

3. **Deployment Coordination**
   ```
   Bug in extraction
   Must redeploy entire app (risk to transcription)
   Could have deployed just extraction service
   ```

4. **Development Conflict**
   ```
   Team A (transcription) wants Python 3.10
   Team B (extraction) wants Python 3.11
   Can't have both in single deployment
   ```

---

## CHANGE CONDITION

**When to Split into Microservices**:

1. **Independent Scaling Needed**
   - Transcription is 10x slower than extraction
   - Scaling whole app is wasteful
   - Consider: Microservices for transcription

2. **Different Technology Stacks**
   - Extraction needs GPU (Python + CUDA)
   - Transcription needs audio processing (specialized library)
   - Consider: Microservices per stack

3. **Team Autonomy Critical**
   - Teams need independent deployment
   - Coordination overhead too high
   - Consider: Microservices per team

4. **Fault Isolation Required**
   - Bug in extraction crashes whole system
   - Unacceptable downtime
   - Consider: Microservices for isolation

---

## SCALE CONDITION

**When Monolith Stops Working**:

### Scale: 100 uploads/day
- ✅ Monolith perfect (over-engineered, but works)

### Scale: 10,000 uploads/day
- ✅ Monolith works
- Single server insufficient
- Add workers (Celery), but still monolith

### Scale: 100,000 uploads/day
- ✅ Monolith works
- But: Resource contention emerges
- Transcription and extraction compete for CPU
- Scaling everything together is wasteful

### Scale: 1,000,000 uploads/day
- ⚠️ Monolith shows cracks:
  - Transcription bottleneck (20 seconds per upload)
  - Extraction waits
  - Can't scale extraction without scaling transcription
  - Vertical scaling maxed out

### Scale: 10,000,000 uploads/day
- ❌ Monolith breaks:
  - Need independent scaling for each step
  - Transcription (needs more workers) vs Extraction (already fast)
  - Can't manage single monolith at this scale
  - Operational burden too high

**Scaling Point**: ~500,000 uploads/day
- Monolith starts to show pressure
- Consideration of microservices begins

---

## LEARNING QUESTION

**Question**: You're architecting a system that will handle 1M uploads/day.

Monolith vs Microservices:
1. Which would you choose?
2. If monolith: What would force a split?
3. If microservices: What would you be optimizing for?
4. At what upload rate would you reconsider?

Explain your reasoning, including operational costs and team structure.

**Answer Tests Understanding Of**:
- Architecture trade-offs
- Understanding what fails at scale
- Cost of complexity
- Operational considerations

---

# Decision 8: Polling for Results (Not WebSocket/Server-Sent Events)

## WHY THIS?

### What the Repository Does
- User polls `/api/v1/jobs/{job_id}` for status
- GET request returns current status
- If COMPLETED, includes results
- If PENDING, returns status and ETA
- Client polls repeatedly (interval configurable)

### Where Implemented
- `worker/api/v1/endpoints/jobs.py:get_job()` - Status endpoint
- Client polls (in UI, details unknown)

### Problem It Solves
1. **Simplicity**: Stateless HTTP (no connection management)
2. **Scalability**: No persistent connections
3. **Compatibility**: Works with any client (browser, mobile, API)
4. **Testability**: Simple to test (just HTTP endpoints)
5. **Horizontal Scaling**: No server affinity needed (any server handles any request)

### Engineering Principle
**Pull Over Push** (for this use case)

**Evidence in Repository**:
```python
# worker/api/v1/endpoints/jobs.py
@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str, user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == user.tenant_id).first()
    
    if not job:
        raise HTTPException(404, "Job not found")
    
    if job.status == "PENDING":
        return {"status": "PENDING", "message": "Processing..."}
    elif job.status == "COMPLETED":
        return {"status": "COMPLETED", "results": job.result_payload}
    elif job.status == "FAILED":
        return {"status": "FAILED", "error": job.error}
```

---

## WHY NOT THAT?

### Alternative 1: WebSocket (Persistent Connection)

```python
@app.websocket("/ws/jobs/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    
    # Monitor job status
    while True:
        job = await db.get_job(job_id)
        await websocket.send_json({
            "status": job.status,
            "results": job.result_payload if job.status == "COMPLETED" else None
        })
        
        if job.status == "COMPLETED":
            break
        
        await asyncio.sleep(1)  # Check every second
```

**Advantages**:
- Real-time updates (no polling latency)
- Server can push updates immediately
- Better UX (no delay between completion and seeing result)
- Fewer requests (not polling)

**Disadvantages**:
- Complex connection management
- Need connection affinity (connection tied to server)
- Harder to load balance
- Browser reconnection logic needed
- Stateful server (more memory)
- Debugging harder (persistent connection state)
- Deployment more complex (sticky sessions needed)

**Complexity**: Much higher

**Scalability**: Worse (stateful connections)

**UX**: Better (real-time)

**Infrastructure**: More complex (connection management)

---

### Alternative 2: Server-Sent Events (SSE)

```python
@app.get("/api/v1/jobs/{job_id}/stream")
async def stream_job_status(job_id: str, user: User = Depends(get_current_user)):
    async def event_generator():
        while True:
            job = await db.get_job(job_id)
            yield f"data: {json.dumps({'status': job.status})}\n\n"
            
            if job.status == "COMPLETED":
                break
            
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator())
```

**Advantages**:
- Simpler than WebSocket (HTTP-based)
- Server can push updates
- Better than polling (fewer requests)

**Disadvantages**:
- Still persistent connection (doesn't scale as well)
- Limited payload (text only)
- Browser support more limited than polling
- Deployment needs connection affinity

**Complexity**: Medium

**Scalability**: Better than WebSocket, worse than polling

---

### Alternative 3: Webhooks (Callback)

```python
# Client provides callback URL
POST /jobs
{
    "file": "...",
    "callback_url": "https://client.example.com/webhook"
}

# System calls callback when done
POST https://client.example.com/webhook
{
    "job_id": "...",
    "status": "COMPLETED",
    "results": {...}
}
```

**Advantages**:
- Truly asynchronous (client doesn't have to wait)
- Works across networks (firewall-friendly)
- Can batch notifications

**Disadvantages**:
- Requires client to expose endpoint (not always possible)
- Retry logic complex (webhook might fail)
- Ordering issues (webhooks might arrive out of order)
- Security complex (must verify webhook sender)

**Complexity**: High

**Reliability**: Lower (webhook might not arrive)

---

### Alternative 4: Message Streaming (Kafka, Pub/Sub)

```
# Client subscribes to job status topic
client.subscribe(f"job.{job_id}.status")

# System publishes updates
broker.publish(f"job.{job_id}.status", {"status": "COMPLETED"})
```

**Advantages**:
- Decoupled (system doesn't know about clients)
- Scalable (message broker handles distribution)
- Works for 1000s of clients

**Disadvantages**:
- Operational complexity (need message broker)
- Overkill for single job tracking
- Requires client to handle message broker connection

---

## TRADEOFF

**Current Design (Polling) Gains**:
- Simplicity (stateless HTTP)
- Scalability (any server handles any request)
- Load balancing (no sticky sessions)
- Testability (simple to test)
- Compatibility (works with any client)
- Horizontal scaling (no affinity)

**Current Design Sacrifices**:
- User experience (polling latency, refresh delay)
- Server load (repeated requests)
- Network bandwidth (polling traffic)
- Real-time updates (delay between event and notification)

**Net Tradeoff**: Simplicity/scalability at cost of UX

---

## FAILURE POINT

**When Polling Breaks**:

1. **Polling Interval Too Short**
   ```
   Poll every 100ms
   1000 users polling = 10,000 requests/second
   Server overwhelmed
   ```

2. **Polling Interval Too Long**
   ```
   Poll every 10 seconds
   User waits up to 10 seconds after completion
   Bad UX (results available, but user doesn't know)
   ```

3. **Polling Storm**
   ```
   User refreshes page constantly
   Hundreds of duplicate polls for same job
   No deduplication
   ```

4. **Lost Updates**
   ```
   Job completes at 10:01:05
   User polls at 10:01:04 (PENDING)
   User polls at 10:01:10 (COMPLETED)
   Window between completion and discovery: 5 seconds
   ```

---

## CHANGE CONDITION

**When to Replace Polling**:

1. **Real-Time Requirement**
   - Business rule: User sees result within 100ms of completion
   - Current: 1-10 second delay (polling interval)
   - Consider: WebSocket or SSE

2. **User Experience Critical**
   - Thousands of users waiting
   - Polling creates poor UX
   - Consider: Push mechanism

3. **Mobile App**
   - Battery drain from repeated polling
   - Consider: Push notifications or WebSocket

4. **Large User Base**
   - Polling creates overwhelming server load
   - Consider: Message broker for distribution

---

## SCALE CONDITION

**When Polling Becomes Problematic**:

### Scale: 100 users
- ✅ Polling fine (100 polls/minute at 10-second interval)

### Scale: 1,000 users
- ✅ Polling works (1000 polls/minute)

### Scale: 10,000 users
- ✅ Polling works (10,000 polls/minute)

### Scale: 100,000 users
- ⚠️ Issues:
  - Polling load adds up (100,000 polls/minute)
  - Each poll is database query (100,000 QPS)
  - Database connection pool exhausted

### Scale: 1,000,000 users
- ❌ Breaks:
  - 1M polls/minute = 16,666 requests/second
  - Database can't handle this
  - Polling-driven database overload
  - Consider: Push mechanism (message queue)

**Scaling Point**: ~10,000 concurrent users
- At this point, polling generates too much load

---

## LEARNING QUESTION

**Question**: Your system has 100,000 concurrent users waiting for job results. They poll every 5 seconds.

That's 100,000 / 5 = 20,000 requests/second (polling load).

Design a solution that:
1. Maintains simplicity (HTTP, stateless)
2. Reduces polling load by 90%
3. Keeps polling architecture (don't switch to WebSocket)

Options:
1. Increase polling interval (5s → 30s)
2. Add client-side deduplication (multiple tabs same job)
3. Use Redis to cache job status (reduce database hits)
4. Implement exponential backoff polling (first poll fast, then slow)
5. Use long-polling (hold request until ready, then respond)

Which would you choose? Why? What are trade-offs?

**Answer Tests Understanding Of**:
- Polling cost model
- Optimization without architecture change
- Trade-offs between responsiveness and load

---

# Summary: Architectural Decision Patterns

## Patterns Observed

### 1. **Defer Complexity**
- Start simple (monolith, polling, single provider)
- Add complexity when scale demands it
- Current repo at good balance point

### 2. **Fail-Safe Defaults**
- Circuit breaker prevents cascading failures
- Fallback providers ensure availability
- Graceful degradation (no hard failures)

### 3. **Multi-Tenant by Design**
- Tenant scoping built in from start
- Not retrofitted
- Every query includes tenant filter

### 4. **Type Safety**
- Pydantic validation throughout
- Type hints enable IDE support
- Errors caught early

### 5. **Explicit Over Implicit**
- Security filtering visible in code
- Not hidden in database rules
- Easier to audit and debug

### 6. **Separation of Concerns**
- Web tier separate from workers
- Services separated by responsibility
- Easy to reason about each part

## Decision Quality Assessment

| Decision | Quality | Confidence | Trade-off Balance |
|----------|---------|------------|-------------------|
| Async Architecture | Excellent | High | Good (simplicity vs scalability) |
| Multi-Provider LLM | Excellent | High | Good (cost vs reliability) |
| Query-Level Multi-Tenancy | Good | High | Reasonable (portability vs security) |
| Pydantic Validation | Excellent | High | Good (strictness vs flexibility) |
| Semantic Caching | Good | Medium | Reasonable (complexity vs cost) |
| Evaluation Pipeline | Good | High | Good (quality vs cost) |
| Monolithic Architecture | Good | High | Good (simplicity vs scalability) |
| Polling for Results | Good | High | Good (simplicity vs UX) |

---

# Questions For Self-Assessment

### For Each Major Decision

1. **Do you understand the core problem it solves?**
2. **Can you articulate realistic alternatives?**
3. **Can you explain the tradeoffs?**
4. **Do you know when it would break?**
5. **Do you know when to replace it?**
6. **Do you understand the failure modes?**
7. **Can you trace what would happen at scale?**

If you can answer YES to all 7 for each decision, you understand the architecture.

---

**Next Step**: Pick one decision you're unsure about. Deep-dive into it until you can answer all 7 questions.

