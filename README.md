Reliable AI Support Operations Platform

Production-oriented internal AI support platform built with FastAPI, PostgreSQL, SQLAlchemy, Alembic, Docker, authentication, automated testing, and explicit reliability boundaries.

The project is being developed incrementally toward a complete AI support system with RAG, controlled tool calling, human approval, evaluation, security testing, and observability.

Current status: backend foundation, persistence, migrations, authentication, database-backed RBAC, durable security audit logging, structured request-correlated logging, bounded knowledge ingestion, deterministic chunking, OpenAI embedding integration behind an explicit provider boundary, pgvector vector persistence, authorized exact vector retrieval, grounded RAG answer generation with server-validated evidence citations, controlled Tool Calling, durable Human Approval for a fixed higher-risk action, deterministic offline LLM Evaluation, and GitHub-hosted backend verification are implemented.

Why This Project

Many LLM demos focus only on generating an answer.

This project focuses on the engineering required to make an AI application reliable:

validated API boundaries

database transactions

authentication and authorization

failure handling

automated testing

safe tool execution

human confirmation for risky actions

evaluation and security regression testing

The goal is to build an AI system that is not only functional, but also testable, maintainable, and safe to operate.

Implemented

Backend & Persistence

FastAPI application structure

Pydantic request / response validation

PostgreSQL with Docker Compose

SQLAlchemy 2.x engine and session management

Alembic schema migrations

Liveness and database-aware readiness checks

Database failure and recovery handling

Application Architecture

HTTP Request
    ↓
FastAPI Route
    ↓
Service Layer
    ↓
Repository Layer
    ↓
SQLAlchemy Session
    ↓
PostgreSQL

Route / Service / Repository separation

Service-owned transaction boundary

Explicit commit() / rollback()

Duplicate-email conflict handling

Safe database error translation

Authentication

Argon2 password hashing

Credential persistence separated from public user data

JWT access tokens

Token expiration and subject validation

Protected current-user endpoint

Invalid / expired token handling

Disabled-user enforcement

Generic login failure responses

Authorization & Audit

Database-backed RBAC authorization

Permission enforcement independent of JWT role/permission claims

Durable security Audit Events

Actor / target / action / outcome event structure

Atomic Audit recording for RBAC privilege mutations

Best-effort Audit recording for authentication / authorization failures

Sensitive-data exclusion for passwords, tokens, authorization headers, and secrets

Append-only application boundary for Audit records

Observability

Structured one-line JSON application logs

Server-generated per-request UUID correlation

Request-scoped ContextVar propagation

X-Request-ID response header

HTTP request completion / failure events

Route-template logging instead of arbitrary raw paths

Sensitive structured-field redaction

Runtime Application Logs kept separate from durable Audit Events

Knowledge Ingestion

Admin-only text / Markdown ingestion with dedicated knowledge:manage permission

Deterministic newline normalization and SHA-256 content hashing

Provenance through bounded source_name metadata

Idempotent source_name + content_hash persistence

Database Unique Constraint concurrency backstop

Atomic KnowledgeDocument + Audit Event transaction

Untrusted-document boundary during ingestion: no file execution, remote fetch, retrieval, or LLM instruction execution

Embedding Pipeline

Deterministic char-v1 chunking with bounded chunk size and overlap

Stable embedding configuration hash for reproducible/idempotent processing

SDK-independent EmbeddingProvider boundary with OpenAI adapter

text-embedding-3-small with explicit 1536-dimensional output validation

Bounded provider batches and malformed-response fail-closed validation

pgvector PostgreSQL storage using vector(1536)

External provider wait occurs outside the initial DB read transaction

Post-provider DB re-check and Unique Constraint concurrency backstop

Atomic KnowledgeChunk + Audit Event persistence

No chunk text, vectors, API key, or raw provider response in API/Audit/runtime logs

No HNSW/IVFFlat/similarity query in this milestone

Exact Vector Retrieval

Dedicated `knowledge:read` permission for support_agent and admin

Bounded search query with top_k and minimum similarity validation

Ephemeral query embedding through the existing EmbeddingProvider boundary

Shared request DB read transaction closed before external query-embedding wait

Exact pgvector cosine-distance search over the current embedding configuration

Similarity threshold applied before LIMIT

Deterministic distance + Chunk UUID ordering

KnowledgeDocument provenance joined into retrieval results

Best-effort read Audit and safe structured retrieval logs

Retrieved chunk content returned as untrusted evidence without exposing vectors

No HNSW/IVFFlat/ANN or reranking in this milestone

Grounded RAG

POST /knowledge/answer reuses the existing knowledge:read and RetrievalService boundaries

Zero Retrieval results return deterministic insufficient_evidence without calling the generation model

Explicit GroundedAnswerProvider boundary with OpenAI Responses API adapter

Strict JSON Schema Structured Output for answerability / answer / cited source IDs

Server-assigned S1 / S2 / ... evidence IDs with fail-closed unknown citation validation

Final citation provenance reconstructed by the server from authoritative Retrieval results

Retrieved KnowledgeChunk content treated as untrusted evidence, never as policy or tool instruction

No Tool Calling, hosted tools, Web Search, or File Search in the RAG milestone

Shared request DB transaction closed before external generation-provider wait

Raw question, generated answer, chunk content, vectors, API keys, and raw Provider responses excluded from Audit/runtime logs

Durable Human Approval

Server-owned approval_required Tool risk separate from read_only execution

Fixed higher-risk grant_support_agent_role(user_id) action with no model-controlled role_name

Durable ApprovalRequest storing exact canonical validated Tool name + arguments

15-minute pending Approval expiry

Admin-only approval:decide permission kept separate from rbac:manage action permission

Human inspect / approve / reject API

SELECT ... FOR UPDATE row locking for one-time decisions

Approval-time re-check of approver permission and original requester action permission

Transaction-participating RBAC mutation with one atomic Approval + RBAC + Audit commit

Real two-Session PostgreSQL concurrency test proving one execute + one conflict

V1 self-approval allowed; four-eyes separation is explicitly not claimed

Offline LLM Evaluation

Versioned synthetic Eval suite for Grounded RAG and Tool-choice normalized outputs

Strict Case / Result reconciliation prevents missing or silently dropped Cases

Stable Prompt IDs + SHA-256 fingerprints detect Prompt drift

Deterministic RAG metrics cover answerability, citation integrity, required citation coverage, and coarse answer fragments

Deterministic Tool metrics cover direct/tool decision, exact Tool name, exact arguments, and unauthorized Tool selection

Safety violations are gated separately from aggregate case pass rate

Committed v1 corpus contains 12 synthetic Cases

Committed baseline fixture requires 100% case pass rate and zero Safety violations

Baseline fixture is scorer test data, not a measured live-model score

CLI distinguishes quality regression from malformed Eval input with exit codes 0 / 1 / 2

Normal CI performs no live OpenAI call, Product DB mutation, Tool execution, or Approval execution

Testing

pytest

FastAPI TestClient

configuration tests

database-session tests

health and readiness tests

ORM / migration tests

user-flow tests

authentication and JWT failure-path tests

Normal automated tests are designed not to require a manually running PostgreSQL instance.

Technology Stack

Application

Python

FastAPI

Pydantic

Database

PostgreSQL + pgvector

SQLAlchemy 2.x

Psycopg 3

Alembic

AI Integration

OpenAI Embeddings API

OpenAI Responses API for grounded generation

text-embedding-3-small

EmbeddingProvider and GroundedAnswerProvider Protocol / Adapter boundaries

Security

Argon2

pwdlib

PyJWT

Testing / Infrastructure

pytest

httpx

Docker Compose

GitHub Actions

PostgreSQL-backed CI verification

Alembic upgrade / downgrade regression checks

Git / GitHub

Quick Start

1. Clone

git clone https://github.com/yeoeb/reliable-ai-support-platform.git
cd reliable-ai-support-platform

2. Create virtual environment

python -m venv .venv
.\.venv\Scripts\Activate.ps1

3. Install dependencies

python -m pip install -r requirements/dev.txt

4. Configure environment

Copy-Item .env.example .env

Fill in the local PostgreSQL and JWT settings in .env.

OPENAI_API_KEY is optional for normal application startup. It is required when embeddings, grounded RAG generation, or controlled Tool Calling must call the real OpenAI provider.

5. Start PostgreSQL

docker compose up -d postgres
docker compose ps

6. Apply migrations

alembic upgrade head

7. Run the API

python -m uvicorn app.main:app --reload

Open:

http://127.0.0.1:8000/docs

8. Run tests

pytest -v

Current API

Health

GET /health/live
GET /health/ready

/health/live checks whether the application process is alive.

/health/ready checks whether required dependencies such as PostgreSQL are available.

User Registration

POST /users

Includes:

input validation

password hashing

duplicate-email handling

transaction rollback on failure

Authentication

POST /auth/login
GET /auth/me

Includes:

JWT access token creation

token expiration

protected current-user lookup

invalid / expired token rejection

Knowledge Administration

POST /admin/knowledge/documents

POST /admin/knowledge/documents/{document_id}/embeddings

Both endpoints require the database-backed `knowledge:manage` permission.

Knowledge ingestion accepts bounded text / Markdown and returns metadata without echoing document content.

Embedding creation uses deterministic chunking, an explicit OpenAI provider boundary, and pgvector vector(1536) persistence. Existing complete embeddings return idempotently without calling the provider again.

Knowledge Retrieval

POST /knowledge/search

This endpoint requires the database-backed `knowledge:read` permission.

V1 grants raw internal Retrieval to `support_agent` and `admin`, not the default `user` role.

Search uses exact pgvector cosine distance over the current embedding configuration, applies a bounded similarity threshold / top_k, joins KnowledgeDocument provenance, and returns chunk content as untrusted evidence without returning stored vectors.

Grounded RAG Answer

POST /knowledge/answer

This endpoint requires the same database-backed `knowledge:read` permission as raw Retrieval.

The server retrieves bounded evidence, assigns deterministic source IDs such as `S1`, calls the generation Provider without enabling tools, validates every returned citation ID against the retrieved set, and reconstructs final citation provenance from authoritative Retrieval rows.

If Retrieval returns no evidence, generation is skipped and the API returns `insufficient_evidence`. Retrieved content remains untrusted data and cannot grant instruction, policy, or tool-execution authority.

Controlled Tool Calling API

POST /agent/run

The endpoint requires authentication. The server filters available Tool definitions using current database-backed permissions and validates model-proposed arguments against server-owned schemas.

Read-only `platform_readiness` still executes immediately after a current permission re-check.

The fixed higher-risk `grant_support_agent_role(user_id)` proposal never executes in the model request. It creates a durable pending Approval and returns `status=approval_required` with an approval ID. The model cannot provide a role name or approve its own action.

Human Approval endpoints:

GET /approvals/{approval_id}

POST /approvals/{approval_id}/approve

POST /approvals/{approval_id}/reject

Approval decisions require the admin-only `approval:decide` permission, lock the exact Approval row, re-check current permissions, and atomically commit the fixed support_agent mutation with durable Audit evidence.

Reliability & Security Principles

Fail explicitly instead of silently ignoring errors.

Keep liveness independent from external dependencies.

Return 503 when required infrastructure is unavailable.

Roll back failed database transactions.

Never store plaintext passwords.

Never expose password hashes or secrets in API responses.

Never log access tokens or authentication secrets.

Manage schema changes through Alembic.

Keep unit / application tests isolated from developer-local infrastructure.

Do not document unfinished features as completed.

Development Workflow

GitHub Issue
    ↓
Feature Branch
    ↓
Implementation
    ↓
Automated Tests
    ↓
Pull Request
    ↓
Review
    ↓
Merge into develop

Stable milestones are promoted from:

develop
↓
Release Pull Request
↓
main

Roadmap

Completed

FastAPI foundation

PostgreSQL development environment

SQLAlchemy session infrastructure

Alembic migrations

User persistence and creation flow

Password hashing

JWT authentication

Automated regression tests

RBAC authorization

Permission enforcement

Privilege-escalation tests

Durable security audit logging

Structured JSON runtime logging

Server-generated Request ID correlation

Sensitive log-field redaction

GitHub Actions backend verification

Knowledge ingestion foundation

Embedding pipeline foundation

Deterministic chunking and configuration identity

OpenAI embedding provider boundary

pgvector vector(1536) persistence

Exact vector retrieval foundation

knowledge:read least-privilege retrieval access

Current-config cosine search with provenance

Grounded RAG response with evidence / citations

Server-owned citation validation

Zero-evidence generation bypass

Controlled read-only Tool Calling

Server-owned Tool Registry and strict argument validation

Execution-time database-backed permission re-check

Single-Tool execution bound with no Tool access during finalization

Durable Human Approval for higher-risk Tool actions

Exact action binding and 15-minute approval expiry

Row-locked one-time decision with approval-time permission re-check

Atomic support_agent mutation + Approval / RBAC Audit transaction

Offline LLM Evaluation foundation

Versioned RAG / Tool-choice Eval corpus

Prompt fingerprint regression guard

Deterministic Safety / threshold gate

Next

AI Security Regression foundation

Prompt-injection regression cases

AI privilege-escalation regression cases

Planned Reliability & AI Safety

Metrics / distributed tracing / external log aggregation

100+ LLM evaluation cases

Prompt version comparison

Prompt injection testing

AI privilege-escalation testing

Target Architecture

Authenticated User
        ↓
Authorization
        ↓
Support Request
        ↓
RAG / Context
        ↓
LLM Decision
        ↓
Tool Request
        ↓
Parameter Validation
        ↓
Permission Check
        ↓
Human Confirmation (if high risk)
        ↓
Tool Execution
        ↓
Audit Log
        ↓
Response with Evidence

The LLM is treated as a decision-support component, not as an authorization boundary.

Related Project

Restaurant Operations AI Agent

Separate local AI Agent project demonstrating:

Ollama / Qwen

Agent Loop

Tool Calling

Python tools

parameterized MySQL queries

input validation

database failure handling

Streamlit chat interface

This project extends those AI application concepts into a more production-oriented architecture.
