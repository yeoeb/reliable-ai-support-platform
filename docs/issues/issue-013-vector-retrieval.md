# Engineering Issue #013 — Exact Vector Retrieval Foundation

<!-- codex-dispatch-supervisor-approved-through: CP6 -->
<!-- codex-dispatch-write-allow: ["app/core/errors.py","app/schemas/retrieval.py","app/repositories/retrieval.py","app/services/retrieval.py","app/api/routes/retrieval.py","app/main.py","migrations/versions/*retrieval*.py","tests/test_retrieval_schema.py","tests/test_retrieval_repository.py","tests/test_retrieval_service.py","tests/test_retrieval_api.py","tests/test_retrieval_migration.py","tests/integration/test_vector_retrieval.py","tests/test_embedding_migration.py","tests/test_migrations.py","docs/issues/issue-013-vector-retrieval.md"] -->

## GitHub Tracking

- GitHub Issue: #60
- Engineering Issue ID: #013
- Branch: `feature/issue-013-vector-retrieval`

## Goal

Add the first authorized exact Vector Retrieval boundary over persisted KnowledgeChunk embeddings.

V1 performs:

- bounded query validation;
- one query embedding through the existing EmbeddingProvider abstraction;
- exact pgvector cosine search;
- current-config filtering;
- provenance-rich retrieval results;
- knowledge-read RBAC;
- best-effort read Audit;
- safe structured runtime logging.

No RAG generation or approximate vector index is included.

## Required Reading

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #60
- `app/models/knowledge_chunk.py`
- `app/models/knowledge_document.py`
- `app/integrations/embeddings.py`
- `app/services/chunking.py`
- `app/services/embedding.py`
- `app/services/audit.py`
- `app/api/dependencies/authorization.py`
- `migrations/versions/b72a4c5d6e81_add_embedding_chunks.py`

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. #012 stores deterministic KnowledgeChunk rows with `vector(1536)`.
2. #012 deliberately introduced no vector similarity query or ANN index.
3. Current embeddings are identified by `embedding_config_hash`.
4. Historical embedding configurations may coexist, so Retrieval must filter current config.
5. Existing `knowledge:manage` is admin-only and is inappropriate for support read access.
6. Baseline `support_agent` and `admin` role UUIDs are stable in migration history.
7. Default `user` role has no knowledge permission.
8. Existing OpenAI EmbeddingProvider can embed a query without persistence.
9. Existing provider validation already rejects malformed output, but RetrievalService still owns a provider-independent result check.
10. AuditService `record_best_effort()` commits its own Audit record and swallows SQLAlchemy persistence failures.
11. Structured Logging already excludes Request body/query string at the HTTP middleware level.
12. pgvector 0.8.6 supports exact cosine distance search with `<=>`; exact search is default and provides perfect recall.
13. HNSW/IVFFlat introduce approximate recall/speed tradeoffs and are not required to establish the first correctness contract.

No architecture contradiction was found.

## CP1 — Architecture / Scope Validation

Status: **completed and approved by Supervisor**

### 1. Retrieval Correctness Strategy

V1 uses **exact cosine nearest-neighbor search**.

Reason:

- deterministic ranking is easier to test and evaluate;
- exact pgvector search establishes a correctness baseline;
- approximate HNSW/IVFFlat should be introduced only after a retrieval evaluation dataset exists.

Do not create HNSW/IVFFlat in #013.

### 2. Permission Model

Add:

```text
knowledge:read
```

Stable permission UUID:

```text
b4444444-4444-4444-8444-444444444444
```

Grant to:

- `support_agent`
- `admin`

Do not grant to:

- default `user`

This API exposes raw internal KnowledgeChunk content.

End-user RAG access is a separate #014 policy decision.

### 3. Migration

New migration revises:

```text
b72a4c5d6e81
```

Upgrade:

1. create B-tree index:
   `ix_knowledge_chunks_embedding_config_hash`
2. insert `knowledge:read` Permission
3. grant to support_agent and admin

Downgrade:

1. remove support/admin RolePermission rows
2. remove Permission
3. drop B-tree index

Do not change:

- vector column
- pgvector extension
- KnowledgeChunk contents
- #012 Unique Constraint

Do not create:

- HNSW
- IVFFlat
- `vector_cosine_ops` index

### 4. Query Schema

Create:

`KnowledgeSearchRequest`

Fields:

- `query: str`
- `top_k: int = 5`
- `min_similarity: float = 0.0`

Rules:

- raw query length <= 2000 before trimming;
- outer whitespace stripped after raw-length check;
- final query length >= 1;
- `top_k` 1..20;
- `min_similarity` 0.0..1.0;
- extra fields forbidden.

The raw-length check must use a `mode="before"` validator so outer whitespace cannot bypass the size cap.

### 5. Result Schema

Each result:

- `chunk_id: UUID`
- `document_id: UUID`
- `document_title: str`
- `source_type: str`
- `source_name: str`
- `chunk_index: int`
- `content: str`
- `similarity: float`

Response envelope:

- `results`
- `result_count`
- `embedding_model`
- `embedding_dimensions`
- `token_usage`

Do not return:

- query vector
- stored embedding
- API key
- raw provider response
- internal distance value
- embedding_config_hash unless debugging evidence later requires it

### 6. Current Pipeline Configuration

Use existing `build_embedding_pipeline_config(...)` with:

- provider_name from Provider
- current configured chunk size
- current configured overlap
- current embedding model
- current dimensions

Use its `config_hash` as the Retrieval filter.

This prevents mixing embeddings generated under historical configuration.

### 7. Query Embedding

RetrievalService calls:

```python
provider.embed([query])
```

Before any Repository/DB read.

Service independently validates:

- exactly one vector;
- dimension exactly 1536/current configured dimension;
- finite numeric values;
- integer non-negative token usage.

The query vector is ephemeral and is never persisted.

### 8. DB Transaction / External Call Boundary

Approved order:

```text
Pydantic validates query
    ↓
build current config identity (pure)
    ↓
provider.embed([query])
    ↓
validate vector locally
    ↓
repository exact search
    ↓
materialize results
    ↓
best-effort Audit commit
    ↓
runtime log
    ↓
return
```

Do not issue a DB query before the external provider call.

This avoids holding a DB transaction during network wait.

### 9. Retrieval Repository

Create immutable DTO `RetrievalRow`.

Repository method:

```text
search_exact_cosine(
    query_vector,
    embedding_config_hash,
    top_k,
    min_similarity
)
```

SQLAlchemy expression:

```text
distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
```

Required query shape:

- join KnowledgeDocument on document_id;
- filter current `embedding_config_hash`;
- filter `distance <= 1.0 - min_similarity`;
- order by `distance ASC`;
- deterministic tie-breaker:
  `KnowledgeChunk.id ASC`;
- `LIMIT top_k`.

Return DTO contains the distance or precomputed similarity internally; API exposes similarity only.

Repository owns no Commit/Rollback.

### 10. Similarity Conversion

For each row:

```text
similarity = 1.0 - cosine_distance
```

Clamp floating-point presentation to:

```text
[-1.0, 1.0]
```

Do not reinterpret cosine distance itself as a similarity score.

### 11. Empty Result

No matching chunk is not an error.

Return:

```json
{
  "results": [],
  "result_count": 0,
  ...
}
```

HTTP 200.

### 12. Service Errors

Provider errors:
- propagate existing EmbeddingProviderError domain types;
- API -> generic 503 `Embedding service unavailable`.

SQLAlchemy retrieval failure:
- rollback Session;
- raise `PersistenceUnavailableError`;
- API -> generic 503 `Persistence service unavailable`.

Do not expose SQL/provider exception text.

### 13. Best-Effort Read Audit

After successful result materialization:

```text
action=knowledge.search
target_type=knowledge
target_id=<current config hash>
outcome=success
```

Use `record_best_effort()`.

Safe metadata:

- top_k
- min_similarity
- result_count
- embedding_model
- embedding_dimensions
- token_usage

Exclude:

- query
- result content
- document title
- source_name
- vectors
- API key

Audit failure must not suppress a valid Retrieval response.

### 14. Runtime Log

After best-effort Audit:

```text
event=knowledge.search.completed
```

Safe fields:

- result_count
- top_k
- min_similarity
- embedding_model
- embedding_dimensions
- token_usage

Do not log:

- query
- content
- source_name
- vector
- API key

### 15. API

New router:

```text
POST /knowledge/search
```

Permission:

```text
knowledge:read
```

Not under `/admin`, because support_agent is allowed.

Route constructs the existing OpenAIEmbeddingProvider using Settings and injects into RetrievalService.

### 16. Integration Test

Add a real PostgreSQL+pgvector test that inserts deterministic vectors and proves:

- cosine ranking order;
- config-hash filtering;
- top_k;
- similarity threshold;
- provenance join;
- vectors are not returned by repository DTO.

Use direct deterministic test vectors.

Do not call OpenAI in the integration test.

### 17. Security Boundary

Returned KnowledgeChunk content is untrusted data.

#013 does not:

- feed it to an LLM;
- render it as trusted HTML;
- execute instructions inside it;
- call tools based on it.

That transition belongs to #014 RAG and must reassert prompt-injection boundaries.

## Allowed Scope

Product:

- `app/core/errors.py`
- `app/schemas/retrieval.py`
- `app/repositories/retrieval.py`
- `app/services/retrieval.py`
- `app/api/routes/retrieval.py`
- `app/main.py`
- one Retrieval migration

Tests:

- `tests/test_retrieval_schema.py`
- `tests/test_retrieval_repository.py`
- `tests/test_retrieval_service.py`
- `tests/test_retrieval_api.py`
- `tests/test_retrieval_migration.py`
- `tests/integration/test_vector_retrieval.py`
- `tests/test_migrations.py` only if head assumptions require maintenance

Supervisor-controlled:

- `docs/PROJECT_STATE.md`
- `README.md`

## Out of Scope

- HNSW
- IVFFlat
- ANN tuning
- hybrid search
- FTS
- reranking
- cross-encoder
- query rewriting
- RAG/LLM answer
- citations
- end-user raw retrieval
- document ACLs
- caching

## Checkpoints

- [x] CP0 — Context bootstrap / contradiction detection
- [x] CP1 — Architecture + Scope validation
- [x] CP2 — Bounded implementation
- [x] CP3 — Targeted + full verification
- [x] CP4 — Security / retrieval review
- [x] CP5 — Knowledge + documentation sync
- [x] CP6 — PR delivery evidence

## Supervisor Fallback Execution

The authorized CP2 gate was not consumed by a running Local Watcher/Codex Executor.

The Supervisor is therefore performing a bounded fallback implementation on the Feature Branch.

This fallback does **not** bypass:

- the remote CP2 Write Allowlist;
- GitHub-hosted CP3 verification;
- CP4 Security / Retrieval review;
- CP5 Knowledge Capture;
- CP6 Delivery Gate.

The latest repository control-plane rule against delivery-evidence CI retrigger loops remains authoritative.

Branch history must not be represented as a Codex-generated checkpoint unless the Dispatcher actually produced it.

### Scope Expansion — Embedding Migration Regression Test

`tests/test_embedding_migration.py` incorrectly assumes #012 must remain the current Alembic head.

#013 legitimately adds a successor revision, so that test is authorized for bounded maintenance: validate revision `b72a4c5d6e81` directly and keep the parent/pgvector contract, without asserting it is the latest head.

No #012 Product behavior changes.

## CP2 Ordered Slices

1. permission/index migration
2. request/result schemas
3. exact cosine repository
4. RetrievalService provider/DB/audit boundaries
5. route + application wiring
6. focused unit/API tests
7. real pgvector integration test

## CP3 Verification

Targeted:

```powershell
python -m pytest -q tests/test_retrieval_schema.py tests/test_retrieval_repository.py tests/test_retrieval_service.py tests/test_retrieval_api.py tests/test_retrieval_migration.py tests/integration/test_vector_retrieval.py tests/test_migrations.py
```

Then full regression:

```powershell
python -m pytest -q
```

GitHub-hosted pgvector PostgreSQL remains authoritative.

## CP3 Verification Evidence

Final reviewed Product/Test Head after CP4 hardening:

`5b48e61c27f1085f2409270290a1f4f4aabd92c7`

GitHub-hosted exact-head verification:

```text
Backend regression: 344 passed
Database recovery:   1 passed
Control Plane:      87 passed
PostgreSQL + pgvector extension: PASS
Alembic upgrade head:            PASS
Alembic downgrade -1:            PASS
Alembic re-upgrade head:         PASS
```

The first CP3 run reached **342 passed / 1 failed**.

The only failure was integration-test setup ordering: KnowledgeChunk children were flushed before their KnowledgeDocument parent because the test did not establish an ORM relationship dependency. The test fixture now explicitly flushes the parent Document before adding child Chunks. Product Model/Repository behavior was not weakened.

## CP4 Security / Retrieval Review

Status: **PASS**

Review findings:

- raw Retrieval is protected by dedicated `knowledge:read`;
- migration grants it only to `support_agent` and `admin`;
- default `user` is not granted raw chunk access;
- query raw length is bounded before trimming;
- query is sent to the existing EmbeddingProvider boundary only when search is invoked;
- query text and query vector are not persisted;
- OpenAI/API-provider failures map to generic 503 through existing domain errors;
- current `embedding_config_hash` filters out historical embedding configurations;
- exact pgvector cosine distance is used;
- threshold is applied as `distance <= 1 - min_similarity` before LIMIT;
- ordering is cosine distance ASC then Chunk UUID ASC;
- repository returns provenance + chunk content and never vector data;
- empty result sets are successful;
- best-effort read Audit excludes query/content/source/vector/API-key data;
- runtime logs exclude query/content/source/vector/API-key data;
- no HNSW, IVFFlat, ANN, reranking, LLM, or RAG execution path exists;
- the only new index is a normal B-tree on `embedding_config_hash`.

### CP4 hardening

Two correctness boundaries were corrected:

1. **RBAC transaction before Provider wait** — the authorization dependency performs a DB permission read using the same request Session. RetrievalService now explicitly closes that read transaction with `session.rollback()` before waiting on the external Embedding Provider.
2. **Zero query vector** — cosine similarity is undefined for an all-zero query vector. RetrievalService now rejects zero-norm Provider output as `InvalidEmbeddingProviderResponseError` before any search query.

No merge-blocking finding remains.

## CP4 Review Focus

- query/API key/vector leakage
- query provider happens before DB query
- current config filtering
- exact cosine semantics
- threshold correctness
- deterministic tie-breaking
- raw support/admin authorization only
- best-effort Audit behavior
- no ANN index
- no RAG/LLM execution path

## CP5 Knowledge / Documentation

Notion deduplication was completed before writing.

Existing Glossary / Embedding / Audit pages already define individual terms and adjacent boundaries, so #013 does not create separate duplicate pages for Cosine Similarity, Audit, or Vector Search vocabulary.

Created one deeper reusable Engineering Encyclopedia entry:

**Exact Vector Retrieval：Cosine Distance、Config Consistency、Read Boundary 與 Untrusted Context**

Created one linked project Work Log:

**Issue #013 — Exact Vector Retrieval Foundation**

Reusable concepts captured:

- Exact Vector Search is the correctness baseline before ANN optimization.
- Cosine Distance and Cosine Similarity are distinct; V1 exposes `similarity = 1 - distance`.
- Similarity threshold must be translated into a distance predicate before LIMIT.
- Stable tie-breaking improves Regression Test and Evaluation reproducibility.
- Retrieval must filter the current `embedding_config_hash` and must not mix historical vector configurations.
- Query Embeddings are ephemeral and must remain outside persistence/logging/Audit content.
- Zero-norm query vectors fail closed because cosine similarity is undefined.
- A prior RBAC DB read may already have opened the shared request Session transaction, so the read transaction must be explicitly closed before external Provider wait.
- `knowledge:read` is separate from `knowledge:manage` to preserve least privilege.
- High-frequency reads may use best-effort Audit when a failed Audit write should not turn a valid read into an outage.
- Retrieved Chunk content remains untrusted context and must not become an authorization/tool-execution instruction.

## Knowledge Candidates

Deduplicate in CP5:

- Exact vs Approximate Vector Search
- Cosine Distance vs Similarity
- Retrieval Configuration Consistency
- Query Embedding Boundary
- Read Audit vs Mutation Audit
- Retrieval Result as Untrusted Context

## Current State

Engineering Issue #013 is complete and ready for Delivery.

Final reviewed Product/Test Head before CP5 documentation:

- `5b48e61c27f1085f2409270290a1f4f4aabd92c7`
- Backend regression: **344 passed**
- Database recovery: **1 passed**
- Dispatcher / Branch Resolver: **87 passed**
- PostgreSQL + pgvector extension: PASS
- Alembic upgrade/downgrade/re-upgrade: PASS
- CP4 Security / Retrieval Review: PASS
- CP5 Notion Knowledge Capture: complete
- README / Project State synchronization: complete

Supervisor approval marker: **CP6**.

Per the repository Final CI policy, this execution note will not be changed after the final exact-Head verification. Final CI SHA / run / test evidence must be recorded in the Pull Request / GitHub Issue comments without mutating the verified Branch Head.

The final Delivery PR must pass exact-Head GitHub-hosted verification before Merge.

No known merge-blocking finding remains.
