# Engineering Issue #027 — Local Demo Bootstrap and Operator CLI

<!-- codex-dispatch-supervisor-approved-through: CP1 -->
<!-- codex-dispatch-write-allow: ["app/services/demo_bootstrap.py","scripts/bootstrap_demo.py","scripts/start_product_demo.ps1","demo/knowledge/password-reset.md","demo/knowledge/vpn-access.md","demo/knowledge/escalation-policy.md","tests/test_demo_bootstrap.py","tests/test_product_demo_launcher.py","README.md","docs/PORTFOLIO_DEMO.md","docs/issues/issue-027-local-demo-bootstrap.md"] -->

- GitHub Issue: #113
- Source: https://github.com/yeoeb/reliable-ai-support-platform/issues/113
- Branch: `feature/issue-027-local-demo-bootstrap`
- Base: `develop@eb45967ff41dbb55b6b8dc466980b772e74cd0b8`
- Current checkpoint: CP2 authorized
- Authorized through: CP1
- Owner model: Supervisor defines gates; Watcher Agent implements CP2/CP3.

## Assigned GitHub Issue contract snapshot

- Issue number: GitHub Issue #113 / Engineering Issue #027
- Title: `Engineering #027 — Local Demo Bootstrap and Operator CLI`
- Source URL: https://github.com/yeoeb/reliable-ai-support-platform/issues/113
- Captured by Supervisor: 2026-09-05

### Goal

Turn the completed backend platform into a repeatable local product demo that
an operator can start and use without manually editing the database or relying
on test-only fixtures.

### Scope

- a development-only bootstrap service and CLI;
- interactive secret entry, with no password accepted in command arguments or
  printed;
- idempotent local administrator creation;
- safe handling of an existing email, with no silent privilege escalation;
- deterministic Knowledge seeding through existing Service/Audit boundaries;
- optional live Embedding/RAG initialization only after explicit opt-in and
  valid Provider configuration;
- a Windows PowerShell launcher that checks prerequisites, starts PostgreSQL,
  runs Alembic, invokes bootstrap, starts FastAPI, and prints local URLs;
- security/idempotency/failure-path tests;
- accurate README and portfolio demo instructions.

### Acceptance criteria

1. `powershell -ExecutionPolicy Bypass -File scripts/start_product_demo.ps1`
   is the documented primary entry point.
2. The launcher and bootstrap fail closed outside the development environment.
3. Passwords/tokens are not accepted in argv, persisted in repository files, or
   emitted to stdout/stderr.
4. A new administrator is created through existing Password, User, and RBAC
   boundaries.
5. Re-running for the same authenticated administrator is idempotent.
6. An existing non-admin is not promoted unless an explicit promotion option is
   combined with successful password authentication.
7. Demo Knowledge documents are deterministic, content-addressed, idempotent,
   and created through the existing Knowledge Service.
8. Live AI is disabled by default. Provider calls occur only after explicit
   `--enable-live-ai` opt-in and valid configuration.
9. Non-Provider-dependent APIs still launch when Live AI is disabled, with an
   accurate capability summary.
10. With Live AI enabled, seeded documents can be embedded and exercised through
    existing Retrieval/RAG endpoints.
11. Tests cover environment guards, secret handling, identity/role bootstrap,
    Knowledge idempotency, existing-user refusal/promotion, missing-key behavior,
    rollback/failure behavior, and launcher structure.
12. Existing Auth/RBAC/Audit/Knowledge/Retrieval/RAG/Approval behavior remains
    green.
13. Documentation does not claim hosted deployment, free live inference, or a
    fake Provider as live RAG.

### Non-goals

- no Website or Frontend work;
- no hosted or production deployment;
- no production bootstrap or default administrator;
- no default password, stored Token, or Secret;
- no automatic OpenAI spending;
- no Fake Provider represented as Live RAG;
- no Auth/RBAC semantic change;
- no Database Schema or Alembic Migration change;
- no weakening of Audit or Approval boundaries.

### Verification

- `python -m pytest tests/test_demo_bootstrap.py tests/test_product_demo_launcher.py -q`
- focused existing Auth/RBAC/Knowledge/Retrieval/RAG/Approval tests
- `python -m pytest -q` with PostgreSQL healthy
- `python -m ruff check .` when Ruff is available
- `git diff --check`
- PowerShell syntax validation
- manual clean-database smoke test through Swagger

## Required reading

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #113 or this complete offline snapshot
- `README.md`
- `docs/PORTFOLIO_DEMO.md`
- `app/services/user.py`
- `app/services/auth.py`
- `app/services/rbac.py`
- `app/services/knowledge.py`
- `app/services/embedding.py`
- `app/integrations/embeddings.py`
- `app/integrations/llm.py`
- `scripts/start_codex_watch.ps1`
- relevant Auth/RBAC/Knowledge/RAG/Approval tests

## CP0 — Context bootstrap and contradiction detection

Status: **completed** by Supervisor on 2026-09-05.

Findings:

- Engineering #001–#026 are completed and release `0.2.0` is present on
  `main`; `develop` is the Product integration baseline.
- No Engineering Issue, open GitHub Issue, Pull Request, or conflicting Feature
  Branch was active before #027 was created.
- The actual API already contains Auth, PostgreSQL-backed RBAC, Audit,
  Knowledge ingestion, Embedding, pgvector Retrieval, grounded RAG, controlled
  Tool Calling, Human Approval, Evaluation, health, and metrics.
- Seed migrations create roles/permissions but do not create an administrator.
- No supported CLI currently creates an authorized local operator or deterministic
  demo Knowledge.
- The live embedding/generation routes use configured Providers; current
  deterministic demonstrations use test-only Fake Providers.
- Documentation explicitly acknowledges that privileged manual setup is missing.
- Therefore the missing Product surface is local bootstrap/operation, not the
  underlying RAG implementation.
- No contradiction was found between repository rules, Project State, Issue
  contract, current code, and this bounded plan.

## CP1 — Plan and design gate

Status: **completed** by Supervisor on 2026-09-05.

### Design

1. Add a small `DemoBootstrapService` that orchestrates existing User, Auth,
   RBAC, Knowledge, and Embedding boundaries rather than duplicating their
   persistence/security logic.
2. Guard both Service and CLI with the validated application environment. Only
   the development environment is allowed.
3. Read administrator password with `getpass`. Do not add a password/token
   CLI option and do not echo secret material.
4. New email path:
   - create the User with existing password hashing;
   - assign `admin` through the existing RBAC Service;
   - seed Knowledge using that User as the Audit actor.
5. Existing email path:
   - authenticate the supplied password;
   - return success idempotently when the User already has `admin`;
   - otherwise refuse by default;
   - allow promotion only with an explicit `--promote-existing` option plus
     successful authentication.
6. Load three bounded Markdown demo documents from `demo/knowledge/`. Preserve
   normalized/content-addressed Knowledge idempotency.
7. Default mode never invokes an external Provider. `--enable-live-ai` must
   validate Provider configuration before embedding the seeded documents.
8. The launcher must:
   - resolve the repository virtual-environment Python explicitly;
   - verify Docker, Python, and required files;
   - set/require development mode;
   - run `docker compose up -d --wait postgres`;
   - run `python -m alembic upgrade head`;
   - invoke the interactive bootstrap CLI;
   - start `python -m uvicorn app.main:app`;
   - print `/health/live`, `/health/ready`, and `/docs` URLs;
   - stop immediately on a failed prerequisite or command.
9. Output may include created/reused IDs and capability status, but must not
   include passwords, hashes, API keys, JWTs, raw document content, vectors, or
   Provider responses.
10. Keep the launcher foreground process interruptible; do not install services,
    edit global machine configuration, or persist credentials.

### Allowed write set

- `app/services/demo_bootstrap.py`
- `scripts/bootstrap_demo.py`
- `scripts/start_product_demo.ps1`
- `demo/knowledge/password-reset.md`
- `demo/knowledge/vpn-access.md`
- `demo/knowledge/escalation-policy.md`
- `tests/test_demo_bootstrap.py`
- `tests/test_product_demo_launcher.py`
- `README.md`
- `docs/PORTFOLIO_DEMO.md`
- this execution note

`docs/PROJECT_STATE.md` is Supervisor-owned and intentionally outside the
Dispatcher write allowlist.

### Frozen surfaces

- database models, Schema, Alembic migrations, and seed migration semantics;
- existing Auth/RBAC/Audit/Knowledge/Retrieval/RAG/Tool/Approval public contracts;
- external Provider implementations;
- Evaluation fixtures and scoring;
- GitHub Actions and release workflows;
- `AGENTS.md`;
- unrelated docs/tests/scripts;
- the Portfolio Website.

### Required tests and review evidence

- development-only guard and non-development refusal;
- argv/parser has no password/token option;
- captured output never contains supplied secret material;
- new User receives hashed credentials and admin assignment;
- same authenticated admin rerun is idempotent;
- wrong password fails;
- existing non-admin refuses without explicit promotion;
- explicit promotion authenticates first and is auditable;
- deterministic Knowledge seed is idempotent;
- default mode performs zero Provider calls;
- Live AI mode refuses missing configuration before Provider work;
- injected failures preserve transaction/audit invariants;
- launcher uses the repository virtual environment, stop-on-error behavior,
  required Docker/Alembic/bootstrap/Uvicorn steps, and contains no default secret;
- focused and broad regression, PowerShell parse, Diff, and secret scans.

### Risks

- A local bootstrap is a privilege boundary. Environment and existing-account
  behavior must fail closed.
- Interactive prompts can accidentally leak through arguments or logging.
- Partial User/Role/Knowledge setup could leave confusing state. Re-runs must
  reconcile safely and expose bounded status.
- Live embedding can incur cost. It must remain opt-in and must not run before
  configuration checks.
- Windows virtual-environment resolution has failed in prior work. The launcher
  must diagnose it explicitly and must not fall back to an unrelated interpreter.
- Direct database orchestration must reuse existing Services and Audit behavior;
  it must not become an alternate production admin path.

## CP2 — Bounded implementation

Authorized. Work only inside the machine-readable allowlist. Do not change the
Supervisor markers. Implement the CP1 design and record exact changed paths and
targeted evidence here. Do not commit or push; the Dispatcher owns publication.

## CP3 — Targeted verification

Not authorized. Await Supervisor review of the published CP2 checkpoint.

## CP4 — Diff and acceptance review

Not authorized.

## CP5 — Knowledge and documentation synchronization

Not authorized.

## CP6 — Exact-head delivery

Not authorized.
