# Reliable AI Support Operations Platform

A backend portfolio project for AI-assisted support workflows that remain
testable, permission-aware, auditable, and fail-closed when model or
infrastructure behavior is unreliable.

**Maturity:** version `0.1.0` is a hardened local-development reference
implementation, not a hosted production service. Engineering Issues #001-#024
are implemented, including deterministic candidate comparison and
cross-platform evaluation-fixture verification.

## What it demonstrates

- FastAPI request boundaries with Pydantic validation and explicit errors.
- PostgreSQL + pgvector through SQLAlchemy 2.x and Alembic.
- Argon2 password hashing, JWT authentication, and PostgreSQL-backed RBAC.
- Durable security Audit Events separated from structured runtime logs.
- Bounded knowledge ingestion, deterministic chunking, provider-isolated OpenAI
  embeddings, and exact cosine-similarity retrieval.
- Grounded RAG with server-assigned evidence IDs and validated citations.
- Server-owned Tool schemas, permission filtering, argument validation, and a
  one-Tool execution bound.
- Durable Human Approval for a fixed higher-risk action, including expiry, row
  locking, permission re-checks, and atomic mutation/Audit persistence.
- Offline RAG and Tool-choice evaluation, adversarial regression, Prompt
  fingerprinting, coverage contracts, and deterministic Candidate comparison.
- Low-cardinality Prometheus metrics, request-correlated JSON logs, and
  CI/release verification controls.

## System and safety architecture

```text
Authenticated request
        |
        v
JWT identity -----> PostgreSQL-backed RBAC (authorization source of truth)
        |                         |
        v                         v
FastAPI route -> Service transaction boundary -> Repository -> PostgreSQL
        |
        +--> Retrieval -> untrusted evidence -> grounded generation
        |                                      -> validate citations
        |
        +--> model Tool proposal -> server schema + permission checks
                                      |                 |
                                      | read-only       | higher-risk
                                      v                 v
                                  execute once    durable Approval
                                                       |
                                              re-check + atomic execute

Cross-cutting: append-only Audit | redacted logs | bounded metrics
Offline: synthetic suites -> deterministic scorer -> safety gate/comparison
```

The LLM is a decision-support component, never the authorization boundary.
Retrieved text, model output, citations, Tool names, Tool arguments, and
persisted Approval state are revalidated at server-owned boundaries.

## Selected reliability boundaries

| Area | Implemented boundary |
| --- | --- |
| Identity/access | JWT establishes identity; current database permissions decide access; protected routes deny by default. |
| Transactions | Services own commit/rollback; privilege and Approval mutations commit atomically with Audit evidence. |
| RAG | Zero evidence skips generation; citation IDs must match server-assigned sources; final provenance comes from retrieved rows. |
| Tools | Only registered, currently authorized Tools are exposed; arguments are validated again before execution. |
| Approval | One exact action is persisted, expires after 15 minutes, is row-locked for a one-time decision, and is reauthorized before execution. |
| Sensitive data | Passwords, tokens, API keys, prompts, answers, chunks, vectors, and Tool arguments are excluded from reviewed log/metric surfaces as applicable. |
| Observability | Liveness is database-independent; readiness reports database failure; telemetry cannot change Product responses. |
| Evaluation | Case/result IDs reconcile exactly, Prompt drift fails closed, and Safety violations are gated separately from aggregate accuracy. |

## Verification evidence

The repository includes unit, API, service, persistence, migration,
integration, security, evaluation, dispatcher, and release-control tests.
Normal automated verification uses fake providers and makes no live OpenAI
call.

- The first hardened release candidate passed 482 Backend tests, database
  recovery, and 87 Dispatcher tests before promotion to `main`.
- Engineering #023 added deterministic same-Suite Candidate / Prompt
  Comparison; its exact Feature Head passed Backend and Dispatcher CI.
- Engineering #024 recorded 27 focused Windows tests and 60 Windows
  control-plane regression tests, and pinned fixture bytes across platforms.
- V2 evaluation data contains 80 normal and 40 adversarial synthetic Cases. Its
  passing baseline is a **scorer fixture**, not measured live-model quality.

Exact evidence is recorded in [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)
and the [`docs/issues/`](docs/issues/) execution notes.

## Quick start (Windows PowerShell)

Prerequisites: Python 3.11+, Git, Docker Desktop with Docker Compose, and
PowerShell.

```powershell
git clone https://github.com/yeoeb/reliable-ai-support-platform.git
Set-Location reliable-ai-support-platform

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/dev.txt

Copy-Item .env.example .env
docker compose up -d --wait postgres
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs>. `OPENAI_API_KEY` is not required for
startup, the local identity flow, or deterministic offline verification.

Follow [`docs/PORTFOLIO_DEMO.md`](docs/PORTFOLIO_DEMO.md) for the exact
health, Swagger, Auth/RBAC, bounded AI demonstration, offline evaluation,
optional cost-bearing provider, cleanup, and troubleshooting walkthrough.
Evaluation formats and exit codes are in
[`evals/README.md`](evals/README.md).

## Current API surface

| Area | Endpoint | Boundary |
| --- | --- | --- |
| Health | `GET /health/live`, `GET /health/ready` | Process liveness is separate from PostgreSQL readiness. |
| Users/Auth | `POST /users`, `POST /auth/login`, `GET /auth/me` | Password hashing, JWT validation, disabled-user enforcement. |
| RBAC | `GET /users`, `PUT/DELETE /admin/users/{user_id}/roles/{role_name}` | Database permissions and durable privilege-mutation Audit. |
| Knowledge | `POST /admin/knowledge/documents`, `POST /admin/knowledge/documents/{document_id}/embeddings` | `knowledge:manage`, bounded content, idempotent persistence. |
| Retrieval/RAG | `POST /knowledge/search`, `POST /knowledge/answer` | `knowledge:read`, exact retrieval, grounded citations. |
| Agent | `POST /agent/run` | Authorized Tool filtering, strict arguments, one Tool maximum. |
| Approval | `GET /approvals/{approval_id}`, `POST .../approve`, `POST .../reject` | `approval:decide`, row lock, expiry and permission re-check. |
| Metrics | `GET /metrics` | Custom bounded registry; intentionally omitted from OpenAPI. |

## Technology

- Python, FastAPI, Pydantic, Uvicorn
- PostgreSQL 16, pgvector, SQLAlchemy 2.x, Psycopg 3, Alembic
- OpenAI Embeddings and Responses APIs behind provider interfaces
- Argon2 (`pwdlib`) and PyJWT
- pytest, HTTPX, Docker Compose, and GitHub Actions

## Completed milestones

1. Backend, PostgreSQL, migrations, Users, Auth, RBAC, Audit, and structured
   observability foundations (#001-#010).
2. Knowledge ingestion, embeddings, exact retrieval, grounded RAG, controlled
   Tool Calling, and durable Human Approval (#011-#016).
3. Offline evaluation, adversarial AI security regression, operational
   metrics, CI/release hardening, and the first hardened release (#017-#021).
4. Expanded evaluation coverage, Candidate / Prompt Comparison, and
   cross-platform determinism/Watcher completion evidence (#022-#024).

## Limitations and optional future work

This repository does **not** claim:

- production deployment, uptime, scalability, or compliance certification;
- measured live-model accuracy, safety, latency, or cost;
- semantic equivalence from coarse required-answer fragments;
- a frontend, tenant isolation, four-eyes Approval, ANN retrieval, reranking,
  distributed tracing, or external log aggregation;
- enforced GitHub Branch Protection or repository Rulesets.

Possible later work includes broader semantic-diversity evaluation,
recorded/live Candidate evidence with explicit budgets, evidence-driven
ANN/reranking, deployment/network controls, distributed tracing, external log
aggregation, and a dedicated four-eyes Approval design. These are optional
future work, not current capability.
