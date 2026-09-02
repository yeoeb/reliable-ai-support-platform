Reliable AI Support Operations Platform

Production-oriented internal AI support platform built with FastAPI, PostgreSQL, SQLAlchemy, Alembic, Docker, authentication, automated testing, and explicit reliability boundaries.

The project is being developed incrementally toward a complete AI support system with RAG, controlled tool calling, human approval, evaluation, security testing, and observability.

Current status: backend foundation, persistence, migrations, user creation, password hashing, JWT authentication, RBAC permission enforcement, durable security audit logging, structured runtime logging with request correlation, bounded knowledge document ingestion, and GitHub-hosted backend verification are implemented. Embedding, retrieval, and LLM-backed RAG remain planned.

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

Untrusted-document boundary: no file execution, remote fetch, embedding, retrieval, or LLM use

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

PostgreSQL

SQLAlchemy 2.x

Psycopg 3

Alembic

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

Next

Embedding pipeline

Planned AI Layer

Retrieval / Vector Search

Embeddings

RAG with source citations

Agent tool calling

Tool parameter validation

Human confirmation for high-risk actions

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
