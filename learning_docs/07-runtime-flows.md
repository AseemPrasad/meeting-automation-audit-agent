# Runtime Flows

Trace actual requests through the system step-by-step.

---

## Flow 1: User Registration and Login

### Registration

```
POST /api/v1/auth/register
{
  "email": "alice@acme.com",
  "password": "secret123"
}

↓ [Route Handler: worker/api/v1/endpoints/auth.py]

1. Validate Input
   └─ email format valid? ✓
   └─ password strength? ✓

2. Check if user exists
   db.query(User).filter(
       User.email == "alice@acme.com"
   ).first()
   
   Result: None (doesn't exist yet)

3. Generate Tenant ID
   tenant_id = uuid.uuid4()
   (First user in this email domain gets new tenant)

4. Hash Password
   password_hash = bcrypt.hashpw(
       b"secret123",
       bcrypt.gensalt()
   )
   
   Result: $2b$12$R9h/cIPz0gi.URNNK3kh2OPST9/PgBkqquzi.Ee8K2T23DsqAWXci
   (deterministic, salted, salted, slowish to compute)

5. Create User Record
   user = User(
       id=uuid.uuid4(),
       email="alice@acme.com",
       password_hash="$2b$12$...",
       tenant_id=tenant_id,
       role="admin",  # First user is admin
       is_active=True
   )
   db.add(user)
   db.commit()  ← Atomic write

6. Generate JWT Token
   payload = {
       "sub": str(user.id),
       "tenant_id": str(tenant_id),
       "exp": datetime.utcnow() + timedelta(minutes=60)
   }
   
   token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
   
   Result: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWI...

7. Return Response
   {
       "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWI...",
       "token_type": "bearer",
       "expires_in": 3600
   }

Response Time: ~50ms
```

### Login

```
POST /api/v1/auth/login
{
  "email": "alice@acme.com",
  "password": "secret123"
}

↓ [Route Handler]

1. Query User
   user = db.query(User).filter(
       User.email == "alice@acme.com"
   ).first()
   
   Result: User(id=uuid, password_hash="$2b$12$...")

2. Verify Password
   if not bcrypt.checkpw(b"secret123", user.password_hash):
       raise AuthenticationError()
   
   (Constant-time comparison prevents timing attacks)

3. Check if Active
   if not user.is_active:
       raise UserInactiveError()

4. Generate JWT Token
   (Same as registration, step 6)

5. Return Token
   {
       "access_token": "...",
       "token_type": "bearer",
       "expires_in": 3600
   }

Response Time: ~100ms
(Slower due to bcrypt verification)
```

**Key Insight**: [Observable] Tokens are issued, not stored. Stateless authentication.

---

## Flow 2: Upload and Process Meeting

### Upload (Immediate Response)

```
POST /api/v1/transcripts/process
{
  "file": <audio.mp3, 25MB>
}
Header: Authorization: Bearer eyJhbGc...

↓ [Route Handler: worker/api/v1/endpoints/jobs.py]

1. FastAPI receives async request
   ├─ Adds to event loop
   └─ Other requests can be processed simultaneously

2. Extract JWT Token
   Authorization: Bearer eyJhbGc...
   ↓
   token = "eyJhbGc..."

3. Validate JWT
   [Middleware or dependency injection]
   
   try:
       payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
   except jwt.ExpiredSignatureError:
       raise HTTPException(401, "Token expired")
   except jwt.InvalidTokenError:
       raise HTTPException(401, "Invalid token")
   
   Result:
       user_id = UUID("550e8400-...")
       tenant_id = UUID("aaa-...")
       exp = 2026-08-15 10:05:00

4. Get Current User
   user = db.query(User).filter(
       User.id == user_id,
       User.tenant_id == tenant_id,
       User.is_active == True
   ).first()
   
   Result: User(id=..., tenant_id="aaa", role="admin")

5. Check Rate Limit
   [Middleware]
   
   key = f"rate_limit:{tenant_id}:/api/v1/transcripts/process"
   
   current = redis.get(key)  # Atomic counter
   if current >= 120:  # 120 requests per minute
       raise HTTPException(429, "Rate limit exceeded")
   
   redis.incr(key)
   redis.expire(key, 60)
   
   Result: Request passes (45/120)

6. Validate File
   ├─ file.content_type in ["audio/mpeg", "audio/wav", ...]? ✓
   ├─ file.size <= 500MB? ✓
   └─ Continue

7. Create Job Record
   job = Job(
       id=uuid.uuid4(),
       tenant_id=tenant_id,
       user_id=user_id,
       status="PENDING",
       audio_filename="audio.mp3",
       audio_url=f"s3://bucket/{job_id}.mp3",
       created_at=datetime.utcnow()
   )
   
   db.add(job)
   db.commit()  ← Persistent (survives restart)
   
   Result: Job persisted to SQLite

8. Enqueue Celery Task
   [worker/core/celery_app.py]
   
   celery_app.send_task(
       "worker.workflows.transcript_workflow.process_transcript",
       args=[str(job.id)],
       queue="transcripts"
   )
   
   This creates message in Redis:
   {
       "type": "task",
       "task": "worker.workflows.transcript_workflow.process_transcript",
       "id": "celery-task-uuid",
       "args": ["550e8400-..."],
       "kwargs": {},
       "retries": 0
   }

9. Return 202 Accepted Response
   HTTP/1.1 202 Accepted
   Content-Type: application/json
   
   {
       "job_id": "550e8400-...",
       "status": "PENDING",
       "message": "Transcription in progress. Check back in 30 seconds.",
       "check_url": "/api/v1/jobs/550e8400-..."
   }

Response Time: ~50ms
(Fast because we return before doing work)
```

**Key Insight**: [Observable] Async + queueing = instant response. Real work happens in background.

---

### Processing (Background)

```
[Celery Worker picks up task from Redis queue]

1. Dequeue Task
   Queue: "transcripts"
   ↓
   Message: process_transcript(job_id="550e8400-...")

2. Update Job Status
   job = db.query(Job).filter(Job.id == "550e8400-...").first()
   
   if job.status == "COMPLETED":
       return  # Already processed (idempotent)
   
   job.status = "PROCESSING"
   job.started_at = datetime.utcnow()
   db.commit()
   
   Result: Database shows "PROCESSING"
   (Polling client sees status change)

3. Transcribe Audio
   [Call Groq Whisper API]
   
   audio_data = read_from_s3(job.audio_url)
   
   response = await groq.audio.transcriptions.create(
       file=audio_data,
       model="whisper-large-v3",
       language="en"
   )
   
   Result:
   """
   Alice: Let's ship this by Friday.
   We need to finalize the design and testing.
   
   Bob: I can handle the frontend.
   
   Alice: Great. Let's reconvene Thursday morning.
   """
   
   Time: 20 seconds (for 1-hour meeting)

4. Check Cache (Semantic)
   [worker/services/cache/semantic_cache.py]
   
   transcript_hash = sha256(transcript)
   
   cached = redis.get(f"cache:transcript:{transcript_hash}")
   if cached:
       use cached result, skip LLM call
       saving ~$0.05
   
   Result: Cache miss (new transcript)

5. Extract Action Items & Decisions
   [LLM Router: worker/services/llm/router.py]
   
   Prompt:
   """
   Extract from transcript:
   1. Action items (who does what by when)
   2. Key decisions (what was decided)
   3. Sentiment (positive/negative)
   
   Transcript:
   {transcript}
   
   Return JSON:
   {
     "action_items": [...],
     "decisions": [...],
     "sentiment": 0.0-1.0
   }
   """
   
   Try providers in order:
   
   a) Try Groq (Primary)
      ├─ Check circuit breaker: CLOSED? Yes
      ├─ Call: await groq.chat.completions.create(...)
      ├─ Result: TIMEOUT (Groq down!)
      ├─ Mark failure: circuit_breaker.record_failure()
      ├─ Continue to next provider
      
   b) Try OpenAI (Fallback 1)
      ├─ Check circuit breaker: CLOSED? Yes
      ├─ Call: await openai.chat.completions.create(...)
      ├─ Result: {"action_items": [...], ...}
      ├─ Mark success: circuit_breaker.record_success()
      └─ Return result
   
   Time: 10 seconds (Groq timeout ~5s, OpenAI ~5s)
   Cost: Groq failed, OpenAI paid ($0.05)

6. Validate Structured Output
   [Pydantic validation]
   
   response_text = json.loads(result)
   
   validated = MeetingAnalysisResponse(
       action_items=response_text["action_items"],
       decisions=response_text["decisions"],
       sentiment=response_text["sentiment"]
   )
   
   # Pydantic validates types/structure
   # Raises ValidationError if invalid
   
   Result: Typed Python object

7. Evaluate Quality
   [worker/eval/pipeline.py]
   
   a) Deterministic Metrics (FAST)
      ├─ Faithfulness: "ship" in transcript? Yes (100%)
      ├─ Recall: All obvious items found? (95%)
      └─ Score: 0.95
   
   b) LLM Judge (SLOWER)
      ├─ Prompt LLM: "Is this extraction faithful?"
      ├─ Response: "Yes, all mentioned in transcript. Score: 0.98"
      └─ Score: 0.98
   
   Combined Score: 0.96
   
   Time: 3 seconds

8. Export If Low Score
   if quality_score < 0.70:
       db.add(BenchmarkSample(
           transcript=transcript,
           extraction=validated,
           score=quality_score,
           created_at=now()
       ))
       db.commit()
   
   Result: Low-quality samples saved for model improvement

9. Store Result
   job.status = "COMPLETED"
   job.result_payload = {
       "action_items": [
           {"task": "Ship feature", "assignee": "Bob", ...}
       ],
       "decisions": [...],
       "sentiment": 0.75
   }
   job.quality_score = 0.96
   job.completed_at = datetime.utcnow()
   
   db.commit()  ← Results now visible to client

10. Mark Task Complete
    (Celery automatically removes from queue)
    
    Result: Redis message deleted

Processing Time: ~35 seconds total
├─ Transcription: 20s
├─ LLM extraction: 10s (Groq timeout + OpenAI)
└─ Evaluation: 3s
└─ Persist: 2s
```

**Key Insight**: [Observable] At step 5b, Groq is down but system automatically uses OpenAI. User is unaffected.

---

### Polling for Results

```
Client polls repeatedly:

GET /api/v1/jobs/550e8400-...
Header: Authorization: Bearer eyJhbGc...

↓ [Route Handler]

1. Validate JWT (same as step 3)
2. Get User (same as step 4)
3. Query Database (tenant-scoped)

   job = db.query(Job).filter(
       Job.id == "550e8400-...",
       Job.tenant_id == user.tenant_id  ← Security
   ).first()
   
   if not job:
       raise HTTPException(404, "Not found")
       (Could mean job doesn't exist OR belongs to different tenant)

4. Return Status

   First poll (5 sec after upload):
   {
       "status": "PROCESSING",
       "created_at": "2026-08-14T10:00:00Z",
       "started_at": "2026-08-14T10:00:10Z",
       "estimated_completion": "2026-08-14T10:00:45Z"
   }

   Later poll (40 sec after upload):
   {
       "status": "COMPLETED",
       "created_at": "2026-08-14T10:00:00Z",
       "started_at": "2026-08-14T10:00:10Z",
       "completed_at": "2026-08-14T10:00:45Z",
       "results": {
           "action_items": [
               {
                   "task": "Ship feature",
                   "assignee": "Bob",
                   "deadline": "2026-08-15",
                   "priority": "high"
               },
               {
                   "task": "Finalize design",
                   "assignee": "Alice",
                   "deadline": "2026-08-15",
                   "priority": "high"
               }
           ],
           "decisions": [
               {
                   "decision": "Frontend: Bob",
                   "rationale": "Bob has frontend expertise",
                   "impact": "Speeds up feature delivery"
               }
           ],
           "sentiment": 0.75
       }
   }

Response Time: ~50ms (database query)
```

**Key Insight**: [Observable] Client controls polling frequency. Server doesn't push. Simpler, more scalable.

---

## Flow 3: Error Handling Cascade

```
Scenario: Groq times out AND OpenAI rate limits AND Anthropic fails

POST /api/v1/transcripts/process

[...steps 1-4 same as Flow 2...]

5. Extract with Router

   Try Groq:
   ├─ Call groq.chat.completions.create()
   └─ Result: TIMEOUT (5-second timeout)
      └─ Log: ERROR [groq] Timeout after 5s
      └─ circuit_breaker["groq"].record_failure()
      └─ Continue
   
   Try OpenAI:
   ├─ Call openai.chat.completions.create()
   └─ Result: 429 Rate Limit (too many requests)
      └─ Log: ERROR [openai] Rate limited
      └─ circuit_breaker["openai"].record_failure()
      └─ Continue
   
   Try Anthropic:
   ├─ Call anthropic.messages.create()
   └─ Result: 500 Server Error
      └─ Log: ERROR [anthropic] Server error
      └─ circuit_breaker["anthropic"].record_failure()
      └─ Continue
   
   Try Gemini:
   ├─ Call gemini.generate_content()
   └─ Result: SUCCESS (free tier, but working)
      ├─ Log: WARN [gemini] Using final fallback
      ├─ circuit_breaker["gemini"].record_success()
      └─ Return result

6. Result is extracted using Gemini

7. Quality evaluation might show lower score
   (Gemini is weaker than Groq/OpenAI)
   └─ Export to benchmark dataset for improvement

8. Job completes with status=COMPLETED
   (Not FAILED, because a provider succeeded)
   
   Result: User gets results, not errors
   
   BUT: Alert sent to operator
   "Multiple LLM providers down: Groq, OpenAI, Anthropic"

Response to Client: 202 Accepted (results processed)
```

**Key Insight**: [Observable] Layered fallbacks. Cascading failures handled gracefully.

---

## Flow 4: Rate Limit Exceeded

```
Tenant A makes 121st request in 1 minute

POST /api/v1/transcripts/process

[...steps 1-2...]

3. Extract JWT (same)
4. Get User (same)
5. Check Rate Limit

   key = f"rate_limit:AAA:/api/v1/transcripts/process"
   
   current = redis.get(key)  # Now 120
   if current >= LIMIT:
       raise HTTPException(429, "Rate limit exceeded")
   
   Log: WARN [rate_limit] Tenant AAA exceeded limit

6. Return 429 Response

   HTTP/1.1 429 Too Many Requests
   Content-Type: application/json
   Retry-After: 30
   
   {
       "detail": "Rate limit exceeded. Maximum 120 requests per minute.",
       "reset_in_seconds": 30
   }

Response Time: ~10ms
(Fails fast, doesn't waste resources)
```

**Key Insight**: [Observable] Rate limits are per-tenant. Doesn't affect Tenant B.

---

## Flow 5: Multi-Tenancy Isolation

```
Scenario: Two users from different tenants upload identical audio

Alice (Tenant A) uploads meeting.mp3
    └─ Job created with tenant_id="AAA"
    └─ Transcribed and extracted
    └─ Results stored with tenant_id="AAA"

Bob (Tenant B) uploads same meeting.mp3
    └─ Job created with tenant_id="BBB"
    └─ Different Celery task enqueued
    └─ Results stored with tenant_id="BBB"

When Alice queries /jobs/:

    SELECT * FROM jobs WHERE id=? AND tenant_id='AAA'
    
    Returns only Alice's jobs
    Cannot see Bob's results

When Bob queries /jobs/:

    SELECT * FROM jobs WHERE id=? AND tenant_id='BBB'
    
    Returns only Bob's jobs
    Cannot see Alice's results

Even though backend processed same audio twice:
    ├─ Cache might return same cached result
    ├─ Both get same extracted data
    └─ But results are stored separately by tenant
    └─ Complete data isolation

Cost: Groq charges for both transcriptions
(No cross-tenant deduplication at API level)
```

**Key Insight**: [Observable] Complete data isolation at database layer. Cannot accidentally leak data.

---

## Performance Characteristics

| Operation | Time | Bottleneck |
|-----------|------|-----------|
| Transcription (Groq) | 20-30s | API latency, audio processing |
| LLM Extraction | 5-10s | API latency, model inference |
| Quality Eval | 2-5s | LLM judge latency |
| Database Query | <100ms | Local or network round-trip |
| Polling | 50ms | Database query only |
| Rate Limit Check | <10ms | Redis in-memory lookup |
| JWT Validation | 5ms | Cryptographic verification |

**Critical Path**: Transcription (20s) + Extraction (7s) + Eval (3s) = ~30s total

---

**Next Step**: Read [Important Features](08-important-features.md) to understand key capabilities.
