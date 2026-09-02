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

# Keep Python/Codex/Git text pipes independent from the Windows ANSI code page.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

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
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Push-Location $repoRoot
try {
    Require-Command 'git'
    Require-Command 'python'

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

    $resolverPath = Join-Path $repoRoot 'scripts/resolve_issue_branch.py'
    $targetBranch = (& python $resolverPath --issue $issueId --remote origin)

    if ($LASTEXITCODE -ne 0) {
        throw (
            "Unable to resolve a unique remote Feature Branch " +
            "for Engineering Issue #$issueId."
        )
    }

    if ($targetBranch -is [array]) {
        if ($targetBranch.Count -ne 1) {
            throw (
                "Branch resolver returned more than one output line for " +
                "Engineering Issue #$issueId."
            )
        }
        $targetBranch = $targetBranch[0]
    }

    $targetBranch = ([string]$targetBranch).Trim()
    if (-not $targetBranch) {
        throw (
            "Branch resolver returned an empty Branch for " +
            "Engineering Issue #$issueId."
        )
    }

    Require-Command 'codex'

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
