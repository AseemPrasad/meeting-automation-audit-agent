# Blind Spots Analysis: What You Think You Understand But Might Not

Based on your examination score (9.2/10) and the breadth of documentation you've reviewed, this document identifies conceptual gaps that typically emerge even for engineers who score well on surface-level understanding.

**Goal**: Force deeper reasoning about edge cases, failure modes, and subtle interactions that don't appear obvious until you need to debug or scale the system.

---

# Critical Blind Spots

## Blind Spot 1: Database Connection Pooling Under Load

### What You Appear to Understand

- SQLAlchemy uses connection pooling
- There's a max pool size (likely 10-20)
- Connections are returned to the pool after use
- Production uses PostgreSQL, dev uses SQLite

### What You're Actually Missing

The system has a **fundamental mismatch** between how long database connections are held and how long I/O operations take.

**The Problem**:

```python
# worker/api/v1/endpoints/jobs.py (hypothetical)
@app.post("/upload")
async def upload_meeting(file: UploadFile, db: Session = Depends(get_db)):
    # T=0: Connection acquired from pool
    
    job = Job(tenant_id=..., status="created")
    db.add(job)
    db.commit()
    # T=0.005: Connection still held (commit complete)
    
    # Now call Groq API (takes 20 seconds)
    transcription = await groq.transcribe(file)
    # T=20: Connection is STILL HELD (but not in use!)
    
    job.transcript = transcription
    job.status = "transcribed"
    db.commit()
    # T=20.005: Only NOW is connection released
```

**The Impact**:

With 50 concurrent requests:
- 50 connections acquired
- 50 connections × 20 seconds = 1000 connection-seconds
- Pool size 20 = 50 connections needed (impossible, deadlock)
- Users wait for a free connection (connection timeout)

### Why This Matters

This is a **silent killer** that doesn't show up in testing with 1-5 concurrent users but destroys production at 50+ concurrent users. The database isn't slow; the connections are just blocked waiting.

### Repository-Specific Example

In `worker/workflows/transcript_workflow.py`:

```python
# WRONG: Connection held during LLM call
def process_transcript(job_id: str, db: Session):
    job = db.query(Job).filter(Job.id == job_id).first()
    
    # Connection still held here
    result = groq_client.transcribe(job.audio_file)  # 20 sec, connection idle
    
    job.result = result
    db.commit()  # Finally release connection
```

**Right approach**:

```python
# RIGHT: Release connection before long I/O
def process_transcript(job_id: str, db: Session):
    job = db.query(Job).filter(Job.id == job_id).first()
    job_id_copy = job.id  # Copy ID
    db.close()  # RELEASE CONNECTION NOW
    
    # Now Groq call doesn't hold a connection
    result = groq_client.transcribe(job_id_copy)
    
    # Re-acquire connection only for final update
    db = get_db()
    job = db.query(Job).filter(Job.id == job_id_copy).first()
    job.result = result
    db.commit()
```

### The Test That Exposes This

**Question**: If 100 users upload at the same time, what happens in the first 30 seconds?

**Follow-up**: What's the actual connection pool size in `worker/core/database.py`? Is it safe for 100 concurrent users?

### Practical Exercise

1. Read `worker/core/database.py` and find the pool size setting
2. Calculate: max_concurrent_users = pool_size / (1 + avg_llm_call_time / db_call_time)
3. Identify every place where the code holds a connection during long I/O
4. Refactor to release connections before external API calls
5. Write a load test: 50 concurrent requests, measure connection wait time

---

## Blind Spot 2: Job Status Update Race Conditions

### What You Appear to Understand

- Jobs have status: CREATED → PROCESSING → TRANSCRIBED → EXTRACTING → COMPLETED/FAILED
- Status is stored in the database
- Celery workers update status as they work

### What You're Actually Missing

There's a race condition between:
1. The API returning status to user
2. The worker updating status
3. Concurrent workers (if the same job is processed twice)

**The Scenario**:

```
Time | Worker 1             | Worker 2            | Database State
-----|----------------------|---------------------|-------------------
0    | Start job #123       | (idle)              | status=PROCESSING
5    | Calling Groq API     | (idle)              | status=PROCESSING
10   | Groq completes       | (idle)              | status=PROCESSING
15   | Writing transcript   | (idle)              | status=PROCESSING
20   | Updating status      | (idle)              | status=PROCESSING
25   | Commits status=TRANSCRIBED | (idle)       | status=TRANSCRIBED

BUT WHAT IF:

Time | Worker 1             | Worker 2            | Database State
-----|----------------------|---------------------|-------------------
0    | Start job #123       | Picks up same job   | status=PROCESSING
1    | Calling Groq API     | Calling Groq API    | status=PROCESSING
20   | Groq done, process   | Groq done, process  | status=PROCESSING
21   | Set status=FAILED    | Set status=SUCCESS  | status=FAILED or SUCCESS?
22   | Commit               | Commit              | (unpredictable)
```

**Who updates last wins** - could be either worker.

### Why This Matters

- Users see inconsistent results
- Audit logs show contradictory status changes
- Retry logic becomes confused (job marked failed but transcript exists)
- Quality metrics break (evaluation runs on failed job)

### Repository-Specific Example

In `worker/workflows/transcript_workflow.py`:

```python
@app.task(bind=True)
def transcribe_audio(self, job_id: str):
    db = get_db()
    
    job = db.query(Job).filter(Job.id == job_id).first()
    # NO LOCK! Other worker can also grab this job
    
    job.status = "transcribing"
    db.commit()
    
    try:
        transcript = groq_client.transcribe(job.audio_file)
    except Exception as e:
        job.status = "failed"  # ← Race condition
        db.commit()
        return
    
    job.transcript = transcript
    job.status = "transcribed"
    db.commit()
```

**Better approach**: Use database lock or status transition validation

```python
def transcribe_audio(self, job_id: str):
    db = get_db()
    
    # Lock the row so no other worker can grab it
    job = db.query(Job)\
        .filter(Job.id == job_id)\
        .with_for_update()\
        .first()
    
    if job.status != "created":  # Prevent double-processing
        return  # Another worker already started
    
    job.status = "processing"
    db.commit()
    
    # Now only this worker can process it
```

### The Test That Exposes This

**Question**: What happens if Celery delivers the same job to two workers simultaneously?

**Follow-up**: How does the code currently prevent double-processing?

### Practical Exercise

1. Enable `TASK_ALWAYS_EAGER = False` in Celery config
2. Create a test that enqueues the same job twice
3. Observe status changes (you'll likely see non-deterministic results)
4. Implement `with_for_update()` in the database query
5. Re-run test and verify idempotent behavior

---

## Blind Spot 3: Multi-Tenant Isolation Edge Cases

### What You Appear to Understand

- Multi-tenancy is query-level isolation
- All queries filter by `tenant_id`
- Each user belongs to exactly one tenant
- Admin can see all tenant data

### What You're Actually Missing

There are subtle paths where tenant isolation can leak:

**Scenario 1: Implicit tenant from JWT, but not validated in update**

```python
@app.put("/jobs/{job_id}", dependencies=[Depends(get_current_user)])
async def update_job(job_id: str, update: JobUpdate, current_user: User):
    # Current user's tenant is implicit in JWT
    
    job = db.query(Job).filter(Job.id == job_id).first()
    # BUG: No tenant check! User can update ANY job_id if they know the UUID
    
    if job is None:
        raise 404
    
    job.status = update.status
    db.commit()
```

**Attack**: Attacker enumerates job UUIDs and updates other tenants' jobs.

**Scenario 2: Cache doesn't respect tenant boundary**

```python
# worker/services/llm/cache.py
@cache(ttl=3600)
def get_embedding(text: str) -> List[float]:
    return model.embed(text)

# Same text used by Tenant A and Tenant B
# Both hit the same cache entry
# Tenant B now has Tenant A's embedding (shouldn't matter)
# But what if cache key is too broad?
```

**Scenario 3: Job creation doesn't validate tenant_id**

```python
@app.post("/jobs")
async def create_job(job: JobCreate, current_user: User):
    new_job = Job(
        tenant_id=job.tenant_id,  # ← User can set any tenant_id!
        data=job.data
    )
    db.add(new_job)
    db.commit()
```

**Attack**: User sets `tenant_id` to different tenant's ID. Job gets created there.

### Why This Matters

- Data leakage between customers (compliance nightmare)
- Audit violation (accessing data you shouldn't access)
- Security vulnerability that's hard to detect
- Might only show up with specific UUID enumeration patterns

### Repository-Specific Example

In `worker/models/job.py`:

```python
class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(UUID, primary_key=True)
    tenant_id = Column(UUID, ForeignKey("tenants.id"))
    # Missing: unique constraint on (id, tenant_id)?
```

**Better**:

```python
# All queries should explicitly filter:
db.query(Job).filter(
    (Job.id == job_id) &
    (Job.tenant_id == current_user.tenant_id)
).first()

# Make tenant_id part of lookup
# Not: db.query(Job).filter(Job.id == job_id)
```

### The Test That Exposes This

**Question**: How would you test that Tenant A cannot access Tenant B's jobs?

**Follow-up**: What if two different users have UUIDs that are numerically close? Can one enumerate the other's jobs?

### Practical Exercise

1. Create two tenants (A and B) with one user each
2. User A uploads a job
3. Try accessing that job as User B (both with valid JWTs)
4. Verify you get 403 Forbidden (not 404)
5. Audit the codebase: find every `.filter()` call that doesn't include `tenant_id`
6. Fix any that are missing the check

---

# High Priority Blind Spots

## Blind Spot 4: LLM Circuit Breaker Behavior Under Cascading Failures

### What You Appear to Understand

- Circuit breaker pattern protects against cascading failures
- There are three states: CLOSED (working), OPEN (failing), HALF_OPEN (testing)
- Failure count determines state transition
- Helps prevent wasting API calls on dead services

### What You're Actually Missing

The circuit breaker has subtle timing issues when multiple LLM providers fail:

**Scenario**: Groq is down. Circuit breaker opens. System falls back to OpenAI. What happens?

```
T=0: Groq returns 500 errors
T=1: Circuit breaker opens for Groq
T=2: Router sends traffic to OpenAI
T=10: OpenAI rate limit hit (sudden spike)
T=11: OpenAI circuit breaker opens
T=12: No provider available (both open)
T=13: User requests fail with "no healthy provider"
T=14: Groq recovers, HALF_OPEN state
T=15: Circuit breaker tests Groq
T=16: Groq is healthy, circuit closes
T=17: Normal operation resumes

PROBLEM: From T=12 to T=16, all requests fail
(4 seconds of complete system outage)
```

### Why This Matters

- Predictable failure windows (bad for SLAs)
- No graceful degradation
- Cascade failure can take down entire system
- Recovery is binary (all-or-nothing)

### Repository-Specific Example

In `worker/services/llm/circuit_breaker.py`:

```python
class CircuitBreaker:
    def call(self, func, *args):
        if self.state == "open":
            raise CircuitBreakerOpen()
        
        try:
            result = func(*args)
            self.success_count += 1
            if self.success_count >= THRESHOLD:
                self.state = "closed"
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= THRESHOLD:
                self.state = "open"  # ← All traffic immediately rejected
            raise
```

**Problem**: When state = "open", **all** requests immediately fail. There's no:
- Exponential backoff for retry
- Jitter to prevent thundering herd
- Gradual traffic increase during HALF_OPEN

### The Test That Exposes This

**Question**: If Groq goes down, how long until the system recovers?

**Follow-up**: If OpenAI also goes down while Groq is recovering, what happens to user requests?

### Practical Exercise

1. Simulate Groq failure (mock to return 500)
2. Measure time until circuit opens
3. Measure time in "no healthy provider" state
4. Measure time until recovery
5. Calculate total user-facing outage
6. Implement exponential backoff during recovery

---

## Blind Spot 5: Semantic Cache Behavior Under Concurrent Writes

### What You Appear to Understand

- Semantic cache stores embeddings + results
- Similar queries hit cache (within cosine similarity threshold)
- Reduces LLM API calls
- Results in cost savings

### What You're Actually Missing

The cache has a **consistency problem** under concurrent writes:

**Scenario**:

```
User A: "Summarize meeting action items"
User B: Same query (text-identical)

Time | User A                        | User B              | Cache State
-----|-------------------------------|---------------------|-------------------
0    | Query cache (miss)            | Query cache (miss)  | {}
1    | Call Groq                     | Call Groq           | {}
20   | Get result: A₁                | Get result: B₁      | {}
21   | Compute embedding: E_A        | Compute embedding: E_B | {}
22   | Write cache: {E_A, A₁}        | (waiting)           | {E_A: A₁}
23   | (done)                        | Try to write cache  | {E_A: A₁}
24   | (done)                        | Write cache: {E_B, B₁} | {E_B: B₁} ← B₁!

PROBLEM: Cache now has B's result (possibly different from A's)
Next user C gets: "It could be A₁ or B₁ depending on timing"
```

**Why it matters**: 
- Same query can return different results (inconsistent)
- Cache hit rate is unpredictable
- Cost savings are not guaranteed

### Repository-Specific Example

In `worker/services/cache/semantic_cache.py`:

```python
class SemanticCache:
    def get_or_compute(self, query: str, compute_fn):
        # Check cache
        embedding = embed(query)
        cached = self.find_similar(embedding, threshold=0.95)
        
        if cached:
            return cached.result  # Hit!
        
        # Miss, compute
        result = compute_fn(query)
        
        # Save to cache
        self.cache_table.insert({
            "embedding": embedding,
            "result": result,
            "query_text": query
        })
        return result
```

**Problem**: Between checking cache and writing cache, another worker might have written the same thing. Now you have duplicates or inconsistencies.

### The Test That Exposes This

**Question**: If 10 users submit the exact same query simultaneously, how many LLM calls are made? (Answer: probably 10, not 1)

**Follow-up**: How would you guarantee exactly 1 LLM call for identical concurrent queries?

### Practical Exercise

1. Create a test that fires 10 identical queries concurrently
2. Count Groq API calls (you'll likely see 10)
3. Implement cache locking using Redis SETNX
4. Re-run test and verify only 1 LLM call
5. Measure latency: does locking add overhead?

---

## Blind Spot 6: Evaluation Pipeline Metric Conflicts

### What You Appear to Understand

- Evaluation pipeline computes deterministic metrics
- LLM judge provides quality assessment
- Results are compared and exported
- Helps identify low-quality extractions

### What You're Actually Missing

There's a **fundamental conflict** between metrics and judge that the system doesn't handle:

**Scenario**: 

```
Meeting: "Build React component by Friday"

Extraction:
- Action: "Build React component"
- Deadline: "Friday"
- Confidence: 0.95

Deterministic Metrics:
- Extraction recall: 100% (all action items found)
- Format validity: 100% (all fields present)
- Confidence score: 0.95

LLM Judge:
- Faithfulness: 0.3 ("React is not specific enough")
- Completeness: 0.5 ("Missing which specific component")
- Clarity: 0.7 ("Deadline should be specific date")

Overall Score: (100 + 100 + 95) / 3 = 98.3 metrics vs. (30 + 50 + 70) / 3 = 50 judge

Decision: Keep or reject?
```

**The problem**: Metrics and judge disagree. Which do you trust?

### Why This Matters

- Can't identify quality issues that metrics don't catch
- Can't rely on judge alone (might be wrong)
- Combined score is misleading (98 + 50 average = 74?)
- Unclear which extractions to send for reprocessing

### Repository-Specific Example

In `worker/eval/pipeline.py`:

```python
class EvaluationPipeline:
    def evaluate(self, job):
        # Compute metrics
        metrics = self.compute_metrics(job)
        metric_score = average(metrics.values())  # Maybe 98
        
        # Ask LLM judge
        judge_score = self.judge.assess(job)  # Maybe 50
        
        # Combine?
        final_score = (metric_score + judge_score) / 2  # 74
        
        # What does 74 mean?
        if final_score < 0.7:
            export_for_reprocessing(job)
```

**Better approach**: Understand what each measures

```
Metrics: "Is the data well-formatted and complete?"
Judge: "Is the data actually correct and useful?"

These measure different things. Don't average them.

Decision logic:
- If metrics fail: structural problem (fix parser)
- If judge fails: semantic problem (refine prompt or reprocess)
- If both fail: both issues present (reprocess and fix parser)
```

### The Test That Exposes This

**Question**: If metrics score 95 but judge scores 30, what does that tell you? Should you reject the extraction?

**Follow-up**: How would you decide whether to reprocess based on metric-judge disagreement?

### Practical Exercise

1. Run evaluation on 100 jobs
2. Find 10 where metrics > 80 but judge < 50
3. Manually inspect those 10 (are they actually bad?)
4. Refactor evaluation to separate "structural quality" from "semantic quality"
5. Create separate thresholds for each

---

## Blind Spot 7: Rate Limiting Doesn't Actually Protect Against Spike

### What You Appear to Understand

- Rate limiting uses token bucket algorithm
- Limits requests per tenant per time window
- Returns 429 if exceeded
- Protects against abuse

### What You're Actually Missing

Rate limiting has a **timing precision issue** that allows bursts:

**Scenario**:

```
Tenant limit: 100 requests per minute
Token bucket: fills at 100/60 = 1.67 tokens/second

Time | Tokens | Request | Status
-----|--------|---------|--------
0.0  | 100    | GET #1  | 200 OK, tokens=99
0.01 | 99     | GET #2  | 200 OK, tokens=98
0.02 | 98     | GET #3  | 200 OK, tokens=97
...  | ...    | ...     | ...
0.6  | 0      | GET #100| 200 OK, tokens=0
0.61 | 0+1.67 ≈ 1.67 tokens arrive
0.61 | 1      | GET #101| 200 OK, tokens=0
0.61 | 0+1.67 ≈ 1.67 tokens arrive
0.62 | 1      | GET #102| 200 OK, tokens=0

RESULT: User spent entire bucket in 0.6 seconds
Then continues at 1-2 req/sec indefinitely
```

**The impact**:
- User can still DoS by careful timing
- Protection is only per-minute average, not per-second burst
- Real-world spike (100 requests in 1 second) is allowed

### Why This Matters

- A single determined attacker can still spike
- Depends on timer precision
- Doesn't actually prevent peak load on database

### Repository-Specific Example

In `worker/middleware/rate_limit.py`:

```python
class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
    
    def allow_request(self):
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill: add tokens based on time elapsed
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
```

**Problem**: If requests arrive in burst at exactly right moment, tokens might be higher than expected due to timing precision.

**Better**: Add secondary protection

```python
class AdaptiveRateLimiter:
    def allow_request(self):
        # Check token bucket
        if not self.token_bucket.allow():
            return False
        
        # ALSO check: recent request count in last 1 second
        recent_requests = self.get_requests_in_window(1.0)
        if recent_requests > self.burst_limit:
            return False  # Spike detected
        
        return True
```

### The Test That Exposes This

**Question**: If a tenant's limit is 100/min, can they make 100 requests in 1 second and then 100 more in the next second?

**Follow-up**: How would you prevent this?

### Practical Exercise

1. Implement rate limiter test with mock clock
2. Send 100 requests at T=0.1 seconds
3. Send 100 more at T=60.1 seconds
4. Measure: are both batches allowed? (They probably are)
5. Add secondary burst limiting (max per second)
6. Re-run test

---

# Medium Priority Blind Spots

## Blind Spot 8: Job Status Polling Race Condition

### What You Appear to Understand

- User uploads job
- API returns job_id
- User polls `/jobs/{job_id}` to check status
- Eventually status becomes COMPLETED
- User downloads results

### What You're Actually Missing

There's a race between job completion and result visibility:

```
Worker                        | API                   | User
-----------------------------|------------------------|------------------
Job done, result={...}        | (idle)                | Poll: status=COMPLETED
Commit to database            | (idle)                | GET /jobs/{id}/results
(committed)                   | (idle)                | (2ms lag)
                              | Query job (hit cache?) | 
                              | Return status=COMPLETED | 
                              | Return result=null    | ← Result not there yet!
                              | (cache invalidation?) |
```

**Problem**: User sees COMPLETED but result is null.

### Why This Matters

- User experience is broken (show "complete" but no data)
- Retry logic gets confused
- Frontend error handling unclear

### Repository-Specific Example

In `worker/api/v1/endpoints/jobs.py`:

```python
@app.get("/jobs/{job_id}")
async def get_job(job_id: str, current_user: User):
    job = db.query(Job).filter(Job.id == job_id).first()
    return {
        "status": job.status,
        "result": job.result_payload,  # Might be None even if status=COMPLETED
        "created_at": job.created_at
    }
```

**Better**: Verify consistency

```python
@app.get("/jobs/{job_id}")
async def get_job(job_id: str, current_user: User):
    job = db.query(Job).filter(Job.id == job_id).first()
    
    # Consistency check
    if job.status == "completed" and job.result_payload is None:
        # Inconsistent state!
        # Either result is still being written or status was set early
        return {
            "status": "processing",  # ← Show as still processing
            "result": None,
            "created_at": job.created_at
        }
    
    return {
        "status": job.status,
        "result": job.result_payload,
        "created_at": job.created_at
    }
```

### The Test That Exposes This

**Question**: If you query a job immediately after seeing status=COMPLETED, is result guaranteed to be non-null?

**Follow-up**: What's the race window? Is it real in production?

### Practical Exercise

1. Write test that checks job status just after completion
2. Add 1-second polling loop
3. Monitor for cases where status=COMPLETED but result=None
4. Implement consistency check as above
5. Re-run test

---

## Blind Spot 9: RAG Reranking Doesn't Always Help

### What You Appear to Understand

- RAG: Retrieve relevant documents from knowledge base
- Reranking: Re-order results by relevance
- Should improve extraction quality

### What You're Actually Missing

Reranking can **hurt** in specific scenarios:

**Scenario 1: Query is too specific**

```
Query: "Extract specific cost breakdown for AWS infrastructure from May 2024"
Top 5 retrieved documents:
1. "AWS costs July 2024" (retrieved, but July not May)
2. "General AWS pricing guide" (retrieved, generic)
3. "Infrastructure costs summary" (retrieved, contains May data)
4. "May 2024 financial report" (retrieved, wrong domain)
5. "Misc notes" (retrieved, noise)

Reranker scores:
1. AWS July: 0.92 (contains "AWS infrastructure")
2. Pricing: 0.88 (contains "AWS" and "infrastructure")
3. Infrastructure May: 0.85 (contains "costs" and "May")
4. May report: 0.87 (contains "May 2024")
5. Misc: 0.20

After reranking: [1, 4, 2, 3, 5]
New rank #3 is correct (infrastructure May) but now ranked 4th!
Reranker got it wrong.
```

**Scenario 2: Reranker picks noise**

```
Query: "Team satisfaction scores"
Retrieved:
1. "Employee feedback Q2 2024" (relevant: contains scores)
2. "Salary survey results" (irrelevant: about salary)
3. "Training effectiveness" (somewhat relevant: about metrics)

Reranker incorrectly scores:
1. Salary survey: 0.95 (contains "scores")
2. Employee feedback: 0.92
3. Training: 0.88

Result: Wrong document ranked first.
```

### Why This Matters

- Reranking adds latency (extra LLM call)
- Doesn't always improve results
- Can make results worse
- Added cost without guaranteed benefit

### Repository-Specific Example

In `worker/rag/pipeline.py`:

```python
class RAGPipeline:
    def retrieve_and_rank(self, query: str):
        # Retrieve
        documents = self.retriever.retrieve(query, top_k=10)
        
        # Rerank (unconditional)
        ranked = self.reranker.rerank(query, documents)
        
        return ranked[:5]  # Top 5 after reranking
```

**Better**: Conditional reranking

```python
def retrieve_and_rank(self, query: str):
    documents = self.retriever.retrieve(query, top_k=10)
    
    # Only rerank if documents are uncertain (close scores)
    scores = [d.relevance_score for d in documents]
    max_score = max(scores)
    min_score = min(scores)
    score_spread = max_score - min_score
    
    if score_spread < 0.2:  # Documents are close in relevance
        # Reranking might help
        ranked = self.reranker.rerank(query, documents)
    else:
        # Retriever already has clear winners
        ranked = documents  # Skip reranking
    
    return ranked[:5]
```

### The Test That Exposes This

**Question**: Does reranking improve extraction quality by more than the reranking latency costs?

**Follow-up**: In what scenarios does reranking hurt?

### Practical Exercise

1. Disable reranking, measure extraction accuracy
2. Enable reranking, measure accuracy
3. Compare: better? worse? no change?
4. Measure latency impact (extra LLM call)
5. Calculate ROI: accuracy improvement vs. latency cost
6. Decide: when to enable/disable reranking

---

## Blind Spot 10: Authentication Token Refresh Not Implemented

### What You Appear to Understand

- JWT tokens used for stateless auth
- Token has expiration (maybe 1 hour)
- After expiration, user must re-login

### What You're Actually Missing

**There's likely no token refresh mechanism**, which means:

**Scenario**:

```
T=0: User logs in
     - Access token: exp=3600 (1 hour)
     - (No refresh token?)

T=30 min: User working
          - Makes requests with access token
          - All requests pass

T=1 hour: Access token expires
          - User makes request
          - 401 Unauthorized
          - User must re-login (interrupt workflow)

PROBLEM: No way to silently refresh
```

**Better systems**:

```
T=0: User logs in
     - Access token: exp=300 (5 min)
     - Refresh token: exp=86400 (1 day, httpOnly cookie)

T=4:50 min: API detects expiring token
            - Silently refreshes using refresh token
            - Returns new access token
            - User doesn't notice

T=1 day: Refresh token expires
         - User must re-login
         - But only after 1 day, not 5 min
```

### Why This Matters

- Breaks user experience if JWT is short-lived
- Annoying login prompts in middle of work
- Or, JWT is long-lived (security risk)
- No middle ground

### Repository-Specific Example

In `worker/core/security.py`:

```python
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=1)  # ← Default 1 hour
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
```

**Missing**: No refresh token, no rotation logic.

### The Test That Exposes This

**Question**: If a user's JWT expires while they're using the app, what happens?

**Follow-up**: How do they get back without re-entering password?

### Practical Exercise

1. Check if refresh tokens exist in codebase (search for "refresh")
2. If not: implement refresh token mechanism
3. Store refresh token in httpOnly cookie
4. Implement `/auth/refresh` endpoint
5. Configure JWT expiry to 15 minutes (short) for access token
6. Test user experience: does login feel seamless?

---

# Low Priority Blind Spots

## Blind Spot 11: Error Messages Leak Information

### What You Appear to Understand

- Return error messages to user
- Include status codes (404, 500, etc.)
- Help with debugging

### What You're Actually Missing

Error messages can leak security information:

**Examples**:

```
❌ Bad: "User with email 'attacker@example.com' not found"
   (Confirms email exists in database)

✅ Good: "Invalid email or password"
   (Doesn't confirm existence)

---

❌ Bad: "Job #550e8400-e29b-41d4-a716-446655440000 not found"
   (User can enumerate all job IDs)

✅ Good: "Job not found or access denied"
   (Doesn't confirm UUID validity)

---

❌ Bad: "Database connection timeout"
   (Reveals infrastructure)

✅ Good: "Service temporarily unavailable"
   (Generic, safe)
```

### Why This Matters

- User enumeration attacks
- Database structure disclosure
- Infrastructure reconnaissance
- Compliance violation (leaking internals)

### The Test That Exposes This

**Question**: If you try to access a job from a different tenant, what error message do you get?

**Follow-up**: Does the error message distinguish between "not found" and "access denied"? If not, you're leaking information.

### Practical Exercise

1. Audit all error messages in endpoints
2. Find ones that reveal information
3. Generalize them
4. Add tests ensuring no information leak

---

## Blind Spot 12: Evaluation Export Format Not Versioned

### What You Appear to Understand

- Evaluation pipeline exports results
- Results used for monitoring quality
- Exports are stored somewhere

### What You're Actually Missing

There's no versioning on export format. If schema changes:

**Scenario**:

```
2024-08-14: Export format version 1
{
  "job_id": "...",
  "metrics": {...},
  "judge_score": 0.85
}

2024-09-01: Metrics added new field
{
  "job_id": "...",
  "metrics": {...},
  "judge_score": 0.85,
  "semantic_similarity": 0.92  ← New field
}

Downstream consumers break if they expect old format
```

### Why This Matters

- Schema drift breaks data pipeline
- Analysis tools expect specific fields
- No way to handle mixed versions

### Practical Exercise

1. Add `export_version: int` to evaluation export
2. Document version changes
3. Implement version-aware parsers downstream

---

# Summary Table

| Blind Spot | Priority | Category | Impact | Time to Fix |
|-----------|----------|----------|--------|------------|
| Connection pooling | Critical | Concurrency | Production outage | 2-4 hours |
| Job status race conditions | Critical | Concurrency | Data inconsistency | 2-3 hours |
| Multi-tenant isolation gaps | Critical | Security | Data leakage | 3-4 hours |
| Circuit breaker timing | High | Reliability | Cascading failure | 3-4 hours |
| Semantic cache consistency | High | Performance | Non-deterministic results | 2-3 hours |
| Evaluation metric conflicts | High | Design | Wrong quality assessment | 2-3 hours |
| Rate limiting spike | High | DoS protection | Ineffective protection | 2-3 hours |
| Status polling race | Medium | Data consistency | Poor UX | 1-2 hours |
| RAG reranking | Medium | Performance | Wasted cost | 2-3 hours |
| Token refresh | Medium | Security/UX | Poor experience | 2-3 hours |
| Error message leakage | Low | Security | Information disclosure | 1-2 hours |
| Export versioning | Low | Maintenance | Breaking changes | 1-2 hours |

---

# How to Use This Document

## If You Have 1 Hour

Focus on **Critical** blind spots:
1. Connection pooling
2. Job status races
3. Multi-tenant isolation

These are production issues that will bite you.

## If You Have 3 Hours

Add **High** priority:
4. Circuit breaker
5. Semantic cache
6. Evaluation metrics
7. Rate limiting

These affect reliability and correctness.

## If You Have a Full Day

Work through all 12 blind spots. For each:

1. Read the explanation
2. Read the repository-specific example
3. Answer the "Test Question"
4. Complete the "Practical Exercise"
5. Commit your fixes

## Recommended Order

1. Start with Critical (foundation)
2. Move to High (robustness)
3. Polish with Medium (UX)
4. Audit with Low (security hygiene)

---

# Validation

After working through these exercises, you should be able to:

✅ Explain database connection lifecycle in detail  
✅ Design idempotent job processing  
✅ Audit multi-tenant isolation in code  
✅ Design circuit breaker with graceful degradation  
✅ Implement cache consistency under concurrency  
✅ Evaluate design tradeoffs in evaluation pipeline  
✅ Understand rate limiting limitations  
✅ Implement status consistency checks  
✅ Know when reranking helps vs. hurts  
✅ Design token refresh mechanisms  
✅ Write secure error messages  
✅ Version data exports  

If you can do these, you've moved from 9.2/10 → 9.8/10 on deep understanding.

