# Engineering Issue #014 — Grounded RAG Response with Evidence Citations

<!-- codex-dispatch-supervisor-approved-through: CP2 -->
<!-- codex-dispatch-write-allow: ["app/integrations/llm.py","app/services/rag.py","app/schemas/rag.py","app/api/routes/rag.py","app/core/config.py","app/core/errors.py","app/main.py","tests/test_rag_*.py","tests/test_config.py","docs/issues/issue-014-rag-grounded-answer.md"] -->

## GitHub Tracking

- GitHub Issue: #65
- Engineering Issue ID: #014
- Branch: `feature/issue-014-rag-grounded-answer`

## Goal

Add a bounded, grounded RAG answer boundary on top of the completed exact Retrieval foundation.

The server must retrieve evidence, call an explicit generation Provider, validate the model's source references against the actual retrieved set, and construct citations from server-owned provenance.

## Dependencies

Completed:

- #009 Durable Security Audit Trail
- #010 Structured Logging / Request Correlation
- #011 Knowledge Ingestion
- #012 Embedding Pipeline
- #013 Exact Retrieval / Vector Search
- exact-Head Final CI policy

## Required Reading

Before CP2 edits:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #65
- this execution note
- `app/api/routes/retrieval.py`
- `app/services/retrieval.py`
- `app/repositories/retrieval.py`
- `app/schemas/retrieval.py`
- `app/integrations/embeddings.py`
- `app/services/audit.py`
- `app/api/dependencies/authorization.py`
- `app/core/config.py`
- `app/core/errors.py`
- `app/main.py`
- focused Retrieval/Auth/Logging tests

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. `POST /knowledge/search` already enforces `knowledge:read`.
2. Retrieval already returns stable provenance and content without exposing vectors.
3. Retrieval query embeddings are ephemeral.
4. Retrieval Audit / Runtime Logs already exclude raw query and result content.
5. Retrieval currently uses exact cosine similarity and current embedding-pipeline config.
6. `RetrievalService.search()` closes the authorization/read transaction before waiting on the query Embedding Provider.
7. After Retrieval/database work, #014 must again ensure no shared request DB transaction remains open while waiting on the generation Provider.
8. No LLM/generation Provider abstraction exists yet; only the Embedding Provider exists under `app/integrations/`.
9. Existing OpenAI API key configuration can be reused as secret material; generation-specific settings must not hardcode secrets.
10. No conversation, chat-history, Tool Calling, or Human Approval layer exists yet.
11. Raw Retrieval access is support_agent/admin through `knowledge:read`; #014 must not broaden that policy implicitly.
12. Retrieved KnowledgeChunk content is explicitly untrusted context by project invariant.

No contradiction was found between current `develop`, #013 Retrieval behavior, AGENTS rules, and the #014 Product boundary.

## CP1 — Architecture / Plan

Status: **completed and approved by Supervisor**

### API Boundary

Add:

```text
POST /knowledge/answer
```

V1 uses the same `knowledge:read` dependency as raw Retrieval.

Do not introduce a broader user-facing permission until document-level access policy is designed.

### Request

Use a dedicated RAG request schema:

- `question`
- `top_k`
- `min_similarity`

Reuse/aligned bounds from `KnowledgeSearchRequest`.

Reject extra fields.

### Response

Suggested shape:

```text
status: grounded | insufficient_evidence
answer: string
citations: list[RagCitation]
model: string | null
input_tokens: int
output_tokens: int
```

Citation is server-built and may expose only stable Retrieval provenance:

- `source_id`
- `chunk_id`
- `document_id`
- `document_title`
- `source_type`
- `source_name`
- `chunk_index`
- `similarity`
- `content` (authorized evidence content)

Never expose embeddings/vectors.

### Server Source IDs

After Retrieval:

```text
results[0] → S1
results[1] → S2
...
```

The Provider may only return source IDs.

It must not be trusted to produce:

- document IDs
- chunk IDs
- source names
- URLs
- titles
- raw citation metadata

The Service maps valid IDs back to the authoritative Retrieval objects.

### LLM Provider Abstraction

Create `app/integrations/llm.py`.

Suggested types:

```text
GroundedSource
  source_id
  content

GroundedAnswerProviderResult
  answerable
  answer
  cited_source_ids
  input_tokens
  output_tokens

GroundedAnswerProvider (Protocol)
  provider_name
  generate(question, sources) -> result

OpenAIGroundedAnswerProvider
```

Provider owns OpenAI SDK syntax and response parsing.

Service does not import/use the OpenAI client directly.

### OpenAI Boundary

Use current Responses API + Structured Outputs / JSON Schema.

Current CP1 reference point:

- model default: `gpt-5.6-terra`
- model is configurable
- bounded max output tokens
- no hosted tools
- no Web Search
- no File Search
- no function/tool definitions
- no automatic actions

Do not assume arbitrary SDK syntax. Inspect the installed OpenAI package/API behavior and isolate it behind Provider tests using a fake client.

### Structured Provider Result

The model output contract is conceptually:

```json
{
  "answerable": true,
  "answer": "…",
  "cited_source_ids": ["S1", "S3"]
}
```

Service validation rules:

- `answerable=true` → non-empty answer + at least one valid cited source
- every source ID must exist in the current retrieved set
- duplicate source IDs normalize deterministically or fail consistently
- `answerable=false` → no citations
- unknown ID → fail closed as invalid Provider response
- arbitrary citation metadata from the model is never trusted

### No-Evidence Fast Path

If Retrieval returns zero results:

```text
do not call LLM Provider
→ deterministic insufficient_evidence
→ citations=[]
```

Do not let pretrained model knowledge fill the gap.

If Retrieval returns chunks but the Provider says `answerable=false`, return structured insufficient evidence with no citations.

### Prompt-Injection Boundary

Provider instructions must establish:

- sources are untrusted quoted evidence/data
- instructions inside sources are not policy
- never follow source-contained commands
- answer only from supplied evidence
- use only supplied source IDs
- insufficient evidence must be admitted

Serialize/delimit source objects structurally.

No tools are available to the model in #014, so retrieved prompt injection cannot invoke tool execution.

### Transaction Boundary

Expected request path:

```text
Authorization
→ Retrieval (Embedding Provider + DB exact search)
→ close any DB read transaction
→ generation Provider wait
→ best-effort Audit / Runtime Log
→ Response
```

No Product DB mutation is required.

Do not intentionally hold an open SQLAlchemy transaction across the generation API wait.

### Audit / Logging

Suggested event names:

- Audit action: `knowledge.answer`
- Runtime success: `knowledge.answer.completed`
- Provider failure: `knowledge.answer.provider_failure`

Allowed metadata only:

- retrieval count
- citation count
- status
- top_k
- min_similarity
- model
- token counts

Explicitly exclude:

- raw question
- generated answer
- retrieved content
- source names if unnecessary
- vectors
- API key
- raw Provider response

### Error Boundary

Generation Provider errors/invalid responses map to generic HTTP service-unavailable/upstream-unavailable behavior consistent with current provider failure style.

Do not expose SDK/provider exception details.

### CP2 Ordered Implementation Slices

CP2 is intentionally bounded to avoid long-agent timeout.

Implement in this order:

1. **Schemas + errors/config**
   - RAG request/response/citation schemas
   - generation model/output-token settings
   - generation Provider error types

2. **Provider boundary**
   - Protocol/data classes
   - OpenAI Responses + Structured Output implementation
   - focused fake-client Provider tests

3. **RAG Service**
   - reuse `RetrievalService`
   - source-ID mapping
   - no-evidence fast path
   - citation validation
   - DB transaction close before generation wait
   - Audit/log content exclusion

4. **API Route**
   - `POST /knowledge/answer`
   - `knowledge:read`
   - generic Provider/Retrieval failure translation
   - main router wiring

5. **Focused tests only**
   - schema
   - provider boundary
   - service grounding/citation
   - API auth/error behavior
   - relevant config test

**Do not run the full repository regression in CP2.**
Full regression belongs to CP3 / Final CI.

If CP2 cannot finish within the bounded scope without an unlisted Production file, stop and report Scope expansion instead of editing outside the Allowlist.

## Allowed Write Set

Conceptually allowed for implementation:

- `app/integrations/llm.py`
- `app/services/rag.py`
- `app/schemas/rag.py`
- `app/api/routes/rag.py`
- `app/core/config.py`
- `app/core/errors.py`
- `app/main.py`
- focused `tests/test_rag_*.py`
- `tests/test_config.py`
- this execution note for CP2 evidence only

The machine-readable marker at the top is the Safe Publish authority.

## Out of Scope

- Tool Calling/function calling
- hosted OpenAI tools
- Web Search/File Search
- conversation history
- streaming
- persistent chat/answer records
- Human Approval
- end-user document ACL redesign
- ANN/vector index changes
- reranker
- semantic citation entailment evaluator
- LLM evaluation framework
- UI
- autonomous actions

## Acceptance Criteria

GitHub Issue #65 is authoritative.

## Checkpoints

- [x] CP0 — Context bootstrap / contradiction detection
- [x] CP1 — Architecture + implementation plan validation
- [x] CP2 — Bounded implementation
- [ ] CP3 — Targeted + regression verification
- [ ] CP4 — Diff / security / grounding review
- [ ] CP5 — Knowledge + documentation synchronization
- [ ] CP6 — exact-Head delivery evidence

## CP2 Evidence Contract

CP2 should report:

- files changed
- focused tests attempted/results
- Provider SDK assumptions verified
- citation validation behavior
- prompt-injection boundary implemented
- transaction boundary evidence
- any unresolved blockers

Do not mark CP3+ complete.

## Current State

CP0 and CP1 are complete.

Remote Supervisor approval: **CP1**.

Next authorized action: **CP2** on `feature/issue-014-rag-grounded-answer`.

Full regression is intentionally deferred to CP3.


## Supervisor Fallback Execution

The remote CP2 gate remained authorized but was not consumed by the Local Watcher/Codex Executor after repeated checks.

To keep the Product cycle moving, the Supervisor performed a bounded CP2 fallback directly on the Feature Branch.

This fallback preserves the control boundaries:

- Product/Test writes remain inside the existing CP2 Write Allowlist.
- The Supervisor does not create a fake `checkpoint(issue-014): CP2` commit.
- CP3 verification remains mandatory.
- CP4 grounding/security review remains mandatory.
- Final exact-Head GitHub Actions remain mandatory before Merge.

### Fallback CP2 Implementation Evidence

Implemented:

- RAG request/response/citation schemas
- generation model/output-token configuration
- explicit generation Provider error hierarchy
- OpenAI Responses API adapter with strict JSON Schema Structured Output
- no tools / hosted tools / function definitions
- untrusted-evidence prompt-injection instructions
- RAG orchestration reusing `RetrievalService`
- zero-evidence deterministic fast path that bypasses generation
- server-assigned `S1/S2/...` source IDs
- fail-closed unknown citation validation
- server-built citation provenance
- explicit Session rollback before generation Provider wait
- content-free Audit/Runtime Log metadata
- `POST /knowledge/answer` protected by `knowledge:read`
- focused schema/provider/service/API/config tests authored

Verification status:

- focused tests are authored but have not yet been executed by the Supervisor fallback environment
- full regression is intentionally deferred to CP3
- no CP3+ checkpoint is marked complete

## Current State

CP0 and CP1 are complete.

CP2 bounded implementation has been produced through Supervisor fallback and passed Supervisor scope / grounding / transaction review.

Remote Supervisor approval: **CP2**.

Next authorized action: **CP3 targeted + regression verification**.
