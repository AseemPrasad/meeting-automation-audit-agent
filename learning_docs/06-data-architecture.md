# Data Architecture

Database design, schemas, and data flow.

---

## Data Model Overview

```
┌──────────────────────────────────────────────────┐
│                 Tenant (Implicit)                │
│  (Scopes all other entities)                     │
└──────────────────┬───────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
    ┌────────┐ ┌──────┐ ┌──────────┐
    │ User   │ │ Job  │ │ Cache    │
    └────────┘ └──────┘ └──────────┘
```

---

## User Table

**File**: `worker/models/user.py`

**Schema**:
```python
class User(Base):
    __tablename__ = "users"
    
    id: UUID4                    # Primary key
    email: str                   # Unique per tenant
    password_hash: str           # bcrypt hash
    tenant_id: UUID4             # Tenant scoping
    role: Literal["admin", "member", "viewer"]
    is_active: bool              # Soft delete
    created_at: datetime
    updated_at: datetime
    
    __table_args__ = (
        UniqueConstraint("email", "tenant_id"),  # Same email in different tenants OK
    )
```

**Keys**:
- Primary Key: `id`
- Index: `(email, tenant_id)` - For login lookups

**Why `email` is not unique globally**: [Observable] Multi-tenancy allows same email in different tenants (alice@acme.com exists in Company A and Company B).

**Why `password_hash` not plain text**: [Observable] Security. Bcrypt with salt.

**Why `is_active` field**: [Observable] Soft deletes. Don't remove records (lose audit trail). Mark inactive instead.

---

## Job Table

**File**: `worker/models/job.py`

**Schema**:
```python
class Job(Base):
    __tablename__ = "jobs"
    
    id: UUID4                                   # Primary key
    tenant_id: UUID4                            # Tenant scoping
    user_id: UUID4                              # Who created this job
    status: Literal["PENDING", "PROCESSING", 
                    "COMPLETED", "FAILED"]      # State machine
    
    # Input
    audio_filename: str                         # For audit
    audio_url: str                              # Where to fetch
    
    # Output
    result_payload: JSON                        # Extraction results
    error: str | None                           # Error message if failed
    quality_score: float | None                 # 0-1 evaluation score
    
    # Metadata
    created_at: datetime
    started_at: datetime | None                 # When processing began
    completed_at: datetime | None               # When finished
    
    __table_args__ = (
        Index("idx_tenant_status", "tenant_id", "status"),
        Index("idx_tenant_created", "tenant_id", "created_at"),
    )
```

**Keys**:
- Primary Key: `id`
- Index: `(tenant_id, status)` - For listing jobs by tenant
- Index: `(tenant_id, created_at)` - For sorting by creation time

**Why `status` is enum**: [Observable] Type-safe. Prevents typos ("COMPLETED" vs "COMPLETE"). State machine validation possible.

**Why `result_payload` is JSON**: [Observable] Flexible schema. Extracted data varies (different # of items). JSON column handles variable structure.

**Why `quality_score` can be NULL**: [Observable] Not computed for all jobs (expensive). Computed on-demand or asynchronously.

**Why `user_id` is stored**: [Observable] Audit trail. Know who uploaded what.

---

## Cache Table

**File**: `worker/models/cache.py`

**Schema**:
```python
class CacheEntry(Base):
    __tablename__ = "cache_entries"
    
    id: UUID4
    text_hash: str                  # SHA256(input_text)
    cached_result: JSON             # Serialized extraction
    
    # Metrics
    cache_hits: int                 # How many times retrieved
    cache_misses: int               # How many times missed
    last_accessed: datetime
    
    # Embeddings
    embedding_vector: VECTOR        # For semantic search
    
    created_at: datetime
    expires_at: datetime            # TTL for old entries
    
    __table_args__ = (
        Index("idx_text_hash", "text_hash"),
        Index("idx_expires", "expires_at"),
    )
```

**Purpose**: Observe cache behavior and manage cache lifecycle.

**Why separate from Redis**: [Observable] Redis is ephemeral (survives restarts but not crashes). Database is durable. Could sync to Redis on startup.

---

## Result Payload Schema

**File**: `worker/schemas/transcript.py`

The `result_payload` JSON field contains:

```json
{
  "action_items": [
    {
      "task": "Ship feature",
      "assignee": "Bob",
      "deadline": "2026-08-15",
      "priority": "high",
      "status": "pending"
    }
  ],
  "decisions": [
    {
      "decision": "Use React for frontend",
      "rationale": "Team preference and existing expertise",
      "impact": "Affects hiring and architecture decisions",
      "owner": "Alice"
    }
  ],
  "sentiment": {
    "overall": 0.75,
    "by_speaker": {
      "Alice": 0.8,
      "Bob": 0.7
    }
  },
  "summary": "Team discussed shipping timeline and tech stack...",
  "metadata": {
    "transcript_length": 1200,
    "processing_time_ms": 35000,
    "model_used": "gpt-4"
  }
}
```

**Validation**: Pydantic ensures structure at insertion time.

```python
class MeetingAnalysisResponse(BaseModel):
    action_items: List[ActionItem]
    decisions: List[KeyDecision]
    sentiment: SentimentAnalysis
    summary: str
```

**[Observable]** Structured schemas make results predictable.

---

## Data Flow: Insert

```
Client uploads audio
    │
    ├─ FastAPI validates JWT (user, tenant_id extracted)
    ├─ Validate file (type, size)
    │
    └─ Create Job record:
        INSERT INTO jobs (
            id=uuid,
            tenant_id='AAA',
            user_id=123,
            status='PENDING',
            audio_filename='meeting.mp3',
            created_at=now()
        )
        │
        └─ Commit transaction (ACID guarantee)
```

**Transaction Isolation**: SQLAlchemy handles. Prevents dirty reads, lost updates.

---

## Data Flow: Update

```
Celery Worker processing job
    │
    ├─ Read current status
    │  SELECT status FROM jobs WHERE id=uuid
    │
    ├─ Check: Already completed?
    │  if status == 'COMPLETED': return  # Idempotent
    │
    ├─ Update to PROCESSING
    │  UPDATE jobs SET status='PROCESSING', started_at=now()
    │
    ├─ Do work (transcribe, extract, evaluate)
    │  (If fails, will retry)
    │
    └─ Update to COMPLETED
        UPDATE jobs SET 
            status='COMPLETED',
            result_payload='{...}',
            quality_score=0.96,
            completed_at=now()
        │
        └─ Commit (now results visible to client polling)
```

**Idempotency**: If same task runs twice, second run exits early (already COMPLETED).

**[Observable]** Status progresses: PENDING → PROCESSING → COMPLETED|FAILED

---

## Data Flow: Query

```
Client polls for results
    │
    ├─ GET /api/v1/jobs/{job_id}
    │  Header: Authorization: Bearer token
    │
    ├─ Extract user context from JWT
    │  tenant_id = 'AAA', user_id = 123
    │
    └─ Query database (tenant-scoped):
        SELECT * FROM jobs 
        WHERE id = {job_id} 
        AND tenant_id = 'AAA'    ← Critical: tenant filter
        
        If found:
            ├─ status == 'PENDING': Return status + ETA
            ├─ status == 'PROCESSING': Return status + progress
            └─ status == 'COMPLETED': Return status + results
        
        If not found:
            └─ Return 404 (either job doesn't exist or belongs to different tenant)
```

**Multi-Tenancy**: [Observable] Every query filters by tenant_id. Prevents data leakage.

---

## Database Initialization

**File**: `worker/core/database.py`

```python
def init_db():
    # Create all tables
    # Idempotent: only creates tables that don't exist
    Base.metadata.create_all(bind=engine)
    
    # Create indexes
    # Idempotent: indexes aren't recreated
```

**Run once on startup**:
```python
# In app.py
@app.on_event("startup")
async def startup():
    init_db()
```

**[Observable]** Idempotent design. Safe to call multiple times.

---

## Session Management

**File**: `worker/core/database.py`

```python
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Objects remain usable after commit
)

def get_db():
    db = SessionLocal()
    try:
        yield db  # Use in route
    finally:
        db.close()  # Always clean up
```

**Pattern**: Context manager pattern. Ensures sessions are closed.

**Usage in route**:
```python
@app.get("/jobs")
async def list_jobs(db: Session = Depends(get_db), user: User = ...):
    jobs = db.query(Job).filter(
        Job.tenant_id == user.tenant_id
    ).all()
    
    # db auto-closed after route returns (dependency cleanup)
    return jobs
```

**[Observable]** Session cleanup is automatic. No resource leaks.

---

## Persistence Layers

### SQLite (Development)
**Default**: `jobs.db` (file-based)

**Characteristics**:
- Single file
- Zero setup
- Good for dev/testing
- Not suitable for production (no concurrent writes)

### PostgreSQL (Production)
**Alternative**: Set `DATABASE_URL=postgresql://...`

**Characteristics**:
- Server-based
- Concurrent access
- Replication, backup, recovery
- Connection pooling
- ACID guarantees

**[Observable]** ORM (SQLAlchemy) abstracts away differences. Code works with both.

---

## Indexing Strategy

### Index 1: Tenant + Status
```sql
CREATE INDEX idx_tenant_status ON jobs(tenant_id, status)
```

**Why**: Common query pattern
```python
# List pending jobs for tenant
SELECT * FROM jobs WHERE tenant_id = 'AAA' AND status = 'PENDING'
```

**Benefit**: Index supports both columns, fast scan.

### Index 2: Tenant + Created Time
```sql
CREATE INDEX idx_tenant_created ON jobs(tenant_id, created_at DESC)
```

**Why**: Sort jobs by creation time
```python
# Recent jobs first
SELECT * FROM jobs WHERE tenant_id = 'AAA' ORDER BY created_at DESC
```

**Benefit**: Avoids sort operation.

### Index 3: Text Hash (Cache)
```sql
CREATE INDEX idx_text_hash ON cache_entries(text_hash)
```

**Why**: Lookup cached results
```python
SELECT * FROM cache_entries WHERE text_hash = sha256(text)
```

**[Observable]** Indexes only on frequently queried fields. Too many indexes slow down writes.

---

## Backup and Recovery

**Not shown in code, but operationally important**:

```
Daily backup:
    └─ pg_dump job
    └─ Store in S3

Recovery procedure:
    └─ If database corrupted:
        ├─ Stop application
        ├─ Restore from last backup
        ├─ Replay job logs (Celery logs)
        └─ Resume processing
```

**[Assumed]** Production setup includes backup strategy. Not visible in this codebase.

---

## Data Retention

**Job Records**:
- Keep indefinitely (audit trail)
- Could implement archival (move old jobs to cold storage)

**Cache Entries**:
- Expire after configured TTL (e.g., 30 days)
- LRU eviction if cache grows too large

**Logs**:
- Aggregated by OpenTelemetry
- Retention depends on logging infrastructure
- Could be weeks to years depending on compliance needs

**[Assumed]** Retention policies configured operationally, not in code.

---

## Data Integrity

### Constraints

**User email is unique per tenant**:
```python
__table_args__ = (
    UniqueConstraint("email", "tenant_id"),
)
```

**Prevents**: Same person registering twice in same tenant.

### Foreign Keys

**Job references User**:
```python
user_id = Column(UUID4, ForeignKey("users.id"))
```

**[Observable]** Would prevent orphaned jobs (if User deleted, Job stays but reference breaks).

**[Note]** Implementation shows FK constraints but may have cascading delete disabled (unclear from code).

### Soft Deletes

**Users can be marked inactive**:
```python
is_active: bool = True

# When deleting:
user.is_active = False
db.commit()

# Queries filter out:
db.query(User).filter(User.is_active == True)
```

**Benefit**: Preserves audit trail. Job history still shows who created what.

---

## Data Validation

### At Database Level
- Types (INT, VARCHAR, JSON)
- Constraints (NOT NULL, UNIQUE)

### At ORM Level (SQLAlchemy)
- Column types enforced
- Relationships validated

### At Application Level (Pydantic)
```python
class MeetingAnalysisResponse(BaseModel):
    action_items: List[ActionItem]  # Must be list
    decisions: List[KeyDecision]     # Must be list
    sentiment: SentimentAnalysis     # Must match schema
    
    # Validation runs on instantiation
    # Prevents invalid data from being stored
```

**[Observable]** Multi-layer validation. Invalid data caught early.

---

## Scalability Considerations

### Read Scaling
```
If queries are slow:
    ├─ Add read replicas (PostgreSQL)
    ├─ Add caching layer (Redis)
    └─ Optimize queries (better indexes)
```

### Write Scaling
```
If writes are slow:
    ├─ Use PostgreSQL connection pooling
    ├─ Partition data (by tenant)
    └─ Archive old data
```

### Data Growth
```
If storage explodes:
    ├─ Archive old jobs (to cold storage)
    ├─ Compress result_payload JSONs
    ├─ Remove embeddings (regenerate on demand)
    └─ Delete old cache entries
```

**[Inferred]** Design is scalable to millions of records with proper indexing and partitioning.

---

**Next Step**: Read [Runtime Flows](07-runtime-flows.md) to see data in motion.
