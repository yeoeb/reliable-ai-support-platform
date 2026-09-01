# Local Supervisor-Gated Codex Watcher\n\n## Purpose\n\ncodex_watch.py 讓操作者只需要啟動一次本機 Process。\n之後 GPT Supervisor 透過 Remote Feature Branch 的批准 Marker 控制 CP2 / CP3；Watcher 只在新的 Write Checkpoint 被明確批准時啟動 Codex。\n\n流程：GPT Supervisor → Remote Approval → Local Watcher → Codex Dispatcher → CP2/CP3 → Safe Publish → Remote Feature Branch → Supervisor Review。\n\n## Responsibility Boundary\n\nWatcher 不是 Supervisor。它不會自己選 Issue、修改 Approval Marker、自動執行 CP0/CP1/CP4/CP5/CP6、自動 Merge，或無限 Retry 失敗的 Codex Turn。\n\nV1 只有兩個 Trigger：Remote approved through CP1 → CP2；Remote approved through CP2 → CP3。其他 Approval State 只 Poll，不呼叫 Codex。\n\n## Token Behavior\n\nIdle Polling 只執行 Git command，不會呼叫 LLM。只有新的 CP2 / CP3 被 Supervisor 授權後，Watcher 才產生 Codex Turn。\n\n## Start\n\nPowerShell：\n\n    cd C:\Users\88693\reliable-ai-support-platform\n    git fetch origin\n    git switch feature/issue-009-audit-logging\n    git pull --ff-only origin feature/issue-009-audit-logging\n\n一次 Smoke Test：\n\n    python scripts/codex_watch.py --issue 009 --once\n\n持續 Watch：\n\n    python scripts/codex_watch.py --issue 009\n\n預設 Poll 30 秒；最低 5 秒。\n\n## Execution Sequence\n\n1. 確認目前 Branch 對應 Engineering Issue。\n2. 確認 Working Tree 乾淨。\n3. Fetch remote Feature Branch。\n4. git pull --ff-only，同步 Supervisor Marker。\n5. 讀 Remote Approval。\n6. 判斷是否有新的 CP2 / CP3。\n7. 檢查 Remote Branch 是否已存在 deterministic Checkpoint Commit。\n8. 沒有新 Write Checkpoint 就保持 Idle。\n9. 有新 Checkpoint 才呼叫 codex_dispatch.py。\n10. Dispatcher 負責 Shared Gate + Safe Publish。\n\n## Duplicate Prevention\n\nLocal .codex-dispatch/state.json 防止同機重跑；Remote Branch 上的 checkpoint(issue-NNN): CP2 / CP3 Commit 則提供跨 Process 的完成 Evidence。\n\n## Failure Policy\n\nCodex / Dispatcher 一旦失敗，Watcher 直接停止，不做 Automatic Retry。Supervisor 先分析 Scope、Dependency、Test 或 Agent Failure，再決定下一步，避免無限消耗 Codex Usage。\n\n## Process Lock\n\n每個 Engineering Issue 使用 .codex-dispatch/watch-NNN.lock，避免同一 Repository / Issue 同時跑兩個 Watcher。正常結束或 Ctrl+C 會清掉 Lock；Stale PID Lock 會在下次啟動時驗證。\n\n## Safety\n\nWatcher 不削弱 Dispatcher 的 Guard：Sandbox、Remote Supervisor Gate、Remote Write Allowlist、Local/Remote Head Race Guard、Control Marker Immutability、Hard-protected Control Plane、No Force Push、No Push to main/develop 都仍然生效。\n\nWatcher只是 Trigger Layer，不是新的 Trust Boundary。

## Windows One-Command Launcher

Windows 開發環境可直接使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_codex_watch.ps1 -Issue 009
```

只做一次檢查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_codex_watch.ps1 -Issue 009 -Once
```

Launcher 會：

1. 使用明確的 Engineering Issue → Branch mapping；未知 Issue 直接拒絕。
2. 驗證 `git`、`python`、`codex` 都在 PATH。
3. 驗證目前 Repository 與 Working Tree。
4. 拒絕 Dirty Working Tree。
5. `git fetch origin <branch>`。
6. `git switch <branch>`。
7. `git pull --ff-only origin <branch>`。
8. 啟動 `codex_watch.py`。

Launcher 不會安裝 Windows Service、不會保存 Credential、不會 Merge/Rebase、不會 Force Push。
