# Component Architecture

Deep dive into each major subsystem.

---

## LLM Service Architecture

### Purpose
Provide a unified interface to multiple LLM providers with automatic failover, cost tracking, and fault tolerance.

### Components

```
┌─────────────────────────────────────────────┐
│ LLM Router (router.py)                      │
│ Public interface: query(), structured()    │
└────────────┬────────────────────────────────┘
             │
    ┌────────┼────────┐
    │        │        │
    ▼        ▼        ▼
┌─────┐ ┌──────┐ ┌──────────┐
│Groq │ │OpenAI│ │Anthropic │
└─────┘ └──────┘ └──────────┘
    │        │        │
    └────────┼────────┘
             │
             ▼
    ┌────────────────────┐
    │Circuit Breaker     │
    │ (CLOSED/OPEN)     │
    └────────────────────┘
             │
             ▼
    ┌────────────────────┐
    │Pricing & Usage     │
    │ (token tracking)   │
    └────────────────────┘
```

### Key Classes

#### LLMRouter
**File**: `worker/services/llm/router.py`

**Interface**:
```python
class LLMRouter:
    async def query(prompt: str) -> str
    async def structured(prompt: str, schema: Type[T]) -> T
    estimate_cost(provider: str, tokens: int) -> float
```

**Algorithm**:
```python
def query(prompt):
    for provider in [Groq, OpenAI, Anthropic, Gemini]:
        if provider.circuit.is_open():
            continue  # Skip open circuits
        
        try:
            result = provider.query(prompt)
            provider.circuit.mark_success()
            return result
        except Exception as e:
            provider.circuit.mark_failure()
            continue
    
    raise AllProvidersFailedError()
```

**Key Insight**: [Observable] Tries each provider in order. Circuit breaker prevents retrying failing providers.

#### LLMProvider (Abstract)
**File**: `worker/services/llm/base.py`

**Interface**:
```python
class LLMProvider(ABC):
    @abstractmethod
    async def query(self, prompt: str) -> str: ...
    
    @abstractmethod
    async def structured(self, prompt: str, schema) -> Any: ...
    
    def estimate_tokens(self, text: str) -> int: ...
    
    async def stream(self, prompt: str) -> AsyncIterator[str]: ...
```

**Why Abstract**: [Observable] Each provider has different API structure. Concrete classes handle provider-specific quirks.

#### Provider Implementations

**Groq** (`worker/services/llm/providers/groq.py`):
- **Cost**: ~$0.05 per 1M input tokens
- **Speed**: Fastest (optimized hardware)
- **Strengths**: JSON mode, function calling
- **Weakness**: Limited model selection

**OpenAI** (`worker/services/llm/providers/openai.py`):
- **Cost**: ~$5 per 1M input tokens (100x more expensive)
- **Speed**: Moderate
- **Strengths**: Most reliable, strong model (GPT-4)
- **Weakness**: Cost, rate limits

**Anthropic** (`worker/services/llm/providers/anthropic.py`):
- **Cost**: ~$3 per 1M input tokens
- **Speed**: Moderate
- **Strengths**: Structured output, strong reasoning
- **Weakness**: Rate limits

**Gemini** (`worker/services/llm/providers/gemini.py`):
- **Cost**: Free tier available
- **Speed**: Moderate
- **Strengths**: Cost (last resort)
- **Weakness**: Limited capabilities, rate limits

**[Observable]** Order is deliberate: Cost (Groq) → Reliability (OpenAI) → Quality (Anthropic) → Free (Gemini).

#### Circuit Breaker
**File**: `worker/services/llm/circuit_breaker.py`

**States**:
```
CLOSED (normal)
  ├─ Requests pass through
  └─ On 3+ failures → OPEN

OPEN (provider down)
  ├─ Requests fail immediately
  └─ After 60 seconds → HALF_OPEN

HALF_OPEN (testing recovery)
  ├─ Single request passes through
  ├─ If succeeds → CLOSED
  └─ If fails → OPEN (restart timer)
```

**Why**: [Observable] Prevents thundering herd. If Groq is flaky, don't hammer it while open.

#### Pricing Service
**File**: `worker/services/llm/pricing.py`

**What It Does**:
```python
class PricingService:
    def estimate_cost(self, provider: str, tokens: int) -> float:
        # Example: Groq = $0.05 per 1M tokens
        # 1000 tokens = $0.00005
        return (tokens / 1_000_000) * RATES[provider]
```

**Why**: [Inferred] Know your costs before they explode. Budget tracking for multi-tenant usage.

---

## RAG (Retrieval-Augmented Generation) Architecture

### Purpose
Enable the system to find and use relevant context from transcripts when extraction is uncertain.

### Flow
```
Query: "What should be done?"
    │
    ├─ Chunker: Split transcript into 512-token chunks (50% overlap)
    │
    ├─ Indexer: Build two indexes
    │   ├─ Dense: Vector embeddings (semantic search)
    │   └─ Sparse: BM25 (keyword search)
    │
    ├─ Retriever: Hybrid search
    │   ├─ Query both indexes
    │   └─ Merge results (BM25 + cosine similarity)
    │
    ├─ Reranker: Re-rank by relevance (cross-encoder)
    │
    └─ Return: Top-5 relevant chunks

Used by extraction: "Given these chunks, extract action items"
```

### Components

#### Chunker
**File**: `worker/rag/chunker.py`

**Algorithm**: Sliding window with overlap
```python
def chunk(text, chunk_size=512, overlap=0.5):
    stride = int(chunk_size * (1 - overlap))  # 256 for 512-size chunks
    chunks = []
    for i in range(0, len(text), stride):
        chunk = text[i : i + chunk_size]
        chunks.append(chunk)
    return chunks
```

**Why Overlap**: [Observable] Prevents losing context at chunk boundaries. Action item might span two chunks.

#### Indexer
**File**: `worker/rag/indexer.py`

**Dense Index (Embeddings)**:
```python
# Convert chunks to vectors
embeddings = model.encode(chunks)
# Store in Redis/Qdrant
vector_store.index(chunks, embeddings)
```

**Purpose**: Semantic search ("What does this chunk mean?")

**Sparse Index (BM25)**:
```python
# Keyword-based ranking
bm25 = BM25Okapi(chunks)
```

**Purpose**: Lexical search ("Does this chunk contain these words?")

**Why Both**: [Observable] Semantic search misses exact keywords. Lexical search misses synonyms. Combined = best of both.

#### Retriever
**File**: `worker/rag/retriever.py`

**Algorithm**:
```python
def retrieve(query: str, top_k=5):
    # Dense search
    query_embedding = model.encode(query)
    dense_results = vector_store.search(query_embedding, top_k=10)
    
    # Sparse search
    sparse_results = bm25.get_top_n(query, documents, n=10)
    
    # Merge and rank
    merged = merge_results(dense_results, sparse_results)
    return merged[:top_k]
```

**[Inferred]** Hybrid search is more robust than either alone.

#### Reranker
**File**: `worker/rag/reranker.py`

**What It Does**:
```python
# Cross-encoder scores all (query, chunk) pairs
scores = cross_encoder.predict([
    [query, chunk1],
    [query, chunk2],
    ...
])

# Re-rank by cross-encoder score (more accurate than bi-encoder)
reranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
return reranked[:top_k]
```

**Why Reranking**: [Observable] Initial retrieval is approximate. Reranker uses more expensive model to refine top results.

---

## Evaluation Architecture

### Purpose
Assess quality of extractions. Detect hallucinations, missing items, or errors.

### Components

```
Extraction Result
    │
    ├─ Metrics (fast, deterministic)
    │   ├─ Faithfulness: Does text appear in transcript?
    │   ├─ Recall: How much ground truth did we catch?
    │   └─ Overall score (weighted average)
    │
    └─ LLM Judge (slower, semantic)
        ├─ Prompt LLM: "Is this faithful?"
        ├─ LLM scores: 0-1
        └─ Combined with metrics
        
    Result: Quality score 0-1
    
    If score < threshold:
        └─ Export to benchmark dataset
```

#### Metrics Service
**File**: `worker/eval/metrics.py`

**Faithfulness Metric**:
```python
def faithfulness(extraction: str, transcript: str) -> float:
    # Simple: how much of extracted text appears in transcript?
    # (Lexical match, not semantic)
    
    words_in_extraction = set(extraction.lower().split())
    words_in_transcript = set(transcript.lower().split())
    
    overlap = len(words_in_extraction & words_in_transcript)
    total = len(words_in_extraction)
    
    return overlap / total if total > 0 else 0
```

**Limitations**: [Observable] Lexical only. Synonyms don't match. But deterministic and fast.

**Recall Metric**:
```python
def recall(extracted_items: List[str], ground_truth: List[str]) -> float:
    # Of the ground truth items, how many did we extract?
    # Requires labeled dataset (rare)
    
    matches = sum(1 for item in ground_truth 
                  if any(item.lower() in ext.lower() 
                         for ext in extracted_items))
    return matches / len(ground_truth)
```

#### LLM Judge
**File**: `worker/eval/judge.py`

**Algorithm**:
```python
def judge_faithfulness(extraction: str, transcript: str) -> float:
    prompt = f"""
    Is this extraction faithful to the transcript?
    
    Extraction: {extraction}
    Transcript: {transcript}
    
    Rate on 0-1 scale.
    """
    
    try:
        score = await llm_router.query(prompt)
        return float(score)
    except:
        # Fallback to deterministic metrics if LLM fails
        return deterministic_metrics(extraction, transcript)
```

**Why Fallback**: [Observable] LLM might fail. Graceful degradation: use metrics instead.

#### Dataset Exporter
**File**: `worker/eval/dataset_exporter.py`

**What It Does**:
```python
def export_low_scoring_samples(threshold=0.7):
    low_scores = db.query(Job).filter(Job.quality_score < threshold)
    
    dataset = {
        "samples": [
            {
                "transcript": job.transcript,
                "extraction": job.result_payload,
                "score": job.quality_score,
                "timestamp": job.completed_at
            }
            for job in low_scores
        ]
    }
    
    save_to_file("benchmark_dataset.jsonl", dataset)
```

**Purpose**: [Inferred] Build training dataset for fine-tuning or model improvement.

---

## Agent Extraction Architecture

### Purpose
Multi-step extraction with validation and human-in-the-loop pauses.

### Components

```
Raw Transcript
    │
    ├─ 1. Cleaner Node
    │     └─ Normalize text, remove filler
    │
    ├─ 2. Extractor Node
    │     └─ Call LLM, get structured output
    │
    ├─ 3. Auditor Node
    │     ├─ Check consistency
    │     └─ Validate business rules
    │
    └─ 4. Inspector Node
          ├─ Calculate confidence
          └─ Flag for human review if needed

Result: Validated, audited, confidence-scored extraction
```

#### Graph Executor
**File**: `worker/agents/graph.py`

**Algorithm**:
```python
class DAGExecutor:
    def __init__(self, nodes: Dict[str, Callable]):
        self.nodes = nodes  # name -> function
        self.edges = {}     # name -> list of dependent names
    
    async def run(self, initial_state: AgentState) -> AgentState:
        state = initial_state
        
        for node_name in self.topological_sort():
            if self.should_pause(state):
                # Human review needed
                return state
            
            # Execute node
            state = await self.nodes[node_name](state)
        
        return state
```

**[Observable]** Nodes run in dependency order. Can pause for human review.

#### Agent State
**File**: `worker/agents/state.py`

**Structure**:
```python
@dataclass
class AgentState:
    transcript: str              # Original
    cleaned_text: str           # After cleaner
    extracted_items: List[str]  # After extractor
    audit_notes: str            # After auditor
    confidence: float           # After inspector
    human_review_needed: bool   # If confidence < threshold
```

**Pattern**: Mutable state threaded through pipeline (vs. return values).

#### Processing Nodes

**Cleaner** (`nodes/cleaner.py`):
- Remove filler words ("um", "uh", "like")
- Normalize punctuation
- Fix speech-to-text errors
- Output: Cleaned transcript

**Extractor** (`nodes/extractor.py`):
- Take cleaned transcript
- Call LLM with extraction prompt
- Parse structured output
- Output: Extracted items

**Auditor** (`nodes/auditor.py`):
- Validate extracted items
- Check consistency (same person assigned multiple items?)
- Check reasonableness (deadline in past?)
- Output: Audit notes

**Inspector** (`nodes/inspector.py`):
- Calculate confidence score
- Determine if human review needed (low confidence)
- Output: Confidence, review flag

---

## Cache Architecture

### Purpose
Avoid redundant LLM calls for similar transcripts.

### Components

```
Incoming Transcript
    │
    ├─ 1. Hash text (SHA256)
    │
    ├─ 2. Check database
    │     └─ Exact match in cache?
    │        └─ Return cached result (skip LLM)
    │
    └─ 3. If no match, compute embeddings
         │
         ├─ Check semantic similarity
         │  └─ Score > 95%?
         │     └─ Return cached result with minor adjustment
         │
         └─ If no semantic match
            ├─ Call LLM
            ├─ Store result in cache
            └─ Update embeddings
```

#### Semantic Cache
**File**: `worker/services/cache/semantic_cache.py`

**Algorithm**:
```python
class SemanticCache:
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
        
        # Cache miss: compute and store
        result = compute_fn(text)
        self.redis[exact_hash] = result
        self.redis_store_embedding(embedding, result)
        return result
```

**Keys**:
```
cache:text:sha256(text) = result
cache:embedding:uuid = embedding_vector
cache:metadata:uuid = hits, misses, timestamp
```

**Tradeoff**: Complexity vs. cost savings. For high-volume, worth it.

---

## Security Architecture

### Components

```
HTTP Request
    │
    ├─ 1. Validate JWT token
    │     └─ Verify signature, expiration
    │
    ├─ 2. Extract user & tenant_id
    │
    ├─ 3. Check rate limit
    │     └─ Token bucket per (tenant, endpoint)
    │
    ├─ 4. Check RBAC
    │     └─ User role >= required role?
    │
    └─ 5. Process request (with user context)
```

#### JWT Authentication
**File**: `worker/core/security.py`

**Token Structure**:
```python
def create_access_token(user_id: str, tenant_id: str):
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "exp": datetime.utcnow() + timedelta(minutes=60)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**Verification**:
```python
async def get_current_user(token: str) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    return user
```

**[Observable]** Token includes tenant_id. Used for all tenant-scoped queries.

#### RBAC (Role-Based Access Control)
**File**: `worker/core/security.py`

**Roles**:
- **admin**: Full access to tenant
- **member**: Create/view own jobs
- **viewer**: Read-only

**Pattern**:
```python
def require_role(required_role: str):
    async def check(user: User = Depends(get_current_user)):
        if not has_role(user, required_role):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check

# Usage:
@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, user: User = Depends(require_role("admin"))):
    ...
```

#### Rate Limiting
**File**: `worker/middleware/rate_limit.py`

**Algorithm**: Token bucket
```python
def check_rate_limit(tenant_id: str, endpoint: str) -> bool:
    key = f"rate_limit:{tenant_id}:{endpoint}"
    
    # Redis implementation
    current = redis.get(key) or 0
    if current >= MAX_REQUESTS_PER_MINUTE:
        return False
    
    redis.incr(key)
    redis.expire(key, 60)
    return True
```

**[Observable]** Per-tenant, per-endpoint limits. Prevent DOS without affecting other tenants.

---

**Next Step**: Read [Data Architecture](06-data-architecture.md) to understand database design.
