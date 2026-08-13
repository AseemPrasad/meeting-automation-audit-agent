# Knowledge Gaps

Things that cannot be determined from the repository alone.

---

## Business Context

### Missing Context 1: Why This Product?
**What we know**: System transcribes and extracts from meetings.

**What we don't know**:
- Who is the target customer? (SMBs? Enterprises?)
- What problem do they have? (Too many meetings? Need better notes?)
- What's the pricing model? (Per-user? Per-transcription? Subscription?)
- Is this a B2B or B2C product?

**Where to find**: Business plan, customer interviews, product requirements document.

---

### Missing Context 2: Market/Competitive Landscape
**What we know**: System uses Groq + OpenAI + Anthropic + Gemini.

**What we don't know**:
- Are there competitors? (Otter.ai, Fireflies, Sembly)
- What are their pricing and features?
- What's our competitive advantage?
- Why would a customer choose us?

**Impact**: Affects feature priority and pricing strategy.

---

### Missing Context 3: Usage Patterns
**What we know**: System can scale to thousands of requests.

**What we don't know**:
- How many concurrent users? (10? 1000? 1M?)
- What's the typical job duration? (5 min meetings? 4 hour conferences?)
- Peak vs. off-peak traffic patterns?
- Geographic distribution?

**Impact**: Affects infrastructure sizing, cost, scaling strategy.

---

## Operational Context

### Missing Context 4: Deployment
**What we know**: Application is Python/FastAPI.

**What we don't know**:
- Where does it run? (Docker? Kubernetes? Serverless?)
- Who manages Redis? (Self-hosted? Managed service?)
- Who manages PostgreSQL? (Self-hosted? RDS?)
- How are secrets managed?
- What's the backup strategy?
- What's the monitoring/alerting setup?

**Where to find**: DevOps documentation, infrastructure-as-code repo, runbook.

---

### Missing Context 5: Cost Structure
**What we know**: System calls external APIs (Groq, OpenAI, etc.)

**What we don't know**:
- What's the cost per job? (Depends on transcript length)
- What's the gross margin? (Revenue - API costs)
- At what scale does margin become negative?
- How are costs allocated to customers?
- What's the break-even point?

**Impact**: Affects pricing, which LLM to use, caching strategy.

---

### Missing Context 6: Data Retention
**What we know**: Jobs and users stored in database.

**What we don't know**:
- How long do we keep job records? (Forever? 1 year?)
- What about audit logs?
- What about old embeddings/cache entries?
- How often do we backup?
- What's the data retention policy?

**Where to find**: Operations manual, compliance documentation.

---

## Technical Unknowns

### Missing Context 7: Performance Targets
**What we know**: System processes transcription (20-30s) + extraction (5-10s).

**What we don't know**:
- What's acceptable latency? (30s? 60s? Real-time?)
- What's acceptable throughput? (100 jobs/day? 100k jobs/day?)
- What's the CPU/memory budget per server?
- What's the acceptable cost per job?

**Impact**: Affects LLM choice (Groq is faster but less capable), caching strategy, scaling.

---

### Missing Context 8: Quality Requirements
**What we know**: System has evaluation pipeline that scores extractions.

**What we don't know**:
- What quality threshold is acceptable? (80%? 95%? 99%?)
- What happens to low-quality jobs? (Retry? Escalate? Alert?)
- Are there SLAs? (99.9% accuracy?)
- How is quality measured in production?

**Impact**: Affects evaluation strategy, LLM choice, improvement roadmap.

---

### Missing Context 9: Reliability Requirements
**What we know**: System uses circuit breaker and fallback providers.

**What we don't know**:
- What's the acceptable uptime? (99%? 99.9%? 99.99%?)
- What's the maximum acceptable outage?
- What's the acceptable data loss? (None? 1 day?)
- Are there compliance requirements (e.g., SOC2)?

**Impact**: Affects architecture, backup strategy, disaster recovery.

---

## Missing Features/Code

### Missing Context 10: Streaming Responses
**What we know**: System processes async but returns all at once.

**What we don't know**:
- Should results stream as LLM generates? (Better UX)
- Should transcription stream as recognized?
- Is WebSocket implemented?

**Code gap**: No websocket implementation shown. Only polling.

---

### Missing Context 11: Model Training/Evaluation
**What we know**: Dataset exported for low-scoring samples.

**What we don't know**:
- How does this dataset feed into model improvement?
- Is there a fine-tuning pipeline?
- How often are models updated?
- A/B testing for model versions?

**Code gap**: No model training pipeline shown.

---

### Missing Context 12: Admin Panel
**What we know**: API exists but no admin UI shown.

**What we don't know**:
- Can admins view all tenant jobs?
- Can admins modify extraction results?
- Can admins block users/tenants?
- What's the admin dashboard look like?

**Code gap**: Only basic HTML form. No full UI. No admin functionality.

---

### Missing Context 13: Audit Logging
**What we know**: System has user authentication.

**What we don't know**:
- Are all actions logged?
- Can we see who accessed what and when?
- Is there a compliance audit trail?

**Code gap**: No audit logging shown. Only basic logging.

---

### Missing Context 14: Email/Notifications
**What we know**: System processes meetings.

**What we don't know**:
- Are notifications sent when job completes?
- Can results be emailed to users?
- Are there digest emails?

**Code gap**: No notification system shown in code.

---

### Missing Context 15: Webhooks
**What we know**: System processes async.

**What we don't know**:
- Can external systems be notified when job completes?
- Are webhooks supported?
- Are they retried on failure?

**Code gap**: No webhook infrastructure shown.

---

## Architectural Unknowns

### Missing Context 16: Database Replication
**What we know**: Can use PostgreSQL in production.

**What we don't know**:
- Is database replicated for HA?
- What's the backup strategy?
- How is failover handled?

**Code gap**: No database replication shown. Depends on operational setup.

---

### Missing Context 17: Redis Clustering
**What we know**: Redis used for queue, cache, rate limit.

**What we don't know**:
- Is Redis clustered for HA?
- What's the persistence strategy (RDB, AOF)?
- How is failover handled if Redis crashes?

**Code gap**: No Redis cluster configuration shown. Depends on operational setup.

---

### Missing Context 18: Load Balancing
**What we know**: FastAPI can run multiple instances.

**What we don't know**:
- How is traffic load-balanced?
- Is it round-robin or more sophisticated?
- How is sticky session handling (if needed)?

**Code gap**: No load balancer configuration shown. Depends on infrastructure.

---

### Missing Context 19: Geo-Distribution
**What we know**: System centralizes everything.

**What we don't know**:
- Are there regional deployments?
- How is latency handled for global users?
- Is data geo-replicated?

**Code gap**: No geo-distribution shown. Single deployment model.

---

### Missing Context 20: Multi-Language Support
**What we know**: UI is English.

**What we don't know**:
- Does it support non-English audio?
- Is UI translated?
- How are transcription languages handled?

**Code gap**: No i18n shown. Likely works for any language via LLM, but not tested.

---

## Testing Unknowns

### Missing Context 21: Integration Testing
**What we know**: 13 test modules exist.

**What we don't know**:
- Are there end-to-end tests? (Full flow: upload to results)
- Are external APIs mocked?
- What's the test environment setup?

**Code gap**: Tests are unit tests. No visible E2E tests.

---

### Missing Context 22: Performance Testing
**What we know**: System can handle concurrent requests.

**What we don't know**:
- What's the actual max throughput?
- Where are the bottlenecks?
- How does it scale at 10k concurrent users?

**Code gap**: No load testing shown in repo.

---

### Missing Context 23: Security Testing
**What we know**: There's a test_security.py file.

**What we don't know**:
- Are there penetration tests?
- Is there OWASP testing?
- Are there fuzzing tests?

**Code gap**: Basic security tests. No advanced security testing.

---

## Documentation Gaps

### Missing Context 24: Code Comments
**What we know**: Code is readable.

**What we don't know**:
- Why was each component designed this way?
- What are the edge cases?
- What assumptions are made?

**Code gap**: Minimal comments. Relies on self-documenting code.

---

### Missing Context 25: Runbook
**What we know**: System has basic README.

**What we don't know**:
- How do you deploy this?
- How do you debug issues?
- What's the incident response procedure?

**Code gap**: No ops runbook.

---

## Questions to Ask the Team

1. **What's the target annual revenue?**
2. **What's the acceptable cost per job?**
3. **What's the target uptime?** (99%? 99.9%? 99.99%?)
4. **How many concurrent users expected in Year 1?**
5. **What's the maximum acceptable latency?**
6. **Is this B2B or B2C?**
7. **Who are the competitors?**
8. **What's the data retention policy?**
9. **Are there compliance requirements?** (GDPR? SOC2? HIPAA?)
10. **What's the deployment strategy?** (Containers? Serverless? Bare metal?)
11. **How are secrets managed?** (Vault? Parameter store? Environment?)
12. **Is there a CI/CD pipeline?**
13. **What monitoring/alerting is in place?**
14. **How is customer data protected?**
15. **What's the disaster recovery plan?**

---

## Conclusion

This repository is excellent for learning **software engineering principles**, but real production knowledge requires understanding:
- Business context
- Operational setup
- Cost structure
- Compliance requirements
- Performance metrics
- Deployment architecture

To fully master this system, you need access to:
1. Business plan
2. Operations manual
3. Deployment documentation
4. Performance baselines
5. Customer feedback
6. Incident logs
7. Architecture review documents
8. Team decisions/RFC (Request for Comments)

---

**Next Step**: Read [Recommended Deep Dive Order](20-recommended-deep-dive.md) for structured reading order.
