# Architecture Change Scenarios

Interactive scenarios that force you to reason about the system design. Work through each scenario before revealing the solution.

---

# LEVEL 1: Small Changes

## Scenario 1.1: Add a Priority Field to Action Items

### Requirement

Currently, action items have these fields:
- task (string)
- assignee (string)
- deadline (date, optional)
- priority (enum: high/medium/low)

**New Requirement**: Add a `due_date_time` field (datetime) separate from `deadline` (date only).

The system needs to distinguish between:
- `deadline`: The final date (2026-08-15)
- `due_date_time`: When exactly it's due (2026-08-15 17:00 UTC)

This affects extraction, storage, and API responses.

### Your Task

**STOP HERE.** Don't read further. Answer these questions:

1. **Which components would change?** (List files/classes)
2. **Why** would each component change?
3. **What risks** do you foresee?
4. **How would you test** this change?
5. **What tradeoffs** are you making?

Write your answers before continuing.

---

### Solution

**Components That Change**:

```
1. worker/schemas/transcript.py
   ├─ ActionItem model
   │  └─ Add due_date_time: Optional[datetime]
   │
2. worker/workflows/transcript_workflow.py
   ├─ LLM prompt (instruct to extract due_date_time)
   ├─ Validation (ensure due_date_time <= deadline)
   │
3. worker/models/job.py
   ├─ Job.result_payload (stores new field)
   │  └─ JSON schema expanded
   │
4. database migration
   ├─ No database change needed (stored in JSON)
   │  └─ JSON column is flexible
   │
5. API response schema (implicit)
   ├─ GET /api/v1/jobs/{job_id} returns new field
   │
6. Tests
   ├─ test_structured_output.py
   │  ├─ Validate due_date_time presence
   │  ├─ Validate due_date_time <= deadline
   │  └─ Handle null due_date_time
```

**Why Each Changes**:

| Component | Why |
|-----------|-----|
| Pydantic schema | Defines structure; must add field |
| LLM prompt | Tells LLM to extract new field |
| Validation | Ensures data integrity (due_time <= date) |
| API response | Automatic (schema drives JSON) |
| Tests | Verify new field is extracted correctly |

**Risks**:

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM doesn't extract due_date_time | Field always null | Add to prompt, retrain if needed |
| due_date_time > deadline | Logic error | Validate in Pydantic validator |
| Backward compatibility | Old clients don't expect field | Make field optional (it is) |
| Evaluation pipeline | Quality metrics might fail | No change needed (just new field) |

**Testing Strategy**:

```python
def test_due_date_time_extraction():
    # Test 1: LLM extracts both deadline and due_date_time
    transcript = "Ship by Friday 5pm"
    result = extract(transcript)
    assert result.deadline == date(2026, 8, 15)
    assert result.due_date_time == datetime(2026, 8, 15, 17, 0)
    
    # Test 2: Validation catches due_date_time > deadline
    with pytest.raises(ValidationError):
        ActionItem(
            task="...",
            deadline=date(2026, 8, 15),
            due_date_time=datetime(2026, 8, 16, 9, 0)  # Next day!
        )
    
    # Test 3: Optional field (backward compatibility)
    result = ActionItem(task="...", due_date_time=None)
    assert result.due_date_time is None
```

**Tradeoffs**:

| Decision | Gain | Sacrifice |
|----------|------|-----------|
| Store in JSON (no schema change) | Simple, fast | Less queryable (no index on due_date_time) |
| Make field optional | Backward compatibility | Can't require it (might be missing) |
| Validate in Pydantic | Type-safe, caught early | Extra validation layer |
| Update LLM prompt | LLM knows what to extract | Might not extract for old data |

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **Pydantic drives everything** - Schema is the single source of truth
2. **Flexible JSON storage** - Can add fields without schema migration
3. **LLM quality depends on prompt** - New fields require prompt engineering
4. **Validation is lightweight** - Just Pydantic validators

**If You Got This Right**:
✅ You understood schema-driven architecture
✅ You recognized no database migration needed
✅ You identified LLM prompt as critical
✅ You thought about backward compatibility

---

## Scenario 1.2: Add a New User Role

### Requirement

Currently, users have 3 roles:
- **admin**: Full tenant access
- **member**: Create/view own jobs
- **viewer**: Read-only access

**New Role**: `supervisor` - Can:
- View all tenant's jobs (like admin)
- But CANNOT delete jobs or change settings
- CAN reassign action items to different users

### Your Task

**STOP HERE.** Answer:

1. **Which components change?**
2. **Why** each one?
3. **What risks** do you see?
4. **How would you test?**
5. **What tradeoffs** are you making?

---

### Solution

**Components That Change**:

```
1. worker/models/user.py
   ├─ User.role enum
   │  └─ Add "supervisor" to Literal["admin", "member", "viewer", "supervisor"]
   │
2. worker/core/security.py
   ├─ require_role() decorator
   │  ├─ @require_role("supervisor") means: supervisor or admin
   │  └─ Hierarchy: admin > supervisor > member > viewer
   │
3. worker/api/v1/endpoints/jobs.py
   ├─ GET /jobs endpoint
   │  └─ Filter logic
   │     ├─ admin: all jobs
   │     ├─ supervisor: all jobs
   │     ├─ member: own jobs only
   │     └─ viewer: all jobs (read-only)
   │
4. worker/api/v1/endpoints/ (new? or existing)
   ├─ PATCH /jobs/{job_id}/assignee
   │  └─ Reassign action item
   │     ├─ Requires supervisor+ role
   │     └─ Validate new assignee is in same tenant
   │
5. Tests
   ├─ test_security.py
   │  ├─ Supervisor can view all jobs
   │  ├─ Supervisor cannot delete jobs
   │  ├─ Supervisor can reassign items
   │  └─ Supervisor cannot create settings
```

**Why Each Changes**:

| Component | Why |
|-----------|-----|
| User model | Need to store role in database |
| Security utils | Need role hierarchy logic |
| Jobs endpoint | Query filter depends on role |
| Reassign endpoint | New permission needed |
| Tests | Verify role behaves correctly |

**Key Question**: How does role hierarchy work?

Current approach (inferred):
```python
def require_role(required_role: str):
    async def check(user: User = Depends(get_current_user)):
        # Current: strict equality
        if user.role != required_role:
            raise HTTPException(403)
```

**Problem**: `@require_role("supervisor")` won't let admins through!

**Solution**: Implement hierarchy
```python
ROLE_HIERARCHY = {
    "admin": 4,
    "supervisor": 3,
    "member": 2,
    "viewer": 1
}

def require_role(required_role: str):
    async def check(user: User = Depends(get_current_user)):
        if ROLE_HIERARCHY[user.role] < ROLE_HIERARCHY[required_role]:
            raise HTTPException(403)
```

**Risks**:

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Role hierarchy not enforced | Supervisors get admin perms | Define hierarchy clearly |
| Supervisor can reassign to admin | Privilege escalation | Validate assignee role |
| Duplicate view logic | Hard to maintain | Centralize query filtering |
| Database not updated for existing users | Old admins lose role | Data migration script |

**Testing Strategy**:

```python
def test_supervisor_role():
    # Test 1: Can view all jobs
    supervisor = create_user(role="supervisor")
    tenant_jobs = get_jobs(user=supervisor)
    assert len(tenant_jobs) == all_tenant_jobs_count
    
    # Test 2: Cannot delete jobs
    with pytest.raises(HTTPException):
        delete_job(job_id, user=supervisor)
    
    # Test 3: Can reassign action items
    result = reassign_action_item(
        job_id=job_id,
        item_id=item_id,
        new_assignee="other_user",
        user=supervisor
    )
    assert result.success
    
    # Test 4: Cannot reassign to different tenant
    with pytest.raises(HTTPException):
        reassign_action_item(..., new_assignee="user_from_other_tenant")
    
    # Test 5: Admin can do everything supervisor can
    admin = create_user(role="admin")
    assert can_reassign_item(admin)
```

**Tradeoffs**:

| Decision | Gain | Sacrifice |
|----------|------|-----------|
| Role hierarchy (numeric) | Flexible, scalable | Must maintain order |
| Centralized query filter | DRY, maintainable | Extra abstraction layer |
| Validate reassignment | Security | Extra database query |
| Make new endpoint | RESTful | More API surface |

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **Role checks are thin** - Just @require_role decorator
2. **Query filters handle all access control** - Roles determine what's queried
3. **No current hierarchy** - Would need to add
4. **Security is tied to authorization** - Not just authentication

**If You Got This Right**:
✅ You understood RBAC pattern
✅ You identified role hierarchy gap
✅ You recognized query filtering pattern
✅ You thought about privilege escalation

---

# LEVEL 2: Feature Changes

## Scenario 2.1: Add Meeting Recordings Storage & Retrieval

### Requirement

Currently:
- Audio file uploaded → Stored in S3
- Used for transcription
- No longer accessible to users
- No way to re-transcribe or re-process

**New Feature**: Users should be able to:
1. Access recordings (download, replay)
2. Re-transcribe using different LLM provider
3. Delete recordings (GDPR)
4. See storage usage per tenant

### Your Task

**STOP HERE.** Answer:

1. **Which components would change?**
2. **What new components are needed?**
3. **What risks do you foresee?**
4. **How would you test this?**
5. **What architectural tradeoffs are you making?**
6. **How does this affect multi-tenancy?**

---

### Solution

**New Data Model**:

```python
# worker/models/recording.py
class Recording(Base):
    __tablename__ = "recordings"
    
    id = Column(UUID, primary_key=True)
    tenant_id = Column(UUID, ForeignKey("tenants.id"))  # ← Multi-tenancy!
    job_id = Column(UUID, ForeignKey("jobs.id"))
    
    # Storage
    s3_key = Column(String)  # s3://bucket/tenant_id/recording_id
    s3_url = Column(String)  # Pre-signed URL
    file_size_bytes = Column(Integer)
    mime_type = Column(String)  # audio/mpeg, etc.
    
    # Metadata
    uploaded_at = Column(DateTime)
    expires_at = Column(DateTime)  # GDPR: auto-delete after 90 days
    
    # Access control
    accessible_by = Column(String)  # "admin", "member", "anyone_in_tenant"
    download_count = Column(Integer, default=0)
    
    # Re-processing
    can_reprocess = Column(Boolean, default=True)
    reprocessed_count = Column(Integer, default=0)
```

**Components That Change**:

```
1. Database
   ├─ New recordings table
   │  └─ Indexed by (tenant_id, job_id)
   │
2. S3 storage structure (change)
   ├─ Old: /jobs/{job_id}.mp3
   └─ New: /{tenant_id}/{recording_id}.mp3  (per-tenant path)
   
3. worker/api/v1/endpoints/jobs.py (expand)
   ├─ POST /jobs/{job_id}/reprocess
   │  └─ Re-transcribe with different provider
   └─ GET /jobs/{job_id}/recording/download
      └─ Generate pre-signed S3 URL
   
4. worker/api/v1/endpoints/ (new)
   ├─ recordings.py (new file)
   │  ├─ GET /recordings (list user's recordings)
   │  ├─ GET /recordings/{recording_id}/download
   │  ├─ DELETE /recordings/{recording_id} (GDPR)
   │  └─ GET /usage (storage usage)
   │
5. worker/services/ (new)
   ├─ storage_service.py (new)
   │  ├─ upload_recording(file, tenant_id)
   │  ├─ delete_recording(recording_id, tenant_id)
   │  ├─ get_presigned_url(recording_id, tenant_id)
   │  └─ calculate_tenant_usage(tenant_id)
   │
6. worker/workflows/
   ├─ Add reprocess_transcript task
   │  └─ Re-run transcription with different provider
   │
7. Scheduled job (NEW)
   ├─ Delete expired recordings (GDPR compliance)
   │  └─ Run daily, find expires_at < NOW()
   │
8. Tests
   ├─ test_recording_upload.py
   ├─ test_recording_access.py
   ├─ test_reprocessing.py
   ├─ test_storage_usage.py
   └─ test_gdpr_deletion.py
```

**Key Architectural Decisions**:

### Decision 1: S3 Path Structure

**Option A** (Current): `/jobs/{job_id}.mp3`
```
Problem: If two tenants have same job_id (different databases), collision!
Well, actually no — each tenant has separate job UUIDs
But: Doesn't organize by tenant
```

**Option B** (Recommended): `/{tenant_id}/{recording_id}.mp3`
```
Benefit: Clear tenant isolation in S3
Benefit: Can easily implement per-tenant quotas
Benefit: S3 prefix policies can enforce tenant access
Cost: Migration of existing recordings
```

### Decision 2: Recording Lifecycle

**Option A**: Keep forever
```
Problem: Storage costs grow indefinitely
Problem: GDPR "right to be forgotten" — can't delete
```

**Option B**: Auto-delete after 90 days (GDPR compliant)
```
Benefit: Reduces storage costs
Benefit: Satisfies "right to be forgotten"
Cost: Users can't access old recordings
```

**Option C**: Tiered storage (hot → cold)
```
Benefit: Reduce costs over time
Cost: Complex, added complexity
```

**Recommended**: Option B (GDPR compliance critical)

### Decision 3: Re-processing Workflow

**Option A**: Allow unlimited re-processing
```
Problem: User could re-process same audio 1000x times
Cost: Wastes API budget
```

**Option B**: Limit re-processing (e.g., 5 times per recording)
```
Benefit: Controls costs
Cost: Users might exceed limit
```

**Option C**: Charge for re-processing
```
Benefit: Direct cost recovery
Cost: Requires billing system
```

**Recommended**: Option B (simple, prevents abuse)

---

**Risks**:

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Storage costs explode | $1000s/month for large tenants | Auto-delete (GDPR) + quotas |
| Cross-tenant data leak via S3 | Tenant A downloads Tenant B's file | Tenant-scoped S3 prefixes + pre-signed URLs |
| Re-processing abuse | User hammers API with re-processes | Limit re-processing count |
| Pre-signed URL leaks | URL shared externally | Short expiry (1 hour), log access |
| Orphaned recordings | Job deleted, recording remains | Cascade delete in database |
| GDPR deletion delayed | Auto-delete job runs only daily | Need to support on-demand deletion too |

---

**Testing Strategy**:

```python
def test_recording_upload_and_retrieval():
    # Test 1: Upload creates recording record
    job = create_job(tenant_id="AAA")
    recording = upload_recording(job, file_data)
    assert recording.tenant_id == "AAA"
    assert recording.s3_key == f"AAA/{recording.id}.mp3"
    
    # Test 2: Cross-tenant cannot access
    user_b = create_user(tenant_id="BBB")
    with pytest.raises(HTTPException):
        download_recording(recording.id, user=user_b)
    
    # Test 3: Pre-signed URL expires
    url = get_presigned_url(recording.id)
    # Verify expiration time is 1 hour
    assert "Expires=" in url
    assert extract_expiry(url) < now() + 3600
    
    # Test 4: Re-processing creates new job
    result = reprocess_recording(recording.id, provider="openai")
    assert result.status == "PENDING"
    assert result.provider == "openai"
    
    # Test 5: Limit re-processing
    for i in range(5):
        reprocess_recording(recording.id)
    
    with pytest.raises(HTTPException):
        reprocess_recording(recording.id)  # 6th attempt
    
    # Test 6: GDPR deletion
    delete_recording(recording.id)
    assert get_recording(recording.id) is None
    # Verify S3 deletion too
    assert not s3_object_exists(recording.s3_key)
    
    # Test 7: Storage usage calculation
    create_recording(tenant_id="AAA", size_bytes=100*1024*1024)  # 100 MB
    create_recording(tenant_id="AAA", size_bytes=200*1024*1024)  # 200 MB
    
    usage = get_tenant_storage_usage("AAA")
    assert usage.total_bytes == 300*1024*1024
    assert usage.recording_count == 2
```

---

**Tradeoffs**:

| Decision | Gain | Sacrifice |
|----------|------|-----------|
| Tenant-scoped S3 paths | Security, organization | Migration effort |
| Auto-delete recordings | GDPR compliant, reduces cost | Users lose access |
| Re-processing limit | Cost control | User frustration at limits |
| Pre-signed URLs | Secure, no auth needed | Need to rotate/expire |
| New Recording model | Proper isolation | More tables, more queries |

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **Storage is opaque** - Currently not tracked or managed
2. **Multi-tenancy needs explicit S3 paths** - Just storing job_id is insufficient
3. **GDPR considerations** - Auto-delete adds operational requirements
4. **Re-processing is new workflow** - Celery task can be reused
5. **Pre-signed URLs are security boundary** - Must be carefully managed

**If You Got This Right**:
✅ You identified cross-tenant S3 path collision
✅ You thought about GDPR compliance
✅ You recognized abuse potential (re-processing)
✅ You designed new database models correctly
✅ You considered pre-signed URL security

---

# LEVEL 3: Infrastructure Changes

## Scenario 3.1: Migrate from SQLite to PostgreSQL in Production

### Requirement

Currently:
- Development: SQLite
- Production: Undefined (likely SQLite too)

**New Requirement**: Migrate to PostgreSQL in production.

Constraints:
- Zero downtime (can't shut down service)
- 5 million existing jobs must migrate
- 100 concurrent users must keep working

### Your Task

**STOP HERE.** Answer:

1. **What's the migration strategy?**
2. **How do you handle concurrent writes during migration?**
3. **What breaks if you get this wrong?**
4. **How do you test this?**
5. **What's your rollback plan?**
6. **What architectural changes are needed?**

---

### Solution

**Migration Strategy (Blue-Green)**:

```
Phase 1: Preparation (Before cutover)
├─ Deploy new PostgreSQL instance (prod-pg-1)
├─ Leave SQLite running (prod-sqlite)
├─ Code uses both (dual-write)

Phase 2: Dual-Write (Migration)
├─ Code writes to BOTH SQLite and PostgreSQL
├─ Reads from SQLite (source of truth)
├─ PostgreSQL catches up asynchronously
│  ├─ Transfer existing 5M jobs
│  └─ Write new jobs to both

Phase 3: Validation (hours/days)
├─ Verify row counts match
├─ Verify checksums match
├─ Validate no corruption

Phase 4: Read Cutover
├─ Switch reads from SQLite → PostgreSQL
├─ Writes still go to both
├─ Monitor for errors

Phase 5: Write Cutover
├─ Stop writing to SQLite
├─ Writes go only to PostgreSQL
├─ Keep SQLite as fallback (1 week)

Phase 6: Cleanup
├─ Archive/delete SQLite
└─ Clean up migration code
```

**Implementation**:

```python
# worker/core/database.py (modified)

# Determine which database to use
PRIMARY_DB = os.getenv("PRIMARY_DB", "sqlite")  # sqlite or postgres

def get_db_session():
    if PRIMARY_DB == "sqlite":
        return SQLiteSession()
    elif PRIMARY_DB == "postgres":
        return PostgresSession()

# Dual-write pattern
class DualWriteSession:
    def __init__(self):
        self.sqlite = SQLiteSession()
        self.postgres = PostgresSession()
    
    def add(self, obj):
        self.sqlite.add(obj)
        self.postgres.add(obj)
    
    def commit(self):
        try:
            self.sqlite.commit()
        except Exception as e:
            log.error(f"SQLite commit failed: {e}")
            raise
        
        try:
            self.postgres.commit()
        except Exception as e:
            log.error(f"PostgreSQL commit failed: {e}")
            log_for_reconciliation(e)
            # Don't raise — SQLite succeeded, continue
```

**Handling Concurrent Writes**:

```
Problem: Users keep writing while migration in progress

Solution 1: Two-phase commit
├─ Write to SQLite first (primary)
├─ Write to PostgreSQL second (secondary)
├─ If both succeed: committed
├─ If PostgreSQL fails: log, reconcile later

Solution 2: Async replication
├─ Write to SQLite (immediate)
├─ Queue job to replicate to PostgreSQL
├─ Async worker copies rows
├─ User doesn't wait for PostgreSQL

Recommended: Solution 2 (doesn't block users)
```

**What Breaks If Wrong**:

| Failure Mode | Impact | Evidence |
|--------------|--------|----------|
| Row count mismatch | Some data in SQLite, missing from PostgreSQL | Count(*) differs |
| Checksum mismatch | Data corrupted during migration | Hash differs |
| New job written only to SQLite | Job disappears after cutover | Users see "job not found" |
| PostgreSQL falls behind | Cutover before migration complete | Row counts still different |
| Concurrent write causes deadlock | Users experience 500 errors | Logs show deadlock |

---

**Testing Strategy**:

```python
def test_dual_write_consistency():
    # Test 1: New job written to both databases
    job = create_job(tenant_id="AAA")
    
    assert get_from_sqlite(job.id) is not None
    assert get_from_postgres(job.id) is not None
    assert job.id matches in both databases
    
    # Test 2: Migration copy is accurate
    setup_10k_test_jobs_in_sqlite()
    migrate_jobs_to_postgres()
    
    sqlite_count = count_jobs_in_sqlite()
    postgres_count = count_jobs_in_postgres()
    assert sqlite_count == postgres_count == 10000
    
    # Test 3: Checksums match
    for job_id in all_job_ids:
        sqlite_hash = hash_job_in_sqlite(job_id)
        postgres_hash = hash_job_in_postgres(job_id)
        assert sqlite_hash == postgres_hash
    
    # Test 4: Concurrent writes during migration
    def write_jobs():
        for i in range(100):
            create_job()
    
    migration_thread = Thread(target=migrate_jobs_to_postgres)
    write_thread = Thread(target=write_jobs)
    
    migration_thread.start()
    write_thread.start()
    
    migration_thread.join()
    write_thread.join()
    
    # Verify all jobs in both databases
    assert count_sqlite() == count_postgres()
    
    # Test 5: Read cutover (switch reads)
    # Simulate read cutover
    os.environ["PRIMARY_DB"] = "postgres"
    
    job = query_job(job_id)
    assert job.id == job_id
    # If job not in PostgreSQL: test fails
```

**Rollback Plan**:

```
If cutover goes wrong:

Step 1: Switch reads back to SQLite
  └─ env PRIMARY_DB=sqlite

Step 2: Resume dual-writes
  ├─ New jobs go to both databases
  └─ PostgreSQL isn't used

Step 3: Investigate failure
  ├─ Were checksums wrong?
  ├─ Did some data not migrate?
  └─ Was migration incomplete?

Step 4: Fix and retry
  └─ Restart migration process

Timeline: Rollback takes ~5 minutes (redeploy to switch DB)
```

---

**Architectural Changes**:

| Change | Reason |
|--------|--------|
| Abstracted database backend | Allows switch between SQLite/PostgreSQL |
| Dual-write middleware | Writes to both during migration |
| Env variable for primary DB | Controls which database is used |
| Reconciliation service | Catches missed writes, fixes inconsistencies |
| Monitoring/alerts | Watch for write failures, mismatches |

---

**Risks**:

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Migration incomplete before cutover | Data loss | Verify row counts match before proceeding |
| New jobs missed by migration | Job disappears | Dual-write ensures all new jobs in both |
| PostgreSQL too slow | Read cutover fails | Load test PostgreSQL before cutover |
| Rollback fails | Stuck on PostgreSQL | Keep SQLite running 1 week as fallback |
| Disk space runs out | Migration stalls | Monitor disk usage during migration |

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **Database abstraction is missing** - Code assumes SQLite/PostgreSQL same
2. **Migration requires dual-write pattern** - Complex but necessary for zero-downtime
3. **Verification is critical** - Can't just copy and hope
4. **Rollback must be fast** - Users expect reliability

**If You Got This Right**:
✅ You understood blue-green migration
✅ You recognized dual-write problem
✅ You planned validation/rollback
✅ You identified database abstraction gap

---

# LEVEL 4: Scale

## Scenario 4.1: Handle 100x Traffic (100,000 uploads/day)

### Requirement

Current system handles 1,000 uploads/day.

**New Requirement**: Scale to 100,000 uploads/day (100x).

Same-day deadline. No budget constraints.

### Your Task

**STOP HERE.** Answer:

1. **What bottlenecks will you hit first?**
2. **In what order do they fail?**
3. **What do you upgrade/change/add?**
4. **What's the minimal viable scaling path?**
5. **What architectural changes are permanent vs. temporary?**

---

### Solution

**Bottleneck Analysis (In Order of Failure)**:

```
T=0 minutes: Groq API rate limit
├─ Groq limit: ~100 req/min (assumed)
├─ Demand: 100,000 jobs/day = 69 jobs/min
├─ Status: Need ~70% of Groq's capacity
├─ At 100x: Need 6,900 jobs/min (not possible with single provider)
└─ First Fix: Contact Groq, add OpenAI load-balancing

T=5 minutes: Celery worker throughput
├─ Current: 10 workers, 20 sec per transcription
├─ Throughput: 0.5 jobs/sec = 43,200 jobs/day
├─ Demand: 100,000 jobs/day = 2.3 jobs/sec
├─ Shortfall: Need 46 workers (not 10)
└─ Fix: Add 36 more workers

T=30 minutes: Queue backlog grows
├─ 50,000+ jobs queued
├─ Users wait 4+ hours for results
└─ Fix: Confirm worker scaling working

T=60 minutes: Database connection pool
├─ 50 workers × 20 seconds = 1000 connection-seconds/second
├─ Pool size: 20 connections
├─ Oversubscription: 50x
├─ Workers blocked waiting for connection
└─ Fix: Release connections during LLM calls

T=90 minutes: LLM extraction throughput
├─ Groq/OpenAI rate limited
├─ Queue grows for extraction phase
└─ Fix: Already handled by router

T=120 minutes: Database write throughput
├─ 2.3 jobs/second × 3 UPDATEs/job = 7 writes/sec
├─ PostgreSQL can handle 1000s/sec
├─ Probably OK, but monitor
└─ Fix: Add indexes if needed

T=180 minutes: Redis memory
├─ Queue: 50,000 jobs × 1 KB = 50 MB
├─ Cache: 50,000 transcripts × 2 KB = 100 MB
├─ Total: ~150 MB (out of 8GB)
├─ Status: Fine
└─ Fix: None needed at this scale

T=240 minutes: Network bandwidth
├─ LLM calls: 100K/day × 2 KB average = 200 GB
├─ Database queries: negligible
├─ S3 upload/download: varies
└─ Fix: Monitor, scale network if needed

T=300 minutes: LLM API costs
├─ Current: $200/day
├─ At 100x: $20,000/day
├─ At 1 year: $7.3 million
└─ Fix: Optimize extraction, reduce evaluation for low-value jobs
```

---

**Minimal Viable Scaling Path**:

```
Step 1: Groq Rate Limit (Immediate)
├─ Contact Groq for higher limit
├─ Or distribute across multiple Groq accounts
├─ Or add OpenAI load-balancing (70% Groq, 30% OpenAI)

Step 2: Celery Workers (Next hour)
├─ Spin up 40 more worker instances
├─ Distribute across 5 machines
├─ Load test to confirm throughput

Step 3: Connection Lifecycle (Next hour)
├─ Release DB connections during LLM calls
├─ Code change: db.session() context manager
├─ Deploy and monitor

Step 4: Monitoring (Continuous)
├─ Watch queue depth (should stay < 1000)
├─ Watch worker CPU (should be < 80%)
├─ Watch LLM error rate (should be < 1%)
├─ Set up alerts

Step 5: Cost Optimization (Day 2+)
├─ Enable semantic caching (reduce LLM calls by 20-50%)
├─ Reduce evaluation for routine jobs (save $$ on LLM judge)
└─ Monitor cost per job
```

---

**Permanent vs. Temporary Changes**:

| Change | Permanent? | Reason |
|--------|-----------|--------|
| Add 40 workers | Permanent | Need throughput |
| Load-balance LLM | Permanent | Need Groq capacity |
| Release DB connections | Permanent | Good practice |
| Semantic caching | Permanent | Cost reduction |
| Monitoring/alerts | Permanent | Operational necessity |
| Multi-Groq accounts | Permanent | Groq limited to ~100/min per account |
| PostgreSQL (if SQLite) | Permanent | Can't handle 100x with SQLite |

---

**Architecture Changes**:

```
Addition 1: Load Balancing
├─ Router now probabilistic
├─ 70% Groq, 30% OpenAI by default
└─ Monitors success rate, adjusts dynamically

Addition 2: Worker Autoscaling
├─ Monitor queue depth
├─ If queue > 1000 jobs: spin up 10 more workers
├─ If queue < 100 jobs: spin down 5 workers
└─ Requires orchestration (Kubernetes or EC2 auto-scaling)

Addition 3: Connection Pooling Tuning
├─ Max connections: 50 (was 20)
├─ Min idle connections: 5
├─ Connection timeout: 30 seconds
└─ Requires PostgreSQL config change

Addition 4: Caching Expansion
├─ Enable semantic cache
├─ Increase Redis memory (8GB → 32GB)
├─ Set up Redis Cluster for resilience
└─ Expect 20-50% cache hit rate

Addition 5: Observability
├─ Add metrics for LLM response time by provider
├─ Add metrics for queue depth
├─ Add metrics for worker saturation
├─ Set up alerting on all three
```

---

**Budget Required**:

```
Workers: 40 more instances × $0.25/hr = ~$2,400/month

Database: PostgreSQL with 50GB RAM (was embedded SQLite)
  ├─ RDS: ~$500/month
  └─ Self-hosted: ~$300/month in compute

Redis Cluster: 32GB (was single 8GB)
  ├─ Elasticache: ~$1,000/month
  └─ Self-hosted: ~$500/month

LLM Costs (biggest):
  ├─ Groq: $0.05/call × 100K = $5,000/day = $150K/month
  ├─ OpenAI: $0.10/call × 30K = $3,000/day = $90K/month
  └─ Total LLM: ~$240K/month

Total Ops: ~$244K/month + LLM costs

Cost Optimization (Semantic Caching):
  ├─ Expected 30% reduction in LLM calls
  ├─ Savings: ~$72K/month
  └─ Net: ~$172K/month LLM
```

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **Groq is a bottleneck** - Can't scale beyond its rate limit
2. **Celery workers scale easily** - Just add more instances
3. **Database is not the bottleneck** - PostgreSQL easily handles 7 writes/sec
4. **Cost is the real constraint** - LLM APIs are expensive at scale
5. **Caching becomes critical** - 30% reduction in calls = $72K/month savings

**If You Got This Right**:
✅ You identified Groq rate limit first
✅ You calculated worker shortage (50 needed)
✅ You designed load-balancing approach
✅ You estimated cost impact ($240K/month LLM)
✅ You prioritized cost optimization

---

# LEVEL 5: Failure Scenarios

## Scenario 5.1: Database Becomes Unavailable (2 hours)

### Requirement

PostgreSQL goes down for 2 hours (maintenance, network issue, corruption).

The database is completely unavailable:
- SELECT queries fail
- INSERT/UPDATE queries fail
- Job status cannot be checked
- New jobs cannot be created

### Your Task

**STOP HERE.** Answer:

1. **What happens to users?**
2. **What happens to in-flight jobs?**
3. **How does the system degrade?**
4. **How do you recover?**
5. **What architectural changes prevent this?**

---

### Solution

**Failure Cascade**:

```
T=0: PostgreSQL unavailable

T=0-30 sec: Web layer fails
├─ Route handler tries to get_current_user()
├─ Query database for JWT verification
├─ Database connection timeout (30 sec)
├─ User gets: HTTPException(503, "Service Unavailable")
└─ Result: Users can't authenticate, all requests fail

T=30 sec: Celery workers start failing
├─ Job.query(Job).filter(...).first()
├─ Database connection timeout
├─ Worker thread blocked for 30 seconds
├─ Times out and marks job as FAILED
└─ Result: All in-flight jobs marked FAILED

T=1 min: Queue fills up (no processing possible)
├─ New uploads still enqueue (no DB write for job record)
│  Wait, actually...
│  Job record creation requires DB write
│  So new uploads also fail at route layer
├─ No new jobs can be created
└─ Result: "Service Unavailable" for all uploads

T=2 hours: Database recovers

T=2 hours + 1 sec: System attempts recovery
├─ Web layer: Queries succeed again
├─ But what about in-flight jobs?
└─ Need reconciliation
```

**What Happens to In-Flight Jobs**:

```
Job states when DB goes down:

1. Jobs PENDING in queue
   ├─ Celery has message: process job_id=123
   ├─ Worker tries to run
   ├─ Queries database: SELECT job
   ├─ Timeout, marks as FAILED
   └─ State: Lost (message still in Redis, but job marked FAILED in DB)

2. Jobs in PROCESSING state
   ├─ Worker started Groq transcription
   ├─ Groq API call takes 20 seconds (independent of DB)
   ├─ Worker waits for result
   ├─ DB query for status UPDATE times out
   ├─ Worker error, job stays PROCESSING
   └─ State: Incomplete (transcription succeeded, but not stored)

3. Jobs waiting for extraction
   ├─ Transcript available
   ├─ Worker tries to load from DB
   ├─ Timeout, worker exits
   └─ State: Lost (transcript in Redis, not persisted)
```

**User Experience**:

```
During 2-hour outage:

1. User uploads meeting
   ├─ Request: POST /api/v1/transcripts/process
   ├─ Route tries to create Job record (DB write)
   ├─ Times out
   └─ User gets: "Service temporarily unavailable"

2. User who uploaded before outage
   ├─ Polling: GET /api/v1/jobs/{job_id}
   ├─ Route tries to query job
   ├─ Times out
   └─ User gets: "Service temporarily unavailable"

Result: Users see "Service Down" for all operations

After recovery:

3. Incomplete jobs may need re-processing
   ├─ Some jobs marked FAILED incorrectly
   ├─ Some jobs lost (Groq called, but result not stored)
   └─ Need manual reconciliation or re-run
```

---

**Recovery Process**:

```
Step 1: Database back online
├─ PostgreSQL responds to queries
├─ Verify integrity: run FSCK or PRAGMA integrity_check

Step 2: Identify orphaned state
├─ Query: Jobs in PROCESSING > 2 hours old
├─ These are likely incomplete
├─ Manually check or re-run

Step 3: Manual intervention (likely)
├─ Email affected users: "We experienced an outage..."
├─ Offer: "Re-upload your meeting, we'll prioritize it"
└─ Expected: Some users already gave up

Step 4: Resume processing
├─ Celery workers resume
├─ Process queued jobs
├─ Retry any FAILED jobs

Timeline: 2 hours down + 1 hour recovery = 3 hours total impact
```

---

**Architectural Changes to Prevent**:

### Option A: Database Replica (High Availability)

```
Current: Single PostgreSQL instance
New: Primary + Standby (read replica)

Benefits:
├─ If primary fails, fail over to standby
├─ Read queries can go to replica (reduce load)
└─ 99.9% uptime possible

Cost: 2x database cost

Setup:
├─ AWS RDS Multi-AZ: Automatic failover
├─ Manual: PostgreSQL Streaming Replication
└─ Time to failover: 30-60 seconds
```

### Option B: Cache As Fallback

```
Current: No read-cache

New: Redis cache for:
├─ User records (TTL: 1 hour)
├─ Job records (TTL: 5 minutes)
├─ Tenant config (TTL: 1 hour)

Benefits:
├─ If DB unavailable, read from cache
├─ Graceful degradation (show stale data)
└─ Users can still use system

Cost: Small (Redis memory)

Implementation:
├─ @cache_with_ttl decorator
├─ If DB query fails, try cache
├─ If no cache, show cached data or error
```

### Option C: Async Job Persistence

```
Current: Sync writes to database

New: Queue writes to Redis, flush async

Pattern:
├─ App writes to Redis queue
├─ Async worker reads from queue
├─ Worker writes to database
└─ If DB down, queue fills up (recovers when DB back)

Benefits:
├─ DB down doesn't block user requests
├─ Recovers automatically when DB back
└─ Decouples write speed from DB availability

Cost: Small (Redis memory, async worker)

Risk:
├─ Data loss if Redis crashes too
├─ Need both DB + Redis for durability
```

---

**Recommended Approach: Hybrid**

```
Short term (1-2 weeks):
├─ Enable read cache (Option B)
├─ Gracefully serve stale data if DB unavailable
└─ Users see "Using cached data" message

Medium term (1 month):
├─ Deploy RDS Multi-AZ (Option A)
├─ Automatic failover to standby
└─ 99.9% uptime SLA

Long term (2+ months):
├─ Add async persistence (Option C)
├─ Decouple DB writes from request path
└─ True resilience
```

---

**Cost Analysis**:

| Solution | Cost | Uptime | Recovery Time |
|----------|------|--------|----------------|
| No redundancy (current) | $500/mo | 95% | Manual (hours) |
| Read replica + cache | $1000/mo | 99% | 30-60 sec failover |
| Async persistence | $800/mo | 99.5% | Automatic (seconds) |
| All three (best) | $1500/mo | 99.99% | Automatic (seconds) |

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **No high availability** - Single point of failure
2. **Synchronous writes block** - If DB slow/down, users blocked
3. **No read caching** - Can't serve stale data gracefully
4. **No persistence resilience** - Complete outage if DB down

**If You Got This Right**:
✅ You understood failure cascade
✅ You identified user experience impact
✅ You designed recovery procedure
✅ You proposed HA solutions (replica, cache, async)

---

# LEVEL 6: Architectural Redesign

## Scenario 6.1: Event-Driven Architecture

### Requirement

Current architecture:
- Request → Synchronous processing → Response
- State stored only in database
- No audit trail of what happened

**New Requirement**: Redesign to event-driven:
- Every state change emits an event
- Events stored immutably
- Services subscribe to events
- Audit trail is free

Examples of events:
- `TranscriptUploaded` (file_id, tenant_id, timestamp)
- `TranscriptionStarted` (job_id, provider="groq")
- `TranscriptionCompleted` (job_id, transcript_text)
- `ExtractionStarted` (job_id, extraction_provider)
- `ExtractionCompleted` (job_id, results)
- `EvaluationCompleted` (job_id, quality_score)
- `JobFailed` (job_id, error_message, error_stage)

### Your Task

**STOP HERE.** Answer:

1. **How would you structure events?**
2. **What's the event store? (Database? Kafka?)**
3. **How do services react to events?**
4. **What about state consistency?**
5. **How do you handle event replay?**
6. **What breaks? (Timing, causality, ordering)**
7. **Is this worth the complexity?**

---

### Solution

**Event Store Design**:

```python
# worker/models/event.py

class Event(Base):
    __tablename__ = "events"
    
    id = Column(UUID, primary_key=True)
    tenant_id = Column(UUID, ForeignKey("tenants.id"))
    
    # Event identity
    event_type = Column(String)  # "transcription.started", "extraction.completed"
    event_version = Column(Integer, default=1)  # Schema versioning
    
    # Immutable payload
    data = Column(JSON)  # {job_id, transcript, ...}
    
    # Causality
    aggregate_id = Column(UUID)  # The job this event belongs to
    sequence = Column(Integer)  # Order within aggregate (1, 2, 3...)
    
    # Metadata
    timestamp = Column(DateTime, default=now)
    produced_by = Column(String)  # "transcription_worker", "api_gateway"
    
    # Indexes
    __table_args__ = (
        Index("idx_tenant_type_time", "tenant_id", "event_type", "timestamp"),
        Index("idx_aggregate_sequence", "aggregate_id", "sequence"),
    )
```

**Event Flow Architecture**:

```
Event-Driven Pipeline:

1. Event Emission (Source)
   └─ When something happens, emit event
   
   Example: Groq transcription completes
   └─ Emit: TranscriptionCompleted(job_id=123, text="...")
   └─ Store: INSERT INTO events (event_type, data, aggregate_id)

2. Event Storage (Event Store)
   └─ PostgreSQL events table
   └─ Immutable append-only log
   └─ Can replay by reading all events for an aggregate_id

3. Event Subscribers (Services)
   └─ Different services react to events
   
   Examples:
   ├─ On TranscriptionCompleted
   │  └─ Extraction Service: Start extraction
   │
   ├─ On ExtractionCompleted
   │  └─ Evaluation Service: Assess quality
   │
   ├─ On AnyEventCompleted
   │  └─ Audit Service: Log for compliance
   │
   └─ On JobFailed
      └─ Notification Service: Email user

4. Event Handlers (Async)
   └─ Celery workers listen to event stream
   └─ Process events asynchronously
   └─ Emit new events when complete
```

**State Rebuild (Event Sourcing)**:

```python
# Instead of storing state, rebuild from events:

class JobProjection:
    """Rebuild job state from events"""
    
    @staticmethod
    def from_events(job_id: str):
        events = get_events_for_aggregate(job_id)
        
        state = {
            "job_id": job_id,
            "status": "created",
            "transcript": None,
            "extraction": None,
            "quality_score": None
        }
        
        for event in events:
            if event.type == "TranscriptionStarted":
                state["status"] = "transcribing"
            elif event.type == "TranscriptionCompleted":
                state["status"] = "transcribed"
                state["transcript"] = event.data["transcript"]
            elif event.type == "ExtractionStarted":
                state["status"] = "extracting"
            elif event.type == "ExtractionCompleted":
                state["status"] = "extracted"
                state["extraction"] = event.data["results"]
            elif event.type == "EvaluationCompleted":
                state["status"] = "completed"
                state["quality_score"] = event.data["score"]
            elif event.type == "JobFailed":
                state["status"] = "failed"
                state["error"] = event.data["error"]
        
        return state
```

**Event Handlers**:

```python
# worker/handlers/event_handlers.py

class EventHandlers:
    
    @staticmethod
    def on_transcription_completed(event: TranscriptionCompleted):
        """React to transcription completion"""
        job_id = event.data["job_id"]
        transcript = event.data["transcript"]
        
        # Start extraction (emit new event)
        extraction_service.start_extraction(job_id, transcript)
        
        # Emit event
        emit_event(ExtractionStarted(job_id=job_id))
    
    @staticmethod
    def on_extraction_completed(event: ExtractionCompleted):
        """React to extraction completion"""
        job_id = event.data["job_id"]
        results = event.data["results"]
        
        # Start evaluation
        eval_service.evaluate(job_id, results)
        
        # Emit event
        emit_event(EvaluationStarted(job_id=job_id))
    
    @staticmethod
    def on_any_event(event: Event):
        """Audit trail (listens to ALL events)"""
        audit_log.insert({
            "tenant_id": event.tenant_id,
            "event_type": event.event_type,
            "aggregate_id": event.aggregate_id,
            "timestamp": event.timestamp
        })
```

**Event Subscription (Polling or Queue)**:

```python
# Option 1: Polling (Simple)
while True:
    new_events = db.query(Event).filter(
        Event.processed == False
    ).order_by(Event.timestamp).limit(100)
    
    for event in new_events:
        handler = get_handler(event.event_type)
        handler.handle(event)
        event.processed = True
        db.commit()

# Option 2: Message Queue (Kafka, RabbitMQ)
kafka.subscribe("events")
while True:
    event = kafka.get_message()
    handler = get_handler(event.event_type)
    handler.handle(event)
```

---

**State Consistency Issues**:

### Issue 1: Stale Reads

```
Problem: User queries database while projection rebuilding

Timeline:
├─ T=0: TranscriptionCompleted event emitted
├─ T=0.1: Handler starts extraction
├─ T=0.2: User requests: GET /jobs/{job_id}
├─ T=0.3: API reads from Job table (OLD data)
├─ T=0.5: ExtractionCompleted event processed, state updated
└─ Result: User sees stale status
```

**Solution**: Read from projection/cache, not base table
```python
# Don't query Job table
# Instead, rebuild state from events
state = JobProjection.from_events(job_id)
return state
```

### Issue 2: Ordering Guarantees

```
Problem: Events might process out of order

Event 1: TranscriptionCompleted
Event 2: ExtractionStarted

If Event 2 processes before Event 1:
└─ Extraction handler has no transcript yet (error!)

Solution: Enforce ordering by aggregate
├─ Store sequence number per aggregate
├─ Process only in sequence order
└─ Handler waits for previous event to complete
```

### Issue 3: Duplicate Events

```
Problem: Same event might emit twice

Scenario:
├─ Handler processes event
├─ Marks event as processed
├─ Database transaction fails
├─ Event re-processed
└─ Duplicate handling

Solution: Idempotent handlers
├─ If event already handled, skip
├─ Use event_id for deduplication
├─ Handler must be idempotent
```

---

**Tradeoffs**:

| Aspect | Event-Driven | Monolithic |
|--------|--------------|-----------|
| **Complexity** | HIGH | LOW |
| **Auditability** | FREE (events) | Expensive (logs) |
| **Debugging** | Hard (distributed) | Easy (single flow) |
| **Extensibility** | Easy (add subscriber) | Hard (modify flow) |
| **Data Consistency** | Eventually consistent | Strongly consistent |
| **Operational Burden** | Message queue, event store | Database only |
| **Performance** | Potentially faster (parallel) | Straightforward |
| **Event Replay** | Natural (read all events) | Impossible |

---

**Is It Worth It?**:

**Yes if**:
- Audit trail is important (compliance, debugging)
- Future requirements unknown (easy to extend)
- Multiple services will consume events
- Event replay is valuable

**No if**:
- Simple CRUD application
- No audit requirements
- Single monolithic flow
- Team too small to manage event system

**Current project**: Maybe? Depends on:
- Is audit trail important to customers?
- Will other teams need event access?
- Is reliability worth added complexity?

---

### Comparison to Existing Architecture

**What This Reveals**:

1. **Current: State-based** - Stores state in database
2. **Event-driven: Event-based** - Stores events, rebuilds state
3. **Current: Procedural** - Step 1 → Step 2 → Step 3
4. **Event-driven: Reactive** - Services react to events

**Migration Path**:

```
Phase 1: Add events table, emit events (parallel to existing flow)
Phase 2: Add subscribers, handle events alongside existing code
Phase 3: Gradually move logic from procedures to subscribers
Phase 4: Remove old procedures (months later)
Phase 5: Full event-sourcing for state rebuild
```

**If You Got This Right**:
✅ You understood event sourcing
✅ You identified state consistency issues
✅ You designed event handlers
✅ You recognized replay capability
✅ You knew this adds operational complexity

---

# Conclusion

**Scenarios 1-6 Test**:

1. **Level 1**: Can you add a field? (Understand schema-driven design)
2. **Level 2**: Can you add a feature? (Understand roles + permissions)
3. **Level 3**: Can you migrate databases? (Understand zero-downtime patterns)
4. **Level 4**: Can you scale 100x? (Identify bottlenecks in order)
5. **Level 5**: Can you handle outages? (Design resilience)
6. **Level 6**: Can you redesign? (Understand alternative architectures)

---

**How to Use These Scenarios**:

1. Pick a scenario
2. Answer all 6 questions BEFORE reading the solution
3. Compare your answer to the solution
4. Identify gaps in your thinking
5. Learn why certain choices were made

**Expected outcomes**:
- Understand tradeoff reasoning
- Learn to identify bottlenecks
- Practice architectural thinking
- Build intuition for system design

