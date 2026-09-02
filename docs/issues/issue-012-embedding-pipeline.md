# Engineering Issue #012 — Embedding Pipeline Foundation

<!-- codex-dispatch-supervisor-approved-through: CP6 -->
<!-- codex-dispatch-write-allow: ["compose.yaml",".github/workflows/backend-tests.yml","requirements/base.txt",".env.example","app/core/config.py","app/core/errors.py","app/models/knowledge_chunk.py","app/models/__init__.py","app/repositories/knowledge.py","app/repositories/embedding.py","app/services/chunking.py","app/services/embedding.py","app/integrations/__init__.py","app/integrations/embeddings.py","app/schemas/embedding.py","app/api/routes/knowledge.py","migrations/versions/*embedding*.py","tests/test_config.py","tests/test_chunking.py","tests/test_embedding_provider.py","tests/test_embedding_model.py","tests/test_embedding_repository.py","tests/test_embedding_service.py","tests/test_embedding_api.py","tests/test_embedding_migration.py","tests/test_knowledge_migration.py","tests/test_migrations.py","docs/issues/issue-012-embedding-pipeline.md"] -->

## GitHub Tracking

- GitHub Issue: #54
- Engineering Issue ID: #012
- Branch: `feature/issue-012-embedding-pipeline`

## Goal

Create a deterministic, auditable Embedding Pipeline for persisted KnowledgeDocument content.

The Issue includes:

- deterministic character chunking;
- bounded OpenAI Embeddings API calls behind a provider abstraction;
- pgvector storage;
- idempotent reprocessing;
- provider/error validation;
- RBAC, Audit, Logging, and transaction boundaries.

It explicitly stops before similarity search and vector indexes.

## Required Reading

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #54
- `compose.yaml`
- `.github/workflows/backend-tests.yml`
- `app/core/config.py`
- `app/models/knowledge_document.py`
- `app/repositories/knowledge.py`
- `app/services/knowledge.py`
- `app/api/routes/knowledge.py`
- `migrations/versions/a61f9b2c3d40_add_knowledge_documents.py`
- #011 tests and Audit/Logging boundaries

## External Design References

Current implementation contract was checked against:

- OpenAI `text-embedding-3-small`
- OpenAI Embeddings endpoint
- pgvector upstream PostgreSQL extension / Docker image
- pgvector-python SQLAlchemy `Vector(N)`

The repository contract, not previous chat history, remains authoritative during execution.

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. #011 persists immutable normalized KnowledgeDocument content but creates no chunks or vectors.
2. Current `compose.yaml` uses `postgres:16-alpine`.
3. GitHub Backend Verification also uses `postgres:16-alpine`.
4. Current Python dependencies contain neither OpenAI SDK nor pgvector-python.
5. Current Settings contain no OpenAI/Embedding configuration.
6. `knowledge:manage` already protects Knowledge administration; #012 does not need a new permission.
7. Current Audit and Structured Logging boundaries can be reused.
8. Current Alembic head is `a61f9b2c3d40`.
9. No `app/integrations/` layer currently exists.
10. No vector search/index/retrieval implementation exists, so #012 can add storage without conflicting with #013.
11. #011 KnowledgeDocument content is already normalized and bounded at 100,000 raw characters.
12. The application currently has no external AI-provider call in this Product path, so #012 introduces a new explicit Data Processing boundary.

No architecture contradiction was found.

## CP1 — Architecture / Scope Validation

Status: **completed and approved by Supervisor**

### 1. Dependency / Infrastructure Contract

Use:

```text
pgvector>=0.5,<1
openai>=3,<4
```

Development PostgreSQL:

```text
pgvector/pgvector:0.8.6-pg16
```

GitHub Backend Verification PostgreSQL service must use the same pinned pgvector image.

Add `compose.yaml` to Backend Verification path filters because the database-recovery job depends on it.

Do not add:
- LangChain
- LlamaIndex
- sentence-transformers
- tiktoken
- a Vector DB service separate from PostgreSQL

### 2. pgvector Migration Contract

New migration revises `a61f9b2c3d40`.

Upgrade:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then create `knowledge_chunks`.

Downgrade:
- drop `knowledge_chunks`;
- **do not DROP EXTENSION vector**.

Reason: the extension is a database capability that may later be shared by other tables; a feature downgrade must not destructively remove a pre-existing/shared extension.

Do not create:
- HNSW index
- IVFFlat index
- similarity operator index

Those belong to #013.

### 3. KnowledgeChunk Model

Create `KnowledgeChunk`.

Required fields:

- `id: UUID`
- `document_id: UUID` FK → `knowledge_documents.id`, `ON DELETE CASCADE`
- `chunk_index: int`
- `content: Text`
- `content_hash: String(64)`
- `embedding: Vector(1536)`
- `embedding_provider: String(50)`
- `embedding_model: String(100)`
- `embedding_dimensions: int`
- `chunking_strategy: String(50)`
- `chunk_size: int`
- `chunk_overlap: int`
- `embedding_config_hash: String(64)`
- `created_at`

Unique Constraint:

```text
(document_id, chunk_index, embedding_config_hash)
```

No vector index.

The Python Model and Migration must both use vector dimension **1536**.

### 4. Embedding Configuration

Settings defaults:

```text
OPENAI_API_KEY=<optional>

EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_BATCH_SIZE=32

KNOWLEDGE_CHUNK_SIZE=1000
KNOWLEDGE_CHUNK_OVERLAP=150
```

V1 validation:

- model must be exactly `text-embedding-3-small`;
- dimensions must be exactly `1536`;
- batch size: `1..32`;
- chunk size: `1..2000`;
- chunk overlap: `0 <= overlap < chunk_size`.

Missing OpenAI key:
- does not prevent application import/startup;
- real provider creation/use fails explicitly at Embedding boundary.

### 5. Why Chunk Size <= 2000

V1 uses character-based chunking intentionally.

A valid Unicode code point encodes to at most 4 UTF-8 bytes.

A 2000-character chunk therefore has a conservative byte ceiling below the OpenAI Embeddings per-input token ceiling when considering a worst-case byte-per-token approximation.

Default remains 1000.

This is a safety bound, not a claim that characters equal tokens.

Do not add token-aware chunking in #012.

### 6. Deterministic Chunking

Create a pure chunking utility.

Constants:

```text
strategy = char-v1
default chunk_size = 1000
default overlap = 150
```

Algorithm:

```text
step = chunk_size - overlap

start = 0
while start < len(content):
    chunk = content[start:start + chunk_size]
    emit(chunk_index, chunk, sha256(chunk))
    if end reached:
        stop
    start += step
```

Rules:
- input must be non-empty;
- no chunk trimming/rewrite;
- preserve exact normalized KnowledgeDocument characters;
- stable order;
- stable overlap;
- no empty chunks;
- every chunk length <= configured chunk size.

### 7. Pipeline Configuration Hash

Compute deterministic SHA-256 over canonical JSON containing:

- provider name: `openai`
- chunking strategy: `char-v1`
- chunk size
- chunk overlap
- embedding model
- embedding dimensions

Use sorted keys and stable JSON separators.

Do not use Python object `repr()` as identity.

### 8. Integration Layer

Create:

```text
app/integrations/
    __init__.py
    embeddings.py
```

This layer owns OpenAI SDK-specific code.

Service Layer must not construct/call `OpenAI()` directly.

### 9. Provider Protocol

Define an SDK-independent Protocol/interface.

Conceptual types:

```python
EmbeddingBatchResult(
    vectors: list[list[float]],
    token_usage: int,
)

class EmbeddingProvider(Protocol):
    provider_name: str

    def embed(
        self,
        texts: list[str],
    ) -> EmbeddingBatchResult:
        ...
```

The Service may batch at most `embedding_batch_size` chunks per call.

### 10. OpenAI Provider

V1 production adapter:

- provider name: `openai`
- model: `text-embedding-3-small`
- dimensions: 1536

Call shape must explicitly pass:

```python
client.embeddings.create(
    model=model,
    input=texts,
    dimensions=dimensions,
    encoding_format="float",
)
```

Requirements:

- no call with empty text list;
- validate response item count;
- validate indexes/order;
- validate vector dimensions;
- aggregate `usage.total_tokens`;
- catch OpenAI SDK/provider failures and translate to domain `EmbeddingProviderUnavailableError`;
- malformed output raises a dedicated provider-response/domain error;
- never log input text, vectors, API key, or raw provider response.

Provider constructor/factory may accept a test client so provider unit tests do not access network.

### 11. Batch Bound

Service divides chunks into batches of at most 32.

Do not send all chunks from a maximum-size KnowledgeDocument in one provider call.

No automatic retry in #012.

Reason:
- retries can duplicate external cost;
- retry policy requires explicit idempotency/backoff design and belongs to later reliability hardening.

### 12. Knowledge Repository Extension

Add a bounded read method to existing KnowledgeRepository:

```text
get_by_id(document_id)
```

Repository still owns no transaction boundary.

### 13. Embedding Repository

New repository may:

- list chunks for `document_id + embedding_config_hash`;
- create many KnowledgeChunk rows;
- flush.

It must never:
- Commit
- Rollback
- call external provider
- perform similarity search

### 14. Existing-State Validation

Given expected deterministic chunks and DB rows:

**MISSING**
- zero rows.

**COMPLETE**
- row count equals expected chunk count;
- chunk indexes are exactly 0..N-1;
- each stored `content_hash` matches expected chunk hash;
- provider/model/dimensions/config hash match.

**INCONSISTENT**
- any partial/mismatched state.

For COMPLETE:
- do not call provider;
- Audit with `changed=false`;
- return 200.

For INCONSISTENT:
- rollback read transaction;
- raise `EmbeddingStateConflictError`;
- API returns 409;
- do not call provider;
- do not auto-delete or repair.

### 15. External Call / DB Transaction Boundary

Do not intentionally hold an active DB transaction while calling OpenAI.

Approved Service flow:

```text
SELECT KnowledgeDocument + existing chunk metadata
    ↓
copy immutable primitives into local snapshot
    ↓
classify existing state
    ↓
session.rollback()   # close read-only transaction
    ↓
COMPLETE?
    ├─ yes -> new Audit transaction -> commit -> changed=false
    └─ no
         ↓
external provider calls
         ↓
validate all vectors locally
         ↓
re-query existing state
         ↓
complete due concurrent worker?
    ├─ yes -> Audit changed=false -> commit
    ├─ inconsistent -> rollback -> 409
    └─ absent
         ↓
create KnowledgeChunk rows
         ↓
AuditService.record()
         ↓
single commit
```

The intentional rollback after initial reads is a transaction-boundary operation, not an error rollback.

Copy document content/id before rollback; do not access an expired ORM object during the external call.

### 16. Concurrency Boundary

Two concurrent first-time requests may both pay for provider calls because #012 intentionally avoids holding a database lock across a network request.

Correctness requirement:

- they must not create duplicate persisted chunk sets;
- after provider return, recheck DB state;
- one may persist;
- the other must resolve COMPLETE or fail closed;
- no automatic destructive reconciliation.

Cost-deduplication across concurrent workers requires a job/lock architecture and is Out of Scope.

### 17. Persistence + Audit

New vectors/chunks and Audit Event are one transaction.

Audit event:

```text
action=knowledge.document.embed
target_type=knowledge_document
target_id=<document UUID>
outcome=success
```

Metadata:

- embedding_provider
- embedding_model
- embedding_dimensions
- chunk_count
- embedding_config_hash
- changed
- token_usage

No:
- content
- vectors
- API key
- raw provider response

If Audit persistence fails:
- rollback KnowledgeChunk writes;
- return translated persistence failure.

### 18. Runtime Logging

After successful Commit:

```text
event=knowledge.document.embedded
```

Safe fields:

- document_id
- embedding_provider
- embedding_model
- embedding_dimensions
- chunk_count
- changed
- token_usage

Do not log content/vector/config secret/provider error text.

### 19. API Contract

Add to existing Knowledge router:

```text
POST /admin/knowledge/documents/{document_id}/embeddings
```

Permission:

```text
knowledge:manage
```

No request body.

Return metadata only:

- document_id
- embedding_provider
- embedding_model
- embedding_dimensions
- chunk_count
- embedding_config_hash
- changed
- token_usage

Status:
- 201 new persisted set
- 200 existing complete set
- 404 missing KnowledgeDocument
- 409 inconsistent partial state
- 503 provider not configured/unavailable or persistence unavailable

Do not expose provider exception details.

### 20. CI Contract

Backend Verification changes:

1. use `pgvector/pgvector:0.8.6-pg16` service;
2. add `compose.yaml` to path triggers;
3. after `alembic upgrade head`, verify `vector` extension is installed;
4. run the normal full regression suite;
5. keep downgrade/re-upgrade round trip.

Database Recovery compose path must use the same pgvector image.

No OPENAI_API_KEY is supplied in CI.

Any test that accidentally invokes the real provider should therefore fail rather than spend external API credits.

### 21. Tests

Required focused coverage:

- Settings validation/defaults/key optionality
- deterministic chunking/overlap/hash
- config hash determinism
- KnowledgeChunk model
- migration vector(1536) + extension
- repository no-commit boundary
- OpenAI adapter request arguments/batching-response validation without network
- missing key provider boundary
- service COMPLETE idempotency without provider call
- service MISSING → provider → persistence
- partial state → 409 domain conflict without provider
- malformed provider vectors → no DB writes
- provider unavailable → no DB writes/Audit success
- DB transaction closed before provider call
- post-provider concurrent COMPLETE recheck
- Audit failure rolls back chunk writes
- API 201/200/404/409/503/401
- response/log/Audit do not contain chunk content/vector/API key
- no similarity search or vector index

## Allowed Scope

Product:
- `compose.yaml`
- `.github/workflows/backend-tests.yml`
- `requirements/base.txt`
- `.env.example`
- `app/core/config.py`
- `app/core/errors.py`
- `app/models/knowledge_chunk.py`
- `app/models/__init__.py`
- `app/repositories/knowledge.py`
- `app/repositories/embedding.py`
- `app/services/chunking.py`
- `app/services/embedding.py`
- `app/integrations/__init__.py`
- `app/integrations/embeddings.py`
- `app/schemas/embedding.py`
- `app/api/routes/knowledge.py`
- one new Embedding/pgvector Alembic migration

Tests:
- bounded focused test files in Dispatcher marker
- existing migration/config tests only where required

Supervisor-controlled:
- `docs/PROJECT_STATE.md`
- `README.md`

## Out of Scope

- HNSW
- IVFFlat
- cosine/L2 query endpoint
- nearest-neighbor retrieval
- reranking
- RAG generation
- citations
- LLM generation
- file parsers
- remote source fetch
- background worker/job queue
- retries/backoff
- distributed locks
- automatic destructive re-embedding
- multiple production embedding providers

## Checkpoints

- [x] CP0 — Context bootstrap / contradiction detection
- [x] CP1 — Architecture + Scope validation
- [x] CP2 — Bounded implementation
- [x] CP3 — Targeted + full verification
- [x] CP4 — Security / provider / vector review
- [x] CP5 — Knowledge + documentation sync
- [x] CP6 — PR delivery evidence

## Supervisor Fallback Execution

The authorized CP2 gate was not consumed by a running Local Watcher/Codex Executor.

The Supervisor is therefore performing a bounded fallback implementation on the Feature Branch.

This fallback does **not** bypass:

- the remote CP2 Write Allowlist;
- GitHub-hosted CP3 verification;
- CP4 Security / Provider / Vector review;
- CP5 Knowledge Capture;
- CP6 Delivery Gate.

Branch history must not be represented as a Codex-generated checkpoint unless the Dispatcher actually produced it.

### Scope Expansion — Existing Migration Test

Supervisor review found that `tests/test_knowledge_migration.py` incorrectly assumes the #011 migration must remain the current Alembic head.

Because #012 legitimately adds a successor revision, the test must be changed to validate revision `a61f9b2c3d40` directly rather than asserting it is the head.

This is a bounded regression-test maintenance change; it does not alter #011 Product behavior.

## CP2 Ordered Slices

1. Dependencies + pgvector Docker/CI infrastructure
2. Settings/env validation
3. pgvector migration + KnowledgeChunk model
4. deterministic chunking/config hash
5. provider Protocol + OpenAI adapter
6. repositories
7. EmbeddingService transaction/idempotency flow
8. API response/router integration
9. focused tests

Do not begin #013 vector search/indexing.

## CP3 Verification

At minimum:

```powershell
python -m pytest -q tests/test_config.py tests/test_chunking.py tests/test_embedding_provider.py tests/test_embedding_model.py tests/test_embedding_repository.py tests/test_embedding_service.py tests/test_embedding_api.py tests/test_embedding_migration.py tests/test_migrations.py
python -m pytest -q
```

GitHub-hosted pgvector PostgreSQL/Alembic Backend Verification remains authoritative.

## CP3 Verification Evidence

Initial Draft verification established that:

- pgvector PostgreSQL image boots correctly;
- Alembic upgrade enables the `vector` extension;
- Database Recovery passes;
- Control Plane tests pass.

The first full regression run had one test-only failure in migration introspection: an Alembic `UniqueConstraint` is not yet attached to a Table inside the mocked `op.create_table()` call, so `.columns` is empty. The migration itself was correct. The test was fixed to inspect pending column arguments.

Subsequent exact-head verification passed:

```text
Backend regression: 289 passed
Database recovery:   1 passed
Control Plane:      87 passed
pgvector extension: PASS
Alembic downgrade / re-upgrade: PASS
```

CP4 hardening then added malformed external-provider response tests and service-level Protocol validation.

Final reviewed Product/Test Head:

`95660212a8bce4fcfc15c2545cc8c992c5b83a40`

Final exact-head evidence:

```text
Backend regression: 306 passed
Database recovery:   1 passed
Control Plane:      87 passed
PostgreSQL + pgvector: PASS
Alembic upgrade:     PASS
Alembic downgrade:   PASS
Alembic re-upgrade:  PASS
```

## CP4 Security / Provider / Vector Review

Status: **PASS**

Findings:

- OpenAI API key remains optional at application startup and is only required if the real provider is actually invoked.
- A COMPLETE idempotent embedding state does not call the provider and therefore does not require an API key.
- A MISSING state with no API key fails explicitly at the provider boundary.
- OpenAI SDK-specific code is isolated in `app/integrations/embeddings.py`.
- Service Layer depends on an SDK-independent Provider Protocol.
- Provider request explicitly sets model, dimensions=1536, and `encoding_format="float"`.
- Provider output count, indexes, vector dimensions, numeric finiteness, required fields, and integer token usage are validated.
- Malformed provider responses fail closed as domain errors rather than leaking AttributeError/TypeError/ValueError.
- Service independently validates Provider Protocol results, including dimensions, finite numeric values, and token usage type.
- Automated tests use Fake/Mock providers and clients; no live OpenAI request is made.
- Initial DB read transaction is explicitly ended before any external provider wait.
- Provider failure creates no KnowledgeChunk rows and no success Audit Event.
- COMPLETE state skips the provider.
- PARTIAL / inconsistent state fails closed.
- After provider return, persisted state is re-read to handle concurrent completion.
- Database uniqueness prevents duplicate chunk sets for the same document/config.
- New KnowledgeChunk rows + Audit Event commit atomically.
- Audit failure rolls back chunk persistence.
- API response excludes chunk text and vectors.
- Audit metadata and runtime logs exclude chunk text, vectors, API key, and raw provider response.
- pgvector storage is `vector(1536)` in both ORM model and migration.
- No HNSW / IVFFlat vector index exists.
- No cosine/L2/nearest-neighbor retrieval query exists.
- No Retrieval, Reranking, RAG, Citation, or LLM-generation path was introduced.
- Migration downgrade removes the feature table/index but does not destructively DROP the shared vector extension.
- Development Compose and GitHub Backend Verification use the same pinned pgvector PostgreSQL image.

No merge-blocking finding remains.

## CP4 Review Focus

- no API key/content/vector leakage
- provider data boundary is explicit
- real OpenAI is never called from tests
- read transaction is closed before external call
- provider failure produces zero new DB rows
- partial DB state fails closed
- sequential idempotency skips provider
- concurrent persistence stays duplicate-free
- Audit + chunks commit atomically
- vector dimensions exactly 1536
- no vector search or vector index exists
- model/migration/CI/compose agree on pgvector

## CP5 Knowledge / Documentation

Notion deduplication was completed before writing.

Existing pages already mention Embedding, Chunking and pgvector at glossary/interview level, but no page covered the complete Engineering boundary delivered by #012.

Created one reusable Engineering Encyclopedia entry:

**Embedding Pipeline：External Provider Boundary、Deterministic Chunking、pgvector 與 Transaction Boundary**

Created one project Work Log:

**Issue #012 — Embedding Pipeline Foundation**

Captured reusable concepts include:

- Embedding Pipeline is separate from Retrieval / RAG.
- External AI Provider calls introduce a new data-processing boundary.
- Provider SDK code belongs behind an integration adapter / Protocol.
- Deterministic Chunking + canonical Config Hash make persisted vectors reproducible.
- DB read transactions should not remain open during external API waits.
- Provider return requires a DB re-check for concurrent completion.
- Database uniqueness is still the final idempotency correctness backstop.
- Provider output is untrusted input and must be shape/type/dimension validated.
- Missing provider credentials should fail at the capability boundary, not global app startup.
- pgvector storage and vector indexing/query design are separate concerns.
- Automated tests should use Fake/Mock providers; real vector storage should be verified against PostgreSQL+pgvector.

## Knowledge Candidates

Deduplicate in CP5:

- Embedding Pipeline vs Retrieval
- External AI Provider Boundary
- Deterministic Chunking
- Embedding Configuration Identity
- pgvector storage vs vector indexing
- DB Transaction Boundary around external API calls

## Current State

Engineering Issue #012 is complete and ready for Delivery.

Final reviewed Product/Test Head before CP5 documentation:

- `95660212a8bce4fcfc15c2545cc8c992c5b83a40`
- Backend regression: **306 passed**
- Database recovery: **1 passed**
- Dispatcher / Branch Resolver: **87 passed**
- PostgreSQL + pgvector extension: PASS
- Alembic upgrade/downgrade/re-upgrade: PASS
- CP4 Security / Provider / Vector Review: PASS
- CP5 Notion Knowledge Capture: complete
- README / Project State synchronization: complete

Documentation-inclusive CP5 Head also passed:

- Backend regression: **306 passed**
- Database recovery: **1 passed**
- Dispatcher / Branch Resolver: **87 passed**

Supervisor approval marker: **CP6**.

The final non-Draft Delivery PR must run exact-head GitHub-hosted verification before Merge.

No known merge-blocking finding remains.
