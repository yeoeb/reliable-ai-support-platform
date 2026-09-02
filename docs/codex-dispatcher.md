# Local Codex Checkpoint Dispatcher

這個 Dispatcher 是 Repository Supervisor workflow 與本機 Codex 之間的 Bridge。

它不會控制已經開著的 VS Code / Desktop Codex 對話，而是透過 Stable 的 Codex CLI non-interactive mode，啟動或續跑一個 bounded Codex Session。

## Integration Choice

V1 採用：

    Python Dispatcher
        ↓
    codex exec
        ↓
    Local Codex Session

原因：

- codex exec 是 Stable 的 automation boundary。
- 支援 JSONL output。
- 支援 read-only / workspace-write Sandbox。
- 支援 resume non-interactive Session。
- 沿用本機 Codex authentication 與 configuration。
- 不需要額外 OpenAI API Key 寫進 Project。

目前官方 Codex SDK 主要是 TypeScript library。若之後需要 richer event streaming、Approval UI 或 Client Integration，再升級到 Codex App Server。

## Prerequisites

PowerShell：

    codex doctor
    codex login

codex executable 必須在 PATH。

## Context Contract

每次執行前，Dispatcher 固定確認：

1. AGENTS.md
2. docs/PROJECT_STATE.md
3. exactly one docs/issues/issue-NNN-*.md
4. current Git Branch
5. remote Supervisor approval from `origin/<current-branch>`

Issue execution note 應保持精簡，只保存：

- Goal
- Scope / Out of Scope
- Allowed Write Set
- Acceptance Criteria
- Checkpoint
- Test Requirements
- Current State

不要保存完整 Chat transcript。

## Checkpoint Permission

| Checkpoint | Sandbox | 目的 |
| --- | --- | --- |
| CP0 | read-only | Context / contradiction check |
| CP1 | read-only | Plan |
| CP2 | workspace-write | Bounded implementation |
| CP3 | workspace-write | Verification + in-scope fix |
| CP4 | read-only | Diff / Security / Regression review |
| CP5 | read-only | Knowledge / Documentation analysis |
| CP6 | read-only | Delivery evidence |

CP1–CP6 必須在對應的 Engineering Issue Feature Branch 執行；CP2 / CP3 使用 `workspace-write`。

## Shared Supervisor Gate

每份 Issue execution note 必須有且只能有兩個 Control Marker：

```md
<!-- codex-dispatch-supervisor-approved-through: CP0 -->
<!-- codex-dispatch-write-allow: ["app/example.py", "tests/test_*.py"] -->
```

第二個 Marker 是 CP2/CP3 可發布檔案的 Supervisor-controlled Allowlist，採 repository-relative POSIX glob。

批准規則：

- CP1 需要 Supervisor 已批准 CP0。
- CP2 需要批准 CP1。
- CP3 需要批准 CP2。
- 依此類推。

Dispatcher 執行前會：

```text
git fetch origin <current-feature-branch>
git show origin/<current-feature-branch>:docs/issues/issue-NNN-*.md
```

然後從**遠端 Branch**解析批准 Marker。

這代表本機 Codex 即使處於 `workspace-write` 並修改了本機 Markdown，也不能用尚未 Push 的 Working Tree 修改自行跨過下一個 Gate。

`.codex-dispatch/state.json` 只保存 Session Resume 與 Execution Metadata，不再具有批准下一個 Checkpoint 的權力。

## Dry Run

第一次先執行：

    python scripts/codex_dispatch.py --issue 009 --checkpoint CP1 --dry-run

Dry Run 會顯示：

- Engineering Issue ID
- Checkpoint
- Sandbox
- Branch
- Issue Note path
- 是否 Resume 既有 Session
- Codex argv
- 最終 Prompt

但不會呼叫 Codex，也不會寫入 Local State。

## Start CP1

    python scripts/codex_dispatch.py --issue 009 --checkpoint CP1

等價核心行為：

    codex exec --json --sandbox read-only --cd <repo> -

Prompt 透過 stdin 傳入，不使用 Shell command string interpolation。

## Continue CP2

Supervisor 驗收 CP1 後，在同一個 Issue Branch 執行：

    python scripts/codex_dispatch.py --issue 009 --checkpoint CP2

Dispatcher 會同時驗證：

- 遠端 Feature Branch 的 Supervisor Marker 已批准到 CP1。
- Branch 名稱必須包含 `issue-009`，避免在別的 Issue Branch 執行。
- Stored Session 的 Branch 必須與目前 Branch 相同。
- Local State 不得取代 Remote Supervisor Approval。

若已有 Session ID，Dispatcher 會使用：

    codex exec --json --sandbox workspace-write --cd <repo> resume <SESSION_ID> -

Codex flags 放在 resume subcommand 前，避免 Resume 後遺失本輪 Sandbox / JSON 設定。

## Safe Write Checkpoint Publication

CP2 / CP3 開始前：

1. Working Tree 必須乾淨。
2. Dispatcher fetch 目前 Feature Branch。
3. Local HEAD 必須等於 `origin/<branch>` HEAD。
4. Remote Supervisor Gate 必須批准前一個 Checkpoint。
5. Remote Issue Note 必須有合法 Write Allowlist。

Codex 成功返回後，Dispatcher 才執行：

```text
fetch remote branch again
        ↓
remote HEAD still unchanged?
        ↓
local HEAD still unchanged?   (Codex 沒有自己 Commit)
        ↓
Supervisor / Write-Allow markers unchanged?
        ↓
changed paths all match remote Allowlist?
        ↓
git add -- <bounded paths>
        ↓
git diff --cached --check
        ↓
git commit -m "checkpoint(issue-NNN): CP2"
        ↓
git push origin HEAD:<same-feature-branch>
```

任何 Guard 失敗都不 Push。

Hard-protected Control Plane 包含：

- `AGENTS.md`
- `docs/codex-dispatcher.md`
- `scripts/codex_dispatch.py`
- `.github/workflows/`
- `.git/`
- `.codex-dispatch/`

即使 Supervisor Allowlist 寫得過寬，這些路徑也不能由 Write Checkpoint 自動發布。

## Local State

Dispatcher 只保存最小 Metadata：

    .codex-dispatch/state.json

內容包含：

- issue_id
- session_id
- branch
- last_checkpoint
- last_status
- last_returncode
- published_commit_sha
- updated_at

不保存 Prompt、Chat transcript、Credential 或完整 Codex Output。

.codex-dispatch/ 必須 gitignore。

## Safety Controls

- CP2 / CP3 不能跑在 main / develop。
- Session 與建立它的 Branch 綁定。
- Branch 不一致時必須使用 --new-session。
- Checkpoint progression 由遠端 Supervisor Approval Marker 授權；Local State 只記錄 Executor Session/Result。
- 已成功的同一 Checkpoint 不會無意重跑；要重跑必須 --force。
- Write Checkpoint 的 Branch 名稱必須包含對應的 Engineering Issue ID。
- 不使用 danger-full-access。
- 不使用 --yolo。
- Read-only Checkpoint 不自動 Commit/Push。
- CP2/CP3 只有在 Safe Publish Guard 全通過後，Dispatcher 才 Commit 並正常 Push 到同一個 Feature Branch。
- 不 Force Push、不 Push main/develop、不自動 Merge。
- subprocess 使用 argv list，不使用 shell=True。
- 每個 Checkpoint 有 Timeout，避免 Agent / MCP helper 無限卡住。

## Recovery

不要 Resume 既有 Session：

    python scripts/codex_dispatch.py --issue 009 --checkpoint CP1 --new-session

明確重跑已成功 Checkpoint：

    python scripts/codex_dispatch.py --issue 009 --checkpoint CP1 --force

調整 Timeout：

    python scripts/codex_dispatch.py --issue 009 --checkpoint CP2 --timeout-seconds 2400

## Responsibility Boundary

Dispatcher 不負責：

- 選下一個 Issue
- 建立 Product Requirement
- Merge Pull Request
- Push main
- 更新 Notion
- 繞過 Sandbox / Approval
- 操控已開啟的 VS Code / Desktop Codex UI

這些仍由 GPT Supervisor 或後續獨立 Review 的 Orchestration Layer 負責。


## CP6 Exact-Head Delivery Rule

CP6 的 Branch-changing 工作必須在 Final CI **之前**完成：

1. 完成 Product Code / tests。
2. 完成 execution note、PROJECT_STATE、README/architecture 等必要 Repository 文件。
3. 確認沒有預期中的下一個 Branch commit。
4. 記錄 Final Head SHA。
5. 只對這個 exact Head 等待 GitHub Actions。
6. Backend / Dispatcher Checks 全部通過後，把 run ID、結果、Head SHA 寫到 PR / Issue Comment。
7. 不再 Commit 「CI passed」或 Delivery Evidence 回 Feature Branch。
8. Head SHA 未變才可 Merge。

如果 Final CI 後又發現必須修改 Repository：

```text
make required commit
→ new Head SHA
→ previous Final CI is stale
→ run exact-Head CI again
```

### 為什麼 Evidence 放 Comment

GitHub PR/Issue Comment 不改變 Git Branch Head，因此可以保存：

- exact Head SHA
- workflow run ID
- test result
- reviewer finding
- merge decision

而不會重新觸發同一個 Pull Request 的 CI。

### Workflow Concurrency

Verification workflows 使用 PR/ref-scoped `concurrency` 並 `cancel-in-progress: true`。當同一 PR 出現新 Head 時，舊的 in-progress verification 應被取消，避免 stale CI 浪費 Runner 時間。
