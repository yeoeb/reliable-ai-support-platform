# Engineering Issue #011 — Knowledge Document Ingestion Foundation

<!-- codex-dispatch-supervisor-approved-through: CP4 -->
<!-- codex-dispatch-write-allow: ["app/models/knowledge_document.py","app/models/__init__.py","app/repositories/knowledge.py","app/services/knowledge.py","app/schemas/knowledge.py","app/api/routes/knowledge.py","app/main.py","app/core/errors.py","migrations/versions/*knowledge*.py","tests/test_knowledge_model.py","tests/test_knowledge_repository.py","tests/test_knowledge_service.py","tests/test_knowledge_api.py","tests/test_knowledge_migration.py","tests/test_migrations.py","docs/issues/issue-011-knowledge-ingestion.md"] -->

## GitHub Tracking

- GitHub Issue: #50
- Engineering Issue ID: #011
- Branch: `feature/issue-011-knowledge-ingestion`

## Goal

Create a durable, RBAC-protected ingestion boundary for normalized plain-text / Markdown knowledge documents.

This Issue stops **before** chunking, embeddings, Vector Search, RAG, file parsing, remote fetch, or LLM usage.

## Required Reading

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #50
- `app/db/base.py`
- `app/models/audit_event.py`
- `app/models/permission.py`
- `app/models/role_permission.py`
- `app/repositories/rbac.py`
- `app/repositories/audit.py`
- `app/services/audit.py`
- `app/api/routes/admin.py`
- `app/api/dependencies/authorization.py`
- current Alembic head and migration tests

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. Current schema head is the Audit Event migration after baseline RBAC.
2. `Base` uses SQLAlchemy DeclarativeBase and naming conventions.
3. RBAC currently has `users:read` and `rbac:manage`; there is no Knowledge permission.
4. Admin-only operations use `require_permission(...)`.
5. Audit Repository uses `add + flush` and does not Commit.
6. Service Layer owns transaction Commit/Rollback.
7. Structured runtime logging is available and Request Correlation is already implemented.
8. There is no existing Knowledge/RAG/Embedding/Vector code.
9. No multipart/file-parser/pgvector dependency is required for V1.
10. The existing architecture supports atomic Document + Audit persistence in one SQLAlchemy Session.

No contradiction with merged architecture was found.

## CP1 — Architecture / Scope Validation

Status: **completed and approved by Supervisor**

### 1. Data Model

Create `KnowledgeDocument`:

- `id: UUID` primary key
- `title: String(200)`
- `source_type: String(20)`
- `source_name: String(255)`
- `content: Text`
- `content_hash: String(64)`
- `created_by_user_id: UUID`
- `created_at: DateTime(timezone=True)`

Do not create a Foreign Key from `created_by_user_id` to `users`.

Reason: provenance should survive later User deletion/retention changes, similar to the durable Audit actor snapshot approach.

Add a Unique Constraint on:

```text
(source_name, content_hash)
```

This is the database idempotency backstop.

Do not add:
- chunks
- embedding/vector columns
- document status workflow
- update/delete/version fields

### 2. Input Schema

`KnowledgeDocumentCreate`:

- `title`: 1..200, strip outer whitespace
- `source_type`: exactly `text | markdown`
- `source_name`: 1..255, strip outer whitespace
- `content`: 1..100000 characters before Service normalization
- `extra="forbid"`

Constant:

```text
MAX_KNOWLEDGE_CONTENT_CHARS = 100_000
```

Keep the limit close to the schema/normalization code and test both accepted maximum and rejected maximum+1.

### 3. Normalization + Hash

Service normalization:

```python
content.replace("\r\n", "\n").replace("\r", "\n").strip()
```

If result is empty:

- raise a dedicated `InvalidKnowledgeContentError`
- API translates to HTTP 422

Hash:

```text
sha256(normalized_content.encode("utf-8")).hexdigest()
```

Hash only normalized content.

Do not alter internal whitespace, Markdown syntax, Unicode normalization, or semantics in #011.

### 4. Repository Contract

`KnowledgeRepository` may:

- `get_by_source_name_and_hash(...)`
- `create(...)`

Create behavior:

- instantiate model
- `session.add`
- `session.flush`
- return entity

Repository must never Commit/Rollback.

### 5. Idempotent Service Contract

`KnowledgeService.ingest(...)` returns an explicit result object or tuple carrying:

- document
- `changed: bool`

Flow:

```text
normalize
    ↓
hash
    ↓
find source_name + hash
    ├─ existing -> changed=false
    └─ absent   -> create -> changed=true
    ↓
AuditService.record(...)
    ↓
single session.commit()
    ↓
structured runtime log
    ↓
return document + changed
```

Duplicate requests still produce an Audit Event because an administrator performed an ingestion action.

Audit metadata includes:

- `source_type`
- `content_hash`
- `content_length`
- `changed`

It must not include:
- content
- title
- source_name

### 6. Transaction Boundary

For both new and duplicate ingestion:

- Audit is in the same SQLAlchemy transaction used by the service.
- only Service calls Commit.
- any SQLAlchemy persistence failure -> Rollback once and raise `PersistenceUnavailableError`.
- Audit failure must prevent a newly created KnowledgeDocument from being committed.

Do not use `record_best_effort()` here.

Use transaction-participating `AuditService.record()`.

### 7. Runtime Log Contract

After successful Commit:

```text
event=knowledge.document.ingested
```

Structured safe fields only:

- `document_id`
- `source_type`
- `content_length`
- `changed`

Do not emit:
- `content`
- `title`
- `source_name`
- `content_hash` in runtime log (not necessary operationally)
- request body

### 8. RBAC Permission

Add:

```text
knowledge:manage
```

Grant to `admin` only.

Migration must be deterministic and reversible.

Use a stable UUID constant in the migration, following the existing baseline RBAC seed style.

Downgrade must:
1. remove admin RolePermission for `knowledge:manage`
2. remove the Permission
3. drop KnowledgeDocument table/indexes/constraints

or reverse the actual creation order safely.

The migration must preserve one Alembic head.

### 9. API

Create a dedicated router:

```text
POST /admin/knowledge/documents
```

Authorization:

```python
require_permission("knowledge:manage")
```

Do not piggyback on `rbac:manage`.

Response must not contain content.

Response model:

- id
- title
- source_type
- source_name
- content_hash
- created_at
- changed

Use a deterministic status contract:

- HTTP 201 when `changed=true`
- HTTP 200 when the same source_name + normalized content hash already exists

Implement this explicitly rather than always claiming a new resource was created.

### 10. Error Mapping

- invalid normalized content -> 422
- validation errors -> FastAPI/Pydantic 422
- persistence unavailable -> 503
- authorization handled by existing 401/403 dependencies

Do not expose SQL exception detail.

### 11. Untrusted Knowledge Boundary

Stored content remains data only.

#011 must not:
- execute it
- render it as HTML
- feed it to LLM
- use it as Prompt/System instructions
- follow URLs/links inside it
- open source_name as path
- fetch network resources

### 12. Allowed Scope

Product:
- `app/models/knowledge_document.py`
- `app/models/__init__.py`
- `app/repositories/knowledge.py`
- `app/services/knowledge.py`
- `app/schemas/knowledge.py`
- `app/api/routes/knowledge.py`
- `app/main.py`
- `app/core/errors.py`
- one Alembic migration containing KnowledgeDocument + permission/grant

Tests:
- model
- repository
- service
- API/RBAC
- migration/schema
- regression

Supervisor-controlled only:
- `docs/PROJECT_STATE.md`
- `README.md`

### 13. Out of Scope

- PDF / DOCX / Excel / OCR
- Multipart file upload
- Remote URL fetch
- Chunking
- Tokenization
- Embedding
- pgvector
- Vector index
- Retrieval
- RAG
- Citations
- LLM
- Prompt Injection execution/filtering
- Document update/delete/versioning
- External storage

## Checkpoints

- [x] CP0 — Context bootstrap / contradiction detection
- [x] CP1 — Architecture + Scope validation
- [x] CP2 — Bounded implementation
- [x] CP3 — Targeted + full verification
- [x] CP4 — Security / ingestion review
- [ ] CP5 — Knowledge + documentation sync
- [ ] CP6 — PR delivery evidence

## Supervisor Fallback Execution

The authorized CP2 gate was not consumed by a running Local Watcher/Codex Executor.

The Supervisor is therefore performing a bounded fallback implementation on the Feature Branch.

This does not bypass:
- the existing CP2 Write Scope;
- GitHub-hosted CP3 verification;
- CP4 Security / Ingestion review;
- CP5 Knowledge Capture;
- CP6 Delivery Gate.

Branch history must not be represented as a Codex-generated checkpoint unless the Dispatcher actually produced it.

## CP2 Ordered Slices

1. Model + migration
2. Knowledge permission + admin grant
3. schemas + normalization/hash service
4. repository + transaction semantics
5. Audit integration
6. structured runtime event
7. admin route + main wiring
8. focused tests

Do not begin chunking/embedding.

## CP3 Verification Contract

Targeted:

```powershell
python -m pytest -q tests/test_knowledge_model.py tests/test_knowledge_repository.py tests/test_knowledge_service.py tests/test_knowledge_api.py tests/test_knowledge_migration.py tests/test_migrations.py
```

Then full regression:

```powershell
python -m pytest -q
```

GitHub-hosted PostgreSQL/Alembic Backend Verification is authoritative.

## CP2 / CP3 Verification Evidence

CP2 was implemented through the recorded bounded Supervisor fallback.

Initial GitHub-hosted verification:

```text
232 passed, 1 failed
```

The single failure was a Test Contract mismatch: Pydantic `str_strip_whitespace=True` rejects whitespace-only content before the Service executes. Product validation was preserved; the test was corrected to assert the framework-level 422 boundary.

Second exact-head verification:

```text
Backend regression: 233 passed
Database recovery:   1 passed
Control Plane:      87 passed
Alembic round-trip: PASS
```

CP4 then found a real input-boundary gap: Pydantic trimming could reduce oversized raw content before `max_length` validation.

Bounded hardening added:

- a `mode="before"` raw content length validator;
- a whitespace-bypass negative test;
- an exact 100,000-character acceptance test.

Final reviewed Product/Test Head:

`6f1e2a468e09991efd859ceb815ae45964a5aeaf`

Final exact-head evidence:

```text
Backend regression: 235 passed
Database recovery:   1 passed
Control Plane:      87 passed
PostgreSQL 16:       PASS
Alembic upgrade:     PASS
Alembic downgrade:   PASS
Alembic re-upgrade:  PASS
```

## CP4 Security / Ingestion Review

Status: **PASS**

Findings:

- Knowledge content remains stored untrusted data only.
- No PDF/DOCX/Excel/OCR parser exists.
- No filesystem open, remote URL fetch, HTTP client, LLM, Embedding, pgvector, Retrieval, or RAG path was introduced.
- `source_name` remains a logical provenance label only.
- `knowledge:manage` uses a dedicated stable Permission and is granted only to the stable admin Role UUID in the migration.
- Repository owns no Commit/Rollback.
- Service owns the single transaction boundary.
- New KnowledgeDocument + Audit Event commit atomically.
- Audit failure rolls back a newly-created document.
- duplicate `source_name + normalized content_hash` is idempotent and still audited with `changed=false`.
- PostgreSQL Unique Constraint is the concurrency backstop; SAVEPOINT recovery handles duplicate insert races.
- Audit metadata excludes document content, title, and source_name.
- Runtime success/failure logs exclude document content, title, and source_name.
- API success response excludes document content.
- raw content is capped at 100,000 characters before trimming/normalization can reduce it.
- exact 100,000 characters are accepted; oversized content is rejected.
- model and migration remain aligned.
- one linear Alembic head is preserved.

No merge-blocking finding remains.

## CP4 Review Focus

- content/provenance never enters logs/audit unexpectedly
- permission is admin-only
- idempotency works under DB unique backstop
- Repository owns no commit
- Audit failure rolls back new document
- response excludes content
- no fetch/execute/LLM path exists
- model/migration alignment

## Knowledge Candidates

Deduplicate in CP5:

- Knowledge Ingestion vs Embedding
- Content normalization + deterministic hashing
- Provenance
- Idempotent ingestion / content-addressed identity
- Untrusted document boundary

## Current State

CP0–CP4 are complete.

Final reviewed Product/Test Head:

- `6f1e2a468e09991efd859ceb815ae45964a5aeaf`
- Backend regression: **235 passed**
- Docker Compose database recovery: **1 passed**
- Dispatcher / Branch Resolver: **87 passed**
- PostgreSQL 16 + Alembic upgrade/downgrade/re-upgrade: PASS
- CP4 Security / Ingestion Review: PASS

Supervisor approval marker: **CP4**.

Next action: CP5 Knowledge / Documentation synchronization.

No further Product Code change is authorized unless a new verification failure is discovered.
