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

CP2 / CP3 禁止直接在 main 或 develop 執行。

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

- 前一個成功 Checkpoint 必須是 CP1。
- Branch 不能是 `main` 或 `develop`。
- Branch 名稱必須包含 `issue-009`，避免在別的 Issue Branch 寫入。
- Stored Session 的 Branch 必須與目前 Branch 相同。

若已有 Session ID，Dispatcher 會使用：

    codex exec --json --sandbox workspace-write --cd <repo> resume <SESSION_ID> -

Codex flags 放在 resume subcommand 前，避免 Resume 後遺失本輪 Sandbox / JSON 設定。

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
- updated_at

不保存 Prompt、Chat transcript、Credential 或完整 Codex Output。

.codex-dispatch/ 必須 gitignore。

## Safety Controls

- CP2 / CP3 不能跑在 main / develop。
- Session 與建立它的 Branch 綁定。
- Branch 不一致時必須使用 --new-session。
- CP2 必須接在成功 CP1 後，之後依序 CP3 → CP4 → CP5 → CP6。
- 已成功的同一 Checkpoint 不會無意重跑；要重跑必須 --force。
- Write Checkpoint 的 Branch 名稱必須包含對應的 Engineering Issue ID。
- 不使用 danger-full-access。
- 不使用 --yolo。
- 不自動 Commit、Push 或 Merge。
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
