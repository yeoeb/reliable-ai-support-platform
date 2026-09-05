# Reproducible portfolio demo (Windows PowerShell)

This walkthrough demonstrates the implemented local boundaries without
implying production readiness or live-model quality. The default path is
deterministic and does not call OpenAI. Commands assume the repository root
and Windows PowerShell.

## 1. Prerequisites

- Git
- Python 3.11 or newer (`python --version`)
- Docker Desktop with Docker Compose (`docker compose version`)
- PowerShell

```powershell
git clone https://github.com/yeoeb/reliable-ai-support-platform.git
Set-Location reliable-ai-support-platform
```

If you already have a checkout, start at its repository root.

## 2. Create the environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/dev.txt
Copy-Item .env.example .env
```

The example `.env` is ready for an isolated local demo. Change its PostgreSQL
password and `JWT_SECRET_KEY` before using the project beyond that disposable
environment. Leave `OPENAI_API_KEY` empty for the default path.

## 3. Start the product demo

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_product_demo.ps1
```

This is the primary entry point. The launcher verifies Docker, the repository
virtual-environment interpreter, `.env`, Alembic, and the three fixed demo
Knowledge files. It refuses an existing non-development `APP_ENV`, starts the
PostgreSQL service, applies migrations, and then prompts for an administrator
email and password. The password is read without echo and is never accepted as
a command argument.

A new identity is created through the existing password-hashing and User
service, receives the `admin` role through the audited RBAC service, and owns
the Knowledge ingestion Audit events. Re-running with the same authenticated
administrator reuses the identity and content-addressed documents. An existing
non-admin is refused unless the operator explicitly uses `-PromoteExisting`
and successfully authenticates that account:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_product_demo.ps1 `
  -PromoteExisting
```

The launcher leaves FastAPI running in the foreground. In a second PowerShell
terminal, return to the repository root and run:

```powershell
.\.venv\Scripts\Activate.ps1
$baseUrl = "http://127.0.0.1:8000"
Invoke-RestMethod "$baseUrl/health/live"
Invoke-RestMethod "$baseUrl/health/ready"
```

Expected JSON statuses are `alive` and `ready`. Liveness does not query
PostgreSQL; readiness does and returns HTTP 503 if it is unavailable.

## 5. Inspect Swagger and metrics

```powershell
Start-Process "$baseUrl/docs"
(Invoke-WebRequest "$baseUrl/metrics").Content
```

The Prometheus endpoint is deliberately omitted from Swagger. Its custom
registry uses reviewed, low-cardinality labels—not Request IDs, raw paths,
user/document IDs, prompts, answers, Tool arguments, model names, or secrets.
A production deployment would restrict this unauthenticated endpoint at the
network layer.

## 6. Reproduce registration, login, and identity

```powershell
$email = "portfolio.$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())@example.com"
$securePassword = Read-Host "Temporary test-user password" -AsSecureString
$credential = [System.Management.Automation.PSCredential]::new(
  $email,
  $securePassword
)
$password = $credential.GetNetworkCredential().Password

$newUser = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/users" `
  -ContentType "application/json" `
  -Body (@{
    email = $email
    display_name = "Portfolio Demo"
    password = $password
  } | ConvertTo-Json)

$login = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/auth/login" `
  -ContentType "application/json" `
  -Body (@{
    email = $email
    password = $password
  } | ConvertTo-Json)

$headers = @{ Authorization = "Bearer $($login.access_token)" }
$me = Invoke-RestMethod -Uri "$baseUrl/auth/me" -Headers $headers
$newUser
$me
Remove-Variable password
```

The public response contains neither the password nor its hash. JWT establishes
identity; it is not trusted as the authorization source of truth.

## 7. Demonstrate database-backed RBAC denial

A new user receives the baseline `user` role, which lacks `users:read`:

```powershell
$rbacStatus = try {
  Invoke-WebRequest -Uri "$baseUrl/users" -Headers $headers | Out-Null
  200
} catch {
  [int]$_.Exception.Response.StatusCode
}

$rbacStatus
if ($rbacStatus -ne 403) {
  throw "Expected RBAC denial (403), received $rbacStatus"
}
```

Authentication succeeds, then current PostgreSQL RBAC state denies the
protected request by default.

## 8. Demonstrate AI boundaries without a live provider

The default launcher path seeds three deterministic Markdown documents and
makes no Provider calls. Because the documents have no vectors in this mode,
live Retrieval/RAG requests are not claimed to work. The local administrator
can still use authenticated Auth/RBAC/Audit/Knowledge/Tool/Approval APIs.

Existing API/service tests provide a reproducible AI-boundary demonstration
with fake providers:

```powershell
python -m pytest -q `
  tests/test_rag_api.py `
  tests/test_agent_api.py `
  tests/test_approval_api.py `
  tests/test_ai_security_regression.py `
  tests/test_metrics_api.py
```

The tests cover grounded/insufficient-evidence RAG, citation and hostile-input
rejection, authorized and invalid Tool proposals, durable Approval states,
Approval-tampering rejection before mutation, and metrics/OpenAPI behavior.
Fake-provider evidence validates application contracts; it is not measured
live-model performance.

## 9. Run deterministic offline evaluation

These commands use synthetic Cases and normalized result fixtures. They do not
access PostgreSQL, call OpenAI, execute Tools, approve actions, or use an
LLM-as-Judge.

```powershell
python scripts/generate_eval_suite_v2.py --check

python -m app.evaluation.runner `
  --suite evals/suites/v2/suite.json `
  --results evals/suites/v2/baseline_results.jsonl `
  --candidate baseline-v2

python -m app.evaluation.runner `
  --suite evals/suites/security-v2/suite.json `
  --results evals/suites/security-v2/baseline_results.jsonl `
  --candidate security-baseline-v2

python -m app.evaluation.comparison_runner `
  --root evals `
  --comparison comparisons/v2-reference.json
```

Exit `0` means the gate passed, `1` means valid input failed the
quality/safety gate, and `2` means invalid input or CLI usage. A 100% fixture
score and zero Safety violations prove deterministic scorer/gate behavior for
known-good synthetic results—not live-model performance.

## 10. Optional live OpenAI path (may incur cost)

This section is optional, nondeterministic, cost-bearing, and outside default
verification. Before starting the API, set a valid key in `.env`:

```text
OPENAI_API_KEY=<your key>
```

Never expose the key in commands, logs, screenshots, source files, or Git
history. Start the demo with explicit opt-in:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_product_demo.ps1 `
  -EnableLiveAi
```

The bootstrap validates that a key is configured before database or Provider
work, then creates embeddings for the three seeded documents through the
existing embedding service. Provider requests can incur cost and are
nondeterministic. The launcher never enables them implicitly.

After the API starts, sign in through `POST /auth/login` in Swagger using the
administrator email and the password entered interactively. Copy the returned
token into Swagger's **Authorize** dialog, or read it interactively for the
PowerShell examples:

```powershell
$secureAdminToken = Read-Host "Authorized bearer token" -AsSecureString
$tokenCredential = [System.Management.Automation.PSCredential]::new(
  "token",
  $secureAdminToken
)
$adminToken = $tokenCredential.GetNetworkCredential().Password
$adminHeaders = @{ Authorization = "Bearer $adminToken" }
```

The seeded documents are already ingested and embedded. With the authenticated
administrator, exercise exact Retrieval and grounded RAG using the existing
endpoints:

```powershell
$search = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/knowledge/search" `
  -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{
    query = "When should a suspected account takeover be escalated?"
    top_k = 5
    min_similarity = 0.0
  } | ConvertTo-Json)

$answer = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/knowledge/answer" `
  -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{
    question = "When should a suspected account takeover be escalated?"
    top_k = 5
    min_similarity = 0.0
  } | ConvertTo-Json)

$search
$answer
```

The server reconstructs citations from retrieval results. `POST /agent/run`
is also live and cost-bearing, but its result depends on model output and
permissions. A higher-risk `grant_support_agent_role(user_id)` proposal
creates a pending Approval rather than executing in that model request. Use
section 8 for deterministic Tool/Approval proof.

Do not present live output as benchmark evidence without a separate, versioned
measurement protocol.

## 11. Cleanup

Stop Uvicorn with `Ctrl+C`, then run:

```powershell
docker compose down -v
Deactivate
```

`docker compose down -v` permanently deletes the demo database volume and its
data. Omit `-v` to retain it. If `.env` was only for this demo, inspect it
and then remove it:

```powershell
Remove-Item -LiteralPath .env
```

## 12. Troubleshooting

### PowerShell blocks environment activation

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

This changes policy only for the current PowerShell process.

### PostgreSQL is not healthy

```powershell
docker compose ps
docker compose logs postgres
```

Check Docker Desktop and port `5432`. If `POSTGRES_PORT` changes in
`.env`, Compose and the application read the same value.

### Alembic or readiness cannot connect

Confirm `.env` exists, PostgreSQL is healthy, and `POSTGRES_HOST`,
`POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` agree with Compose. Liveness succeeding while readiness
returns 503 means the process is up but its required database is unavailable.

### An AI endpoint returns 403 or 503

Authentication alone is insufficient. Ingestion/embedding needs
`knowledge:manage`; retrieval/RAG needs `knowledge:read`; Approval decisions
need `approval:decide`, plus the original action permission. For 503 on the
optional path, verify the key, restart Uvicorn after editing `.env`, and
check network/provider and database availability.

### The fixture check reports a mismatch

Do not use `--write` merely to hide drift. Inspect `git diff` and line
endings first. V2 fixture paths are pinned to LF in `.gitattributes` so
Windows checkout does not alter their bytes.
