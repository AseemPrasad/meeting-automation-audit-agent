# Design Patterns

Software engineering patterns used throughout the system.

---

## 1. Repository Pattern

**Definition**: Abstract data access logic behind a uniform interface.

**Implementation**: [Implicit via SQLAlchemy ORM]

```python
# Pattern: ORM replaces explicit repository
job = db.query(Job).filter(Job.id == job_id).first()

# vs. explicit Repository pattern:
class JobRepository:
    def find_by_id(self, job_id):
        ...

# This codebase uses SQLAlchemy ORM as repository
```

**Where**: `worker/core/database.py` (SessionLocal provides data access)

**Benefits**:
- Centralized database logic
- Easy to test (mock Session)
- Decouples business logic from database implementation

**Tradeoff**: SQLAlchemy is less explicit than a custom Repository class. More implicit magic.

---

## 2. Strategy Pattern

**Definition**: Define a family of algorithms, encapsulate each, and make them interchangeable.

**Implementation**: [LLM Providers]

```python
# Strategy interface
class LLMProvider(ABC):
    async def query(self, prompt: str) -> str: ...

# Concrete strategies
class GroqProvider(LLMProvider):
    async def query(self, prompt):
        return await self.client.chat.completions.create(...)

class OpenAIProvider(LLMProvider):
    async def query(self, prompt):
        return await self.client.chat.completions.create(...)

# Context selects strategy at runtime
router = LLMRouter(providers=[Groq, OpenAI, Anthropic])
result = await router.query(prompt)
```

**Where**: `worker/services/llm/`

**Benefits**:
- Easy to add new providers (implement interface)
- Runtime selection (can swap providers)
- Testable in isolation

**Tradeoff**: Abstraction overhead for slightly different APIs.

---

## 3. Circuit Breaker Pattern

**Definition**: Prevent cascading failures by failing fast when service is down.

**Implementation**: [LLM Circuit Breaker]

```python
class CircuitBreaker:
    def __init__(self, threshold=3, timeout=60):
        self.state = "CLOSED"  # Normal
        self.failure_count = 0
        self.threshold = threshold
        self.timeout = timeout
    
    async def call(self, func):
        if self.state == "OPEN":
            if time.time() - self.open_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpen()
        
        try:
            result = await func()
            self.on_success()
            return result
        except Exception:
            self.on_failure()
            raise
    
    def on_success(self):
        self.state = "CLOSED"
        self.failure_count = 0
    
    def on_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.state = "OPEN"
            self.open_time = time.time()
```

**Where**: `worker/services/llm/circuit_breaker.py`

**States**:
```
CLOSED ──[3 failures]──> OPEN ──[60 sec timeout]──> HALF_OPEN ──[success]──> CLOSED
                                                        │
                                                        └──[failure]──> OPEN
```

**Benefits**:
- Prevents thundering herd (stop hammering failed service)
- Faster failure detection
- Automatic recovery

**Evidence**: [Observable] Implemented in code, configured via environment variables.

---

## 4. Chain of Responsibility Pattern

**Definition**: Pass request through a chain of handlers. Each handler decides whether to process or pass to next.

**Implementation**: [LLM Router Failover]

```python
class LLMRouter:
    def __init__(self, providers: List[LLMProvider]):
        self.providers = providers  # Chain of handlers
    
    async def query(self, prompt: str) -> str:
        for provider in self.providers:  # Chain iteration
            if provider.circuit.is_open():
                continue  # Skip to next
            
            try:
                return await provider.query(prompt)  # Handler processes
            except Exception:
                continue  # Pass to next handler
        
        raise AllProvidersFailedError()  # End of chain
```

**Where**: `worker/services/llm/router.py`

**Benefits**:
- Simple to understand
- Easy to add handlers (new providers)
- Flexible failure handling

---

## 5. Dependency Injection Pattern

**Definition**: Provide objects with their dependencies rather than having them create dependencies.

**Implementation**: [FastAPI Dependencies]

```python
# Dependency
async def get_current_user(token: str = Header(...)) -> User:
    payload = jwt.decode(token, SECRET_KEY)
    user = db.query(User).filter(User.id == payload["sub"]).first()
    return user

# Injected into route
@app.get("/jobs")
async def list_jobs(user: User = Depends(get_current_user)):
    # user is automatically provided
    return db.query(Job).filter(Job.user_id == user.id).all()
```

**Where**: `worker/api/v1/endpoints/`, `worker/core/security.py`

**Benefits**:
- Decouples route from authentication logic
- Reusable across many routes
- Testable (can mock dependency)

**Tradeoff**: Requires understanding of dependency systems. More implicit than explicit parameters.

---

## 6. Adapter Pattern

**Definition**: Convert interface of one class to interface expected by clients.

**Implementation**: [LLM Provider Adapters]

```python
# Adapter: Convert Groq API to LLMProvider interface
class GroqAdapter(LLMProvider):
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    async def query(self, prompt: str) -> str:
        # Groq API: messages.create()
        response = await self.client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}]
        )
        # Adapter: Convert to expected interface
        return response.choices[0].message.content
```

**Where**: `worker/services/llm/providers/`

**Benefits**:
- Hides provider-specific API details
- Uniform interface for all providers
- Easy to add new providers

---

## 7. Decorator Pattern

**Definition**: Attach additional responsibilities to object dynamically.

**Implementation**: [RBAC Decorator]

```python
def require_role(required_role: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            user = get_current_user()
            if user.role != required_role:
                raise HTTPException(403, "Insufficient permissions")
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage
@app.delete("/jobs/{job_id}")
@require_role("admin")
async def delete_job(job_id: str):
    ...
```

**Where**: `worker/core/security.py`

**Benefits**:
- Cross-cutting concerns (auth, logging) applied uniformly
- Keeps route code clean
- Reusable

---

## 8. State Machine Pattern

**Definition**: Object behavior varies based on state. Transitions between states.

**Implementation**: [Job Status]

```python
# States
PENDING → PROCESSING → COMPLETED
                    ├──→ FAILED
                    └──→ CANCELLED

# Transitions
job.status = "PENDING"      # Initial

job.status = "PROCESSING"   # Start processing
if error:
    job.status = "FAILED"   # Error occurred
else:
    job.status = "COMPLETED"  # Success

# Invariant: Cannot go backwards
# (No going from COMPLETED → PROCESSING)
```

**Where**: `worker/models/job.py`

**Benefits**:
- Clear state transitions
- Prevents invalid states
- Self-documenting

**Why Enum**: [Observable] Prevents typos ("COMPLETE" vs "COMPLETED"). Type-safe.

---

## 9. Template Method Pattern

**Definition**: Define algorithm skeleton in base class, let subclasses override specific steps.

**Implementation**: [Celery Task]

```python
@celery_app.task(bind=True, max_retries=3)
def process_transcript(self, job_id: str):
    try:
        # Step 1: Get job
        job = get_job(job_id)
        
        # Step 2: Pre-process
        transcript = transcribe(job)
        
        # Step 3: Process
        extraction = extract(transcript)
        
        # Step 4: Post-process
        evaluate(extraction)
        
        # Step 5: Persist
        save(job, extraction)
        
    except Exception as exc:
        # Retry logic
        raise self.retry(exc=exc, countdown=60)
```

**Where**: `worker/workflows/transcript_workflow.py`

**Benefits**:
- Clear algorithm structure
- Reusable retry logic
- Easy to modify individual steps

---

## 10. Observer Pattern

**Definition**: Define one-to-many dependency. When one object changes state, dependents are notified.

**Implementation**: [Implicit via Polling]

```
Job status changes in database
    ↓
Client polls /jobs/{job_id}
    ↓
Detects status change
    ↓
Updates UI

# Not explicit observer pattern, but same effect
```

**Alternative**: [OpenTelemetry Hooks]

```python
# When a request completes:
# OpenTelemetry observer records metrics

@app.get("/jobs")
async def list_jobs():
    # Implicit: Instrumentation records latency, error rates
    ...
```

**[Inferred]** Used implicitly for observability (metrics, logging).

---

## 11. Singleton Pattern

**Definition**: Ensure a class has only one instance and provide global access.

**Implementation**: [Service Singletons]

```python
# Database session factory (singleton)
SessionLocal = sessionmaker(bind=engine)

# Router singleton (module-level)
llm_router = LLMRouter([Groq(...), OpenAI(...), ...])

# Used everywhere
async def extract(transcript):
    return await llm_router.query(prompt)
```

**Where**: `worker/core/database.py`, `worker/services/llm/router.py`

**Benefits**:
- Shared state (all requests use same connection pool)
- Reduced memory usage
- Centralized configuration

**Tradeoff**: Global state. Harder to test (must reset between tests).

---

## 12. Pipeline Pattern

**Definition**: Pass data through a series of processing stages.

**Implementation**: [Transcript Processing]

```
Raw Audio
    ↓
[Transcriber] → Transcript
    ↓
[Cleaner] → Cleaned Transcript
    ↓
[Extractor] → Extracted Items
    ↓
[Auditor] → Validated Items
    ↓
[Inspector] → Scored Items
    ↓
[Exporter] → Persisted Results
```

**Where**: `worker/workflows/transcript_workflow.py`, `worker/agents/graph.py`

**Benefits**:
- Clear data flow
- Easy to debug (inspect at each stage)
- Easy to add/remove stages
- Parallelizable stages

---

## 13. Factory Pattern

**Definition**: Create objects without specifying exact classes.

**Implementation**: [Implicit via ORM]

```python
# Factory: SQLAlchemy creates User objects from database rows
users = db.query(User).all()
# Returns: List[User] (objects created from rows)

# vs. explicit factory:
user_factory = UserFactory()
user = user_factory.create_from_dict({"id": ..., "email": ...})
```

**Where**: Throughout `worker/models/`

**Benefits**:
- Decouples object creation from usage
- Can change creation logic centrally

---

## 14. Event-Driven Architecture (Implicit)

**Definition**: Components communicate via events.

**Implementation**: [Celery Task Enqueue]

```
Route sends event: "process_transcript"
    ↓
Event enqueued in Redis
    ↓
Worker picks up event
    ↓
Worker processes
    ↓
Worker stores result (implicit event: "job_completed")
    ↓
Client polls for change
```

**[Implicit]** Not explicit event system, but async messaging via Celery.

**Benefits**:
- Decoupled components
- Scalable (many workers)
- Resilient (queue persists)

---

## Summary Table

| Pattern | Where | Purpose | Benefit |
|---------|-------|---------|---------|
| Repository | ORM | Abstract data access | Testable |
| Strategy | LLM Providers | Multiple algorithms | Pluggable |
| Circuit Breaker | LLM Router | Fault tolerance | Fail fast |
| Chain of Responsibility | LLM Router | Sequential handlers | Flexible |
| Dependency Injection | FastAPI routes | Provide dependencies | Decoupled |
| Adapter | LLM providers | Convert interfaces | Uniform API |
| Decorator | Auth, logging | Cross-cutting concerns | Reusable |
| State Machine | Job status | State transitions | Safe |
| Template Method | Celery tasks | Algorithm skeleton | Reusable |
| Observer | Observability | Change notification | Visibility |
| Singleton | Services | Single instance | Shared state |
| Pipeline | Workflow | Sequential processing | Composable |
| Factory | ORM | Object creation | Flexible |

---

**Key Insight**: [Observable] This codebase uses well-established patterns. Not ad-hoc design.

---

**Next Step**: Read [Architecture Decisions](09-architecture-decisions.md) to understand why each major choice was made.
