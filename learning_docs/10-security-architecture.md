# Security Architecture

Security principles and implementations.

---

## Threat Model

### Actors
1. **Authenticated user** (has valid JWT)
2. **Unauthenticated attacker** (no JWT)
3. **Compromised user** (has JWT, using maliciously)
4. **Insider** (legitimate employee, malicious intent)
5. **Supply chain** (dependency compromise)

### Assets to Protect
- Meeting transcripts (confidential business information)
- Extracted action items (business secrets)
- User credentials (email, password)
- Authentication tokens (JWT)
- API keys (Groq, OpenAI, etc.)
- Database contents

### Threat Scenarios

#### Threat 1: Unauthorized Access
**Scenario**: Attacker accesses Company A's meetings

**Protection**:
- JWT authentication (requires valid token)
- Tenant scoping (token includes tenant_id)
- Database filter (every query checks tenant_id)

**Evidence**: [Observable]
```python
# JWT validation
user = get_current_user(token)  # Rejects invalid token

# Tenant scoping
jobs = db.query(Job).filter(
    Job.tenant_id == user.tenant_id  # Tenant check
).all()
```

#### Threat 2: Brute Force Password Attack
**Scenario**: Attacker guesses passwords

**Protection**:
- Bcrypt hashing (slow, salted)
- Rate limiting (throttles login attempts)
- Account lockout (could add)

**Evidence**: [Observable]
```python
# Bcrypt slows down guessing
password_hash = bcrypt.hashpw(password, bcrypt.gensalt())
# ~100ms per attempt, defeats brute force
```

#### Threat 3: Cross-Tenant Data Leak
**Scenario**: Bug in code allows Company A to see Company B data

**Protection**:
- Tenant filter on every query
- Unique constraints per tenant (can't bypass)
- Tests for isolation

**Evidence**: [Observable]
```python
# Unique constraint per tenant
__table_args__ = (
    UniqueConstraint("email", "tenant_id"),  # email unique per tenant
)
```

#### Threat 4: Token Theft
**Scenario**: Attacker steals JWT token

**Protection**:
- Short expiration (60 minutes)
- HTTPS only (don't send token over HTTP)
- Token in Authorization header (not URL/cookie)
- User revokes if compromised (could implement blacklist)

**Current limitation**: [Observable]
- No instant revocation (would need token blacklist)
- If token stolen and used within 60 min, attacker has access

#### Threat 5: API Key Exposure
**Scenario**: Attacker finds API keys in code or environment

**Protection**:
- Environment variables (not in code)
- .env in .gitignore (not committed)
- Secrets management (in production)
- Key rotation (should be periodic)

**Current limitation**: [Assumed]
- Depends on secure environment variable management
- No automatic key rotation shown in code

#### Threat 6: SQL Injection
**Scenario**: Attacker injects SQL via transcript or extraction

**Protection**:
- SQLAlchemy ORM (parameterized queries)
- No string concatenation in SQL
- Input validation (Pydantic schemas)

**Evidence**: [Observable]
```python
# Safe: ORM uses parameterized queries
job = db.query(Job).filter(Job.id == job_id).first()
# vs. vulnerable:
# job = db.query(f"SELECT * FROM jobs WHERE id={job_id}")
```

#### Threat 7: Denial of Service (DoS)
**Scenario**: Attacker makes many requests

**Protection**:
- Rate limiting per tenant (120 requests/min)
- Graceful degradation (return 429, don't crash)
- Load balancing (distribute across servers)

**Evidence**: [Observable]
```python
# Rate limit check
if current >= 120:
    raise HTTPException(429, "Rate limit exceeded")
```

#### Threat 8: Man-in-the-Middle (MITM)
**Scenario**: Attacker intercepts communication

**Protection**:
- HTTPS (encrypted transport)
- JWT signature verification (ensures token not tampered)
- Certificate pinning (optional, not shown)

**Current limitation**: [Assumed]
- Depends on HTTPS being enforced
- No certificate pinning shown

---

## Authentication Flow

```
1. User submits email + password

2. System verifies password
   ├─ Hash submitted password with bcrypt
   ├─ Compare with stored hash (constant time)
   └─ If match: proceed, else: reject

3. System generates JWT
   ├─ Payload: user_id, tenant_id, exp
   ├─ Sign with SECRET_KEY
   └─ Return to client

4. Client stores JWT (localStorage or secure cookie)

5. Subsequent requests include JWT
   ├─ Authorization: Bearer eyJhbGc...
   └─ Server verifies signature and expiry
```

**Key Point**: [Observable] Password never stored in plain text. Only hash stored.

---

## Authorization Model

### RBAC (Role-Based Access Control)

**Roles**:
- **admin**: Full tenant access
- **member**: Create own jobs, view own
- **viewer**: Read-only

**Implementation**:
```python
def require_role(required_role: str):
    async def check(user: User = Depends(get_current_user)):
        if not has_role(user, required_role):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return check
```

**Usage**:
```python
@app.delete("/jobs/{job_id}")
async def delete_job(user: User = Depends(require_role("admin"))):
    ...  # Only admins can delete
```

### Tenant Scoping

**Every query filters by tenant**:
```python
jobs = db.query(Job).filter(
    Job.tenant_id == user.tenant_id
).all()
```

**Benefits**:
- User A in Tenant X cannot access Tenant Y
- Even if JWT forged, database enforces isolation
- Defense in depth

---

## Data Protection

### At Rest
**SQLite/PostgreSQL**: 
- Data persisted to disk
- Could be encrypted (at rest encryption)
- Not shown in code (operational concern)

### In Transit
**HTTP/HTTPS**:
- JWT token in Authorization header
- Response body contains extraction results
- Should use HTTPS (assumed, not shown in code)

### In Processing
**Memory**:
- Passwords held in memory during login
- Transcripts held in memory during processing
- Could use secure deletion (not shown)

---

## Sensitive Data Handling

### What's Considered Sensitive
- Passwords (hash before storing)
- API keys (Groq, OpenAI credentials)
- JWT tokens (expire after 60 min)
- Meeting transcripts (contain business info)
- Extracted action items (competitive data)

### How Handled

**Passwords**:
```python
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
# Store hash, never plain text
```

**API Keys**:
```python
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # From environment
# Never logged, never committed to git
```

**Tokens**:
```python
token = jwt.encode(payload, SECRET_KEY)  # Signed
# Expires after 60 minutes
```

**Transcripts**:
```python
job = Job(..., result_payload={...})
db.commit()
# Stored in database, protected by auth + tenant scoping
```

---

## Security Best Practices Observed

1. ✅ **Defense in depth**: Multiple layers (auth + rate limit + tenant filter)
2. ✅ **Principle of least privilege**: Users only see their own data
3. ✅ **Fail secure**: Reject on error (not permissive)
4. ✅ **Centralized security logic**: One place (core/security.py)
5. ✅ **Dependency injection**: Security checks reused via decorator

---

## Security Gaps & Risks

### Gap 1: No Token Revocation
**Risk**: Compromised token usable until 60-min expiry

**Mitigation**: Could add token blacklist (Redis)
```python
def logout(token: str):
    redis.add_blacklist(token, ttl=expiry_time)

def verify_token(token: str):
    if token in redis_blacklist:
        raise TokenRevoked()
```

### Gap 2: No HTTPS Enforcement (Assumed)
**Risk**: Token/credentials transmitted in plain text over HTTP

**Mitigation**: Configure HTTPS, HSTS header

### Gap 3: No Input Sanitization for XSS
**Risk**: If transcripts displayed in HTML, could have XSS

**Mitigation**: HTML escape output, use template auto-escaping

### Gap 4: No Rate Limit for Login
**Risk**: Brute force password guessing

**Mitigation**: Add rate limit to /auth/login endpoint specifically

### Gap 5: No Audit Logging
**Risk**: Can't trace who did what and when

**Mitigation**: Log all security events (login, data access)

### Gap 6: Hardcoded SECRET_KEY (Not In Code, But Assumed)
**Risk**: If SECRET_KEY is weak, JWTs can be forged

**Mitigation**: Use strong, random SECRET_KEY. Rotate periodically.

---

## Compliance Considerations

### Data Privacy (GDPR, CCPA)
- **Requirement**: Right to be forgotten, data portability
- **Implementation**: Could add soft-delete + export endpoint
- **Current**: [Assumed] Not implemented

### Data Residency
- **Requirement**: Data stays in specific region
- **Implementation**: Could replicate database regionally
- **Current**: [Assumed] Not enforced

### Encryption
- **Requirement**: Data encrypted at rest and in transit
- **Implementation**: Database encryption, HTTPS
- **Current**: [Assumed] Depends on operational setup

### Access Control
- **Requirement**: Fine-grained permissions, audit trail
- **Implementation**: RBAC shown, audit logging not shown
- **Current**: Partial implementation

---

## Security Testing Checklist

From [test_security.py]:

- ✅ JWT validation (invalid token rejected)
- ✅ Token expiry (expired token rejected)
- ✅ Tenant scoping (can't access other tenant's data)
- ✅ RBAC (role restrictions enforced)
- ✅ Rate limiting (exceeding limit returns 429)
- ✅ Password hashing (plaintext not stored)

---

## Recommendations

1. **Implement token blacklist** for instant revocation
2. **Add audit logging** for compliance
3. **Implement key rotation** for API keys
4. **Add HTTPS enforcement** (redirect HTTP to HTTPS)
5. **Rate limit /auth/login** specifically
6. **Add security headers** (CORS, CSP, X-Frame-Options)
7. **Implement secrets rotation** policy
8. **Add database encryption** at rest
9. **Implement data export** for GDPR compliance
10. **Add comprehensive audit trail** for all data access

---

**Next Step**: Read [Reliability](11-reliability.md) to understand fault tolerance mechanisms.
