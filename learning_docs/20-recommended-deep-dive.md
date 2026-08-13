# Recommended Deep Dive Order

Structured reading path based on your role and goals.

---

## Quick Path (For Busy People)

**Total Time**: 3 hours  
**Goal**: Understand the system

**Reading Order**:
1. [Executive Summary](01-executive-summary.md) - 15 min
2. [System Mental Model](03-system-mental-model.md) - 45 min
3. [Architecture Overview](04-architecture-overview.md) - 45 min
4. [Runtime Flows](07-runtime-flows.md) - "Flow 2" section only - 30 min

**Outcome**: Can explain the system to someone else.

---

## Standard Path (For Engineers)

**Total Time**: 8 hours  
**Goal**: Understand and modify the system

**Reading Order**:
1. [Executive Summary](01-executive-summary.md) - 15 min
2. [Repository Map](02-repository-map.md) - 30 min
3. [System Mental Model](03-system-mental-model.md) - 45 min
4. [Architecture Overview](04-architecture-overview.md) - 60 min
5. [Component Architecture](05-component-architecture.md) - 90 min
6. [Data Architecture](06-data-architecture.md) - 60 min
7. [Runtime Flows](07-runtime-flows.md) - 60 min
8. [Design Patterns](08-design-patterns.md) - 60 min
9. [Architecture Decisions](09-architecture-decisions.md) - 60 min

**Hands-On**:
- Run application locally (30 min)
- Add one feature (2 hours)

**Outcome**: Can modify any part of the codebase confidently.

---

## Expert Path (For Architects)

**Total Time**: 16 hours  
**Goal**: Understand trade-offs and design system

**Reading Order**:
1. [Executive Summary](01-executive-summary.md) - 15 min
2. [System Mental Model](03-system-mental-model.md) - 45 min
3. [Architecture Overview](04-architecture-overview.md) - 60 min
4. [Component Architecture](05-component-architecture.md) - 90 min
5. [Data Architecture](06-data-architecture.md) - 60 min
6. [Runtime Flows](07-runtime-flows.md) - 90 min
7. [Design Patterns](08-design-patterns.md) - 60 min
8. [Architecture Decisions](09-architecture-decisions.md) - 90 min
9. [Security Architecture](10-security-architecture.md) - 60 min
10. [Learning Curriculum](18-learning-curriculum.md) - Expert section - 60 min
11. [Knowledge Gaps](19-knowledge-gaps.md) - 60 min

**Deep Code Study**:
- Study `worker/services/llm/router.py` (circuit breaker, failover) - 90 min
- Study `worker/eval/pipeline.py` (evaluation orchestration) - 60 min
- Study `worker/workflows/transcript_workflow.py` (main orchestration) - 60 min

**Outcome**: Can redesign subsystems and make architectural decisions.

---

## Role-Based Paths

### Backend Engineer

**Goal**: Contribute to backend features  
**Time**: 10 hours

1. [Executive Summary](01-executive-summary.md)
2. [Repository Map](02-repository-map.md)
3. [System Mental Model](03-system-mental-model.md)
4. [Architecture Overview](04-architecture-overview.md)
5. [Component Architecture](05-component-architecture.md) - Complete
6. [Runtime Flows](07-runtime-flows.md) - Complete
7. [Design Patterns](08-design-patterns.md)
8. [Architecture Decisions](09-architecture-decisions.md) - Focus on async, Celery, LLM sections

**Hands-On**: Add a new LLM provider or improve extraction logic

---

### Data Scientist / ML Engineer

**Goal**: Improve model quality and metrics  
**Time**: 8 hours

1. [Executive Summary](01-executive-summary.md)
2. [System Mental Model](03-system-mental-model.md) - Focus on overall flow
3. [Architecture Overview](04-architecture-overview.md)
4. [Component Architecture](05-component-architecture.md) - Focus on "Evaluation Architecture", "RAG Architecture", "LLM Service"
5. [Runtime Flows](07-runtime-flows.md) - Focus on extraction and evaluation steps
6. [Architecture Decisions](09-architecture-decisions.md) - Focus on multi-provider LLM, quality eval sections

**Code Focus**:
- `worker/eval/` - Evaluation pipeline
- `worker/rag/` - Retrieval-augmented generation
- `worker/agents/` - Extraction logic

**Hands-On**: Improve evaluation metrics or add new metric

---

### DevOps / Platform Engineer

**Goal**: Deploy, scale, and operate the system  
**Time**: 9 hours

1. [Executive Summary](01-executive-summary.md)
2. [System Mental Model](03-system-mental-model.md) - Focus on infrastructure section
3. [Architecture Overview](04-architecture-overview.md) - Focus on scalability, concurrency
4. [Data Architecture](06-data-architecture.md)
5. [Runtime Flows](07-runtime-flows.md) - Focus on error handling
6. [Architecture Decisions](09-architecture-decisions.md) - Focus on async, Celery, Redis, database sections
7. [Security Architecture](10-security-architecture.md)
8. [Knowledge Gaps](19-knowledge-gaps.md) - Focus on deployment, monitoring, reliability

**Code Focus**:
- `requirements.txt` - Dependencies
- `worker/core/` - Infrastructure setup
- `worker/middleware/` - Monitoring and rate limiting

**Hands-On**: Deploy to Kubernetes or AWS Lambda

---

### Product Manager

**Goal**: Understand capabilities and limitations  
**Time**: 4 hours

1. [Executive Summary](01-executive-summary.md)
2. [System Mental Model](03-system-mental-model.md)
3. [Architecture Overview](04-architecture-overview.md) - Light read
4. [Architecture Decisions](09-architecture-decisions.md) - Focus on "Why" sections
5. [Knowledge Gaps](19-knowledge-gaps.md)

**Key Takeaways**:
- What's currently possible
- What's technically difficult
- What's the cost/benefit of features
- What's the roadmap implication

---

### Security Auditor

**Goal**: Identify risks and compliance gaps  
**Time**: 7 hours

1. [Executive Summary](01-executive-summary.md)
2. [System Mental Model](03-system-mental-model.md)
3. [Architecture Overview](04-architecture-overview.md)
4. [Data Architecture](06-data-architecture.md) - Focus on data stores, persistence
5. [Security Architecture](10-security-architecture.md) - Complete
6. [Runtime Flows](07-runtime-flows.md) - Focus on "Flow 1" (Auth) and "Flow 4" (Rate limit)
7. [Knowledge Gaps](19-knowledge-gaps.md) - Focus on security sections

**Code Focus**:
- `worker/core/security.py` - Authentication, authorization
- `worker/middleware/rate_limit.py` - Rate limiting
- `tests/test_security.py` - Security tests

**Hands-On**: Perform security audit, identify 10 gaps

---

## Reading by Topic

### Multi-Tenancy
1. [System Mental Model](03-system-mental-model.md) - "Multi-Tenancy" section
2. [Data Architecture](06-data-architecture.md) - Tenant filtering
3. [Runtime Flows](07-runtime-flows.md) - "Flow 5: Multi-Tenancy Isolation"
4. [Architecture Decisions](09-architecture-decisions.md) - Decision 4

---

### Async/Scalability
1. [Architecture Overview](04-architecture-overview.md) - "Concurrency Model" section
2. [Runtime Flows](07-runtime-flows.md) - "Flow 2" (upload and processing)
3. [Architecture Decisions](09-architecture-decisions.md) - Decisions 1 and 2
4. [Component Architecture](05-component-architecture.md) - Skip unless interested

---

### LLM Integration
1. [System Mental Model](03-system-mental-model.md) - "LLM Router" section
2. [Component Architecture](05-component-architecture.md) - "LLM Service Architecture" section
3. [Runtime Flows](07-runtime-flows.md) - "Flow 2" step 5
4. [Architecture Decisions](09-architecture-decisions.md) - Decision 3
5. Code: `worker/services/llm/`

---

### Reliability/Fault Tolerance
1. [System Mental Model](03-system-mental-model.md) - "Error Handling" section
2. [Runtime Flows](07-runtime-flows.md) - "Flow 3: Error Handling Cascade"
3. [Architecture Decisions](09-architecture-decisions.md) - Decision 3 (Circuit Breaker)
4. [Design Patterns](08-design-patterns.md) - Decision 3 (Circuit Breaker)
5. Code: `worker/services/llm/circuit_breaker.py`

---

### Data & Database
1. [Data Architecture](06-data-architecture.md) - Complete
2. [Repository Map](02-repository-map.md) - "Worker Package Structure" section
3. [Runtime Flows](07-runtime-flows.md) - Data flow sections
4. Code: `worker/models/`, `worker/core/database.py`

---

### Security & Auth
1. [Security Architecture](10-security-architecture.md) - Complete
2. [Runtime Flows](07-runtime-flows.md) - "Flow 1: Registration and Login"
3. [Design Patterns](08-design-patterns.md) - Dependency Injection section
4. Code: `worker/core/security.py`

---

### Quality & Evaluation
1. [Component Architecture](05-component-architecture.md) - "Evaluation Architecture" section
2. [Architecture Decisions](09-architecture-decisions.md) - Decision 10
3. Code: `worker/eval/`

---

## Study Tips

### Tip 1: Read in Layers
- First pass: Skim for structure
- Second pass: Deep read for understanding
- Third pass: Code study for details

### Tip 2: Keep Code Open
- Read documentation
- Then open corresponding code file
- Trace through actual implementation

### Tip 3: Take Notes
- Write summaries in your own words
- Draw architecture diagrams
- List questions as you go

### Tip 4: Do Hands-On Exercises
- Don't just read
- Run the code
- Modify it
- Break it and fix it

### Tip 5: Cross-Reference
- When a document mentions a file, open that file
- When a file references a pattern, read the pattern document
- Build a mental map as you go

---

## Learning Checkpoints

### Checkpoint 1: System Understanding
- [ ] Can you explain what this system does in 2 sentences?
- [ ] Can you draw the basic architecture from memory?
- [ ] Do you understand the 202 async pattern?

### Checkpoint 2: Code Navigation
- [ ] Can you find where job processing happens?
- [ ] Can you find where authentication is enforced?
- [ ] Can you find where LLM providers are defined?

### Checkpoint 3: Data Flow Understanding
- [ ] Can you trace a request from POST /process to database?
- [ ] Can you explain where failures happen and how they're handled?
- [ ] Do you understand tenant isolation?

### Checkpoint 4: Modification Capability
- [ ] Can you add a new LLM provider?
- [ ] Can you add a new metric to evaluation?
- [ ] Can you add a new database column?

### Checkpoint 5: Architecture Understanding
- [ ] Can you explain why async architecture was chosen?
- [ ] Can you explain why multi-tenancy was chosen?
- [ ] Can you explain the tradeoffs in each decision?

---

## After You've Read Everything

### Next Steps
1. **Contribute**: Pick an issue, submit a PR
2. **Experiment**: Deploy locally, modify features
3. **Teach**: Explain the system to someone else
4. **Extend**: Add a feature end-to-end
5. **Redesign**: Propose a system improvement

### Resources to Explore
- Tests: Study each test module
- Errors: Trigger errors, understand handling
- Monitoring: Setup observability
- Performance: Load test and profile

---

## Total Time by Path

| Path | Reading | Hands-On | Total |
|------|---------|----------|-------|
| Quick | 3h | - | 3h |
| Standard | 6.5h | 2.5h | 9h |
| Expert | 12h | 4h | 16h |
| Backend | 7.5h | 2.5h | 10h |
| Data Scientist | 6h | 2h | 8h |
| DevOps | 7h | 2h | 9h |
| Product | 4h | - | 4h |
| Security | 6h | 1h | 7h |

---

## Success Metric

You've mastered this repository when you can:

1. ✅ Explain the system to others
2. ✅ Locate any piece of code quickly
3. ✅ Understand any request's flow
4. ✅ Add features confidently
5. ✅ Improve performance
6. ✅ Fix bugs systematically
7. ✅ Propose architectural improvements
8. ✅ Consider tradeoffs thoughtfully

---

**Good luck on your learning journey!**

Start with the path that matches your role, take notes, run the code, and don't hesitate to re-read sections. Understanding a production system takes time, but the investment pays dividends.

When you hit concepts you don't understand, reference the links provided - they're designed to guide you deeper.

