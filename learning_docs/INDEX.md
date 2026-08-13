# Meeting Automation MVP - Learning Curriculum

A comprehensive reverse-engineered learning guide for understanding this sophisticated production-grade meeting automation system.

## Quick Navigation

### Core Understanding
1. **[Executive Summary](01-executive-summary.md)** - What this system does at a glance
2. **[Repository Map](02-repository-map.md)** - Directory structure and file organization
3. **[System Mental Model](03-system-mental-model.md)** - How all pieces fit together

### Architecture & Design
4. **[Architecture Overview](04-architecture-overview.md)** - High-level architectural patterns
5. **[Component Architecture](05-component-architecture.md)** - Individual subsystems in detail
6. **[Data Architecture](06-data-architecture.md)** - Database, schemas, and data flow
7. **[Runtime Flows](07-runtime-flows.md)** - How requests flow through the system

### Deep Dives
8. **[Important Features](08-important-features.md)** - Key capabilities and their implementation
9. **[Design Patterns](09-design-patterns.md)** - Software engineering patterns used
10. **[Architecture Decisions](10-architecture-decisions.md)** - Why each major choice was made

### Analysis
11. **[Alternatives & Tradeoffs](11-alternatives-tradeoffs.md)** - What could have been different
12. **[Security](12-security.md)** - Security architecture and considerations
13. **[Reliability](13-reliability.md)** - Fault tolerance and resilience patterns
14. **[Performance](14-performance.md)** - Performance characteristics and optimization

### Quality & Learning
15. **[Testing Strategy](15-testing-strategy.md)** - How the system validates correctness
16. **[Infrastructure](16-infrastructure.md)** - Deployment and operational aspects
17. **[Weaknesses & Technical Debt](17-weaknesses-technical-debt.md)** - Known issues and risks
18. **[Learning Curriculum](18-learning-curriculum.md)** - Structured learning path
19. **[Knowledge Gaps](19-knowledge-gaps.md)** - What we can't determine from the code
20. **[Deep Dive Order](20-recommended-deep-dive.md)** - Where to start reading

---

## How to Use This Documentation

### For Getting Started
- Start with **Executive Summary** (5 min)
- Then **System Mental Model** (15 min)
- Then **Repository Map** (10 min)

### For Understanding How It Works
- Follow **Recommended Deep Dive Order**
- Use **Runtime Flows** to trace actual behavior
- Reference **Component Architecture** for specific details

### For Learning Architecture Principles
- Study **Design Patterns** to see principles in action
- Review **Architecture Decisions** to understand tradeoffs
- Explore **Alternatives & Tradeoffs** to expand your thinking

### For Maintenance & Extension
- Use **Weaknesses & Technical Debt** to identify risks
- Reference **Security** before adding features
- Check **Testing Strategy** before modifying code

---

## Key Conventions in This Documentation

### Evidence Levels
When we explain "why" a decision was made, we distinguish:

1. **[Observable]** - Directly visible in code/configuration
2. **[Inferred]** - Reasonable engineering inference from patterns
3. **[Assumed]** - Cannot be verified from repository alone

### File References
All references use this format: `path/to/file.py:LineNumber`

Example: `worker/services/llm/router.py:45`

### Diagrams
We use Mermaid for architecture diagrams. They're embedded in markdown.

---

## Repository Quick Facts

- **Language**: Python 3.x
- **Framework**: FastAPI (async)
- **Primary Task Broker**: Celery + Redis
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Tests**: 13 comprehensive test modules
- **Status**: Clean, production-ready MVP
- **Branch**: `revisit`

---

## What This Repository Teaches

This is an excellent learning resource for:
- **Async architecture** (FastAPI + Celery)
- **Multi-tenancy** (complete isolation patterns)
- **LLM integration** (multi-provider with failover)
- **Quality assurance** (evaluation pipelines)
- **System design** (real production patterns)
- **Testing strategy** (comprehensive coverage)
- **Security** (auth, RBAC, tenant isolation)
- **Reliability** (circuit breakers, retries)

---

**Total Documentation**: ~25,000 words organized in 20 sections  
**Estimated Reading Time**: 4-6 hours for complete understanding  
**Best Enjoyed**: With the code repository open in your editor
