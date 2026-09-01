param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{1,3}$')]
    [string]$Issue,

    [switch]$Once,

    [ValidateRange(5, 3600)]
    [int]$PollSeconds = 30,

    [ValidateRange(1, 86400)]
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Require-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Invoke-Git {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $($Arguments -join ' ')"
    }
}

$issueId = '{0:D3}' -f [int]$Issue

$branchByIssue = @{
    '009' = 'feature/issue-009-audit-logging'
}

if (-not $branchByIssue.ContainsKey($issueId)) {
    throw (
        "No explicit Branch mapping exists for Engineering Issue #$issueId. " +
        "Refusing to guess a Branch."
    )
}

$targetBranch = $branchByIssue[$issueId]
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Push-Location $repoRoot
try {
    Require-Command 'git'
    Require-Command 'python'
    Require-Command 'codex'

    $resolvedRoot = (& git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $resolvedRoot) {
        throw 'The launcher is not inside a valid Git repository.'
    }

    if (
        [System.IO.Path]::GetFullPath($resolvedRoot) -ne
        [System.IO.Path]::GetFullPath($repoRoot)
    ) {
        throw (
            "Resolved Git root '$resolvedRoot' does not match " +
            "launcher repository '$repoRoot'."
        )
    }

    $dirty = (& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect Git Working Tree state.'
    }
    if ($dirty) {
        throw (
            'Working Tree is not clean. Commit, stash, or discard local ' +
            'changes before starting the Watcher.'
        )
    }

    Write-Host "Engineering Issue : #$issueId"
    Write-Host "Target Branch     : $targetBranch"
    Write-Host "Repository        : $repoRoot"

    Invoke-Git fetch --quiet origin $targetBranch
    Invoke-Git switch $targetBranch
    Invoke-Git pull --ff-only origin $targetBranch

    $watcherArgs = @(
        'scripts/codex_watch.py',
        '--issue',
        $issueId,
        '--poll-seconds',
        [string]$PollSeconds,
        '--timeout-seconds',
        [string]$TimeoutSeconds
    )

    if ($Once) {
        $watcherArgs += '--once'
    }

    Write-Host (
        'Starting: python ' +
        ($watcherArgs -join ' ')
    )

    & python @watcherArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Codex Watcher exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
