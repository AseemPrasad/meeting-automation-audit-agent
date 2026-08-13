# Learning Curriculum

Structured learning path from beginner to advanced.

---

## Beginner: System Overview

**Goal**: Understand what this system does and basic architecture.

**Time**: 2 hours

### Topics
1. What is this system?
2. How does a user use it?
3. What are the main components?
4. How do they communicate?

### Resources
- Read [Executive Summary](01-executive-summary.md)
- Read [System Mental Model](03-system-mental-model.md)
- Read [Repository Map](02-repository-map.md) - focus on directory structure only

### Hands-On Exercise
1. Run the application locally (follow README)
2. Upload a test audio file
3. Poll for results
4. Inspect the database (sqlite3 jobs.db)

### Assessment Questions
- [ ] What problem does this system solve?
- [ ] How long does processing typically take?
- [ ] What happens if Groq API is down?
- [ ] What is the 202 async pattern?
- [ ] Name the 4 main directories in worker/

---

## Intermediate: Architecture and Data Flow

**Goal**: Understand how the system works internally.

**Time**: 4 hours

### Topics
1. Layered architecture
2. Request lifecycle
3. Database schema
4. Component interactions
5. Error handling

### Resources
- Read [Architecture Overview](04-architecture-overview.md)
- Read [Data Architecture](06-data-architecture.md)
- Read [Runtime Flows](07-runtime-flows.md)
- Read [Component Architecture](05-component-architecture.md) - first 3 sections

### Hands-On Exercises
1. **Trace a request**: Add logging to trace one request from POST /process to database
2. **Database exploration**: 
   - Run `sqlite3 jobs.db`
   - Query: `SELECT * FROM jobs LIMIT 5;`
   - Query: `SELECT COUNT(*) FROM users;`
3. **Circuit breaker**: Temporarily disable Groq, verify fallback to OpenAI
4. **Rate limit**: Make 121 requests in 1 minute, verify 429 response

### Assessment Questions
- [ ] What's the difference between FastAPI and Celery layers?
- [ ] How is tenant scoping implemented?
- [ ] What are the 3 types of failures and how are they handled?
- [ ] Why use Redis instead of database for rate limiting?
- [ ] What indexes exist on the jobs table and why?

---

## Intermediate-Advanced: Design Patterns and Decisions

**Goal**: Understand why architectural decisions were made.

**Time**: 3 hours

### Topics
1. Design patterns in use
2. Architecture decisions
3. Tradeoffs and alternatives
4. Security model

### Resources
- Read [Design Patterns](08-design-patterns.md)
- Read [Architecture Decisions](09-architecture-decisions.md)
- Read [Security Architecture](10-security-architecture.md)

### Hands-On Exercises
1. **Add a new LLM provider**:
   - Create `worker/services/llm/providers/cohere.py`
   - Inherit from `LLMProvider`
   - Implement `query()` method
   - Add to router in `router.py`
   - Write tests
   
2. **Understand multi-tenancy**:
   - Query with wrong tenant_id, verify 404
   - Check JWT payload to see tenant_id
   - Verify rate limit isolation

3. **Security exercise**:
   - Explain password flow (registration to login)
   - Trace JWT creation and validation
   - Identify 3 security layers in the system

### Assessment Questions
- [ ] Name 5 design patterns used in this code
- [ ] What's the Circuit Breaker pattern solving?
- [ ] Why is multi-tenancy baked in from the start?
- [ ] What are the tradeoffs of async architecture?
- [ ] If you wanted to add instant token revocation, how would you do it?

---

## Advanced: Components Deep Dive

**Goal**: Understand each major subsystem in detail.

**Time**: 6 hours

### Topics
1. LLM Service (routing, failover, cost tracking)
2. RAG Pipeline (chunking, indexing, retrieval)
3. Evaluation Pipeline (metrics, judgment, export)
4. Agent Extraction (DAG, state, nodes)
5. Caching (semantic similarity)

### Resources
- Read [Component Architecture](05-component-architecture.md) - complete
- Read [Runtime Flows](07-runtime-flows.md) - Error Handling section

### Hands-On Exercises
1. **LLM Router**:
   - Modify `worker/services/llm/router.py` to log each provider attempt
   - Test with Groq disabled
   - Verify automatic fallback
   - Check cost estimates

2. **Evaluation Pipeline**:
   - Modify `worker/eval/metrics.py` to add a new metric
   - Run evaluation on a sample extraction
   - Check quality score

3. **RAG Pipeline**:
   - Trace through `worker/rag/pipeline.py`
   - Understand chunking strategy (chunk_size=512, overlap=50%)
   - Understand hybrid retrieval (dense + sparse)

4. **Semantic Cache**:
   - Calculate embedding for a transcript
   - Check cache hit/miss
   - Understand cost savings

### Assessment Questions
- [ ] How does the LLM router decide which provider to use?
- [ ] What's the difference between dense and sparse search?
- [ ] What does the reranker do?
- [ ] How are quality scores calculated?
- [ ] What conditions trigger dataset export?

---

## Advanced: Operations and Scaling

**Goal**: Understand production concerns.

**Time**: 4 hours

### Topics
1. Scalability patterns
2. Observability
3. Reliability
4. Performance optimization

### Resources
- Read [Architecture Overview](04-architecture-overview.md) - Scalability section
- Look at `worker/middleware/metrics.py` for observability
- Check `requirements.txt` for OpenTelemetry dependencies

### Hands-On Exercises
1. **Load testing**:
   - Install `locust`
   - Create load test for `/api/v1/transcripts/process`
   - Observe queue backlog
   - Calculate throughput per worker

2. **Monitoring setup**:
   - Export metrics to Prometheus (check telemetry.py)
   - Create dashboard for:
     - Request latency
     - Error rate
     - Queue depth

3. **Scaling analysis**:
   - Calculate: If we have 100 concurrent requests, how many Uvicorn workers needed?
   - Calculate: If Celery processes 10 jobs/min, how long is queue backlog?
   - Calculate: How many Celery workers needed for 1000 jobs/day?

### Assessment Questions
- [ ] How would you scale this system horizontally?
- [ ] What bottlenecks exist?
- [ ] How would you add database replication?
- [ ] What metrics are most important to monitor?
- [ ] How would you handle Celery worker crashes?

---

## Expert: System Design and Redesign

**Goal**: Be able to redesign parts of the system.

**Time**: 8 hours

### Topics
1. Why each component exists
2. Constraints and requirements
3. Alternative architectures
4. Failure modes

### Resources
- Re-read [Architecture Decisions](09-architecture-decisions.md) - deeply
- Read all of [Component Architecture](05-component-architecture.md)
- Study test files in `tests/`

### Hands-On Exercises
1. **Redesign challenge 1: Streaming**
   - Requirement: Stream results as LLM generates them (instead of waiting for completion)
   - Design: How would you change architecture?
   - Considerations: WebSocket? Server-sent events? What changes?

2. **Redesign challenge 2: Per-Tenant Deployment**
   - Requirement: Each tenant gets their own database
   - Design: How would you change code?
   - Considerations: Database migrations? Scaling? Cost?

3. **Redesign challenge 3: Real-Time Collaboration**
   - Requirement: Multiple people can edit extracted items simultaneously
   - Design: How would you implement?
   - Considerations: Conflict resolution? Websockets? State management?

4. **Failure mode analysis**:
   - What happens if Redis crashes?
   - What happens if PostgreSQL is corrupted?
   - What happens if all LLM providers are down?
   - How would you recover?

### Assessment Questions
- [ ] Could this system run on serverless (Lambda)? Why/why not?
- [ ] How would you implement streaming responses?
- [ ] What would breaking up the monolith require?
- [ ] How would you handle geographic distribution?
- [ ] What are the top 3 risks in production?

---

## Expert: Security Deep Dive

**Goal**: Understand security model and threats.

**Time**: 4 hours

### Resources
- Read [Security Architecture](10-security-architecture.md)
- Read all of `worker/core/security.py`
- Study `tests/test_security.py`

### Hands-On Exercises
1. **Penetration test**:
   - Try to access another tenant's jobs
   - Try to forge a JWT token
   - Try to bypass rate limits
   - Document findings

2. **Threat modeling**:
   - Create threat model diagram
   - Identify top 10 risks
   - Propose mitigations
   - Implement 2 mitigations

3. **Compliance audit**:
   - Check for GDPR compliance
   - Check for audit logging
   - Identify gaps
   - Recommend fixes

### Assessment Questions
- [ ] How would you steal someone's data?
- [ ] How would you DoS this system?
- [ ] What's the most critical security gap?
- [ ] How would you improve the threat model?
- [ ] What compliance gaps exist?

---

## Learning Path by Role

### For Backend Engineers
1. Beginner (2h)
2. Intermediate (4h)
3. Design Patterns (3h)
4. Advanced Components (6h)
5. Operations (4h)
→ **Total**: 19 hours → Competent to modify backend

### For Data Scientists (ML)
1. Beginner (2h)
2. Intermediate (4h)
3. Design Patterns - skip (1h less)
4. Advanced Components - focus on Eval/RAG (3h)
5. Expert System Design - focus on LLM/eval (2h)
→ **Total**: 12 hours → Can improve ML components

### For DevOps Engineers
1. Beginner (2h)
2. Intermediate - focus on architecture (2h)
3. Operations (4h)
4. Expert - focus on scaling/reliability (4h)
→ **Total**: 12 hours → Can deploy and scale system

### For Product Managers
1. Beginner (2h)
2. System Mental Model (1h)
3. Architecture Overview - light read (2h)
4. Design Decisions - light read (2h)
→ **Total**: 7 hours → Understand tradeoffs and roadmap

---

## Learning Checklist

### Week 1
- [ ] Read Executive Summary
- [ ] Read System Mental Model
- [ ] Run the application locally
- [ ] Upload a test file
- [ ] Read Repository Map

### Week 2
- [ ] Read Architecture Overview
- [ ] Read Runtime Flows
- [ ] Trace a request in code
- [ ] Read Design Patterns
- [ ] Read Architecture Decisions

### Week 3
- [ ] Read Component Architecture
- [ ] Read Data Architecture
- [ ] Add a new LLM provider
- [ ] Read Security Architecture
- [ ] Perform penetration test

### Week 4
- [ ] Deep dive on LLM router
- [ ] Deep dive on evaluation
- [ ] Setup monitoring
- [ ] Load test the system
- [ ] Complete redesign exercise

---

## Knowledge Milestones

**Beginner**: Can explain the system to a non-technical person

**Intermediate**: Can fix bugs and add simple features

**Advanced**: Can add complex features and optimize performance

**Expert**: Can redesign subsystems and make architectural decisions

---

## Time Investment Table

| Level | Hours | Skills | Projects |
|-------|-------|--------|----------|
| Beginner | 2 | Overview, basic use | None |
| Intermediate | 6 | Understand flow, basic modification | Add 1 feature |
| Advanced | 13 | Deep knowledge, optimize | Design change |
| Expert | 21 | Redesign capability, thought leader | Rewrite subsystem |

---

**Next Step**: Based on your role and timeline, follow the learning path above. Start with Beginner, then choose your track.
