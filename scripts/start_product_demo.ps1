param(
    [switch]$PromoteExisting,
    [switch]$EnableLiveAi
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Require-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Require-File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file '$Path' was not found."
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'

Push-Location $repoRoot
try {
    Require-Command 'docker'
    Require-File $venvPython
    Require-File (Join-Path $repoRoot '.env')
    Require-File (Join-Path $repoRoot 'compose.yaml')
    Require-File (Join-Path $repoRoot 'alembic.ini')
    Require-File (Join-Path $repoRoot 'scripts\bootstrap_demo.py')
    Require-File (Join-Path $repoRoot 'app\main.py')
    Require-File (Join-Path $repoRoot 'demo\knowledge\password-reset.md')
    Require-File (Join-Path $repoRoot 'demo\knowledge\vpn-access.md')
    Require-File (Join-Path $repoRoot 'demo\knowledge\escalation-policy.md')

    $configuredAppEnv = $env:APP_ENV
    if (-not $configuredAppEnv) {
        $appEnvLines = @(
            Get-Content -LiteralPath (Join-Path $repoRoot '.env') |
                Where-Object { $_ -match '^\s*APP_ENV\s*=' }
        )
        if ($appEnvLines.Count -ne 1) {
            throw '.env must contain exactly one APP_ENV setting.'
        }
        $configuredAppEnv = (
            $appEnvLines[0] -replace '^\s*APP_ENV\s*=\s*', ''
        ).Trim()
    }

    if (
        -not $configuredAppEnv -or
        $configuredAppEnv.ToLowerInvariant() -ne 'development'
    ) {
        throw 'The product demo launcher runs only when APP_ENV is development.'
    }
    $env:APP_ENV = 'development'

    Invoke-Checked 'docker' 'compose' 'version'
    Invoke-Checked $venvPython '--version'

    Write-Host 'Starting local PostgreSQL...'
    Invoke-Checked 'docker' 'compose' 'up' '-d' '--wait' 'postgres'

    Write-Host 'Applying Alembic migrations...'
    Invoke-Checked $venvPython '-m' 'alembic' 'upgrade' 'head'

    $bootstrapArguments = @('scripts\bootstrap_demo.py')
    if ($PromoteExisting) {
        $bootstrapArguments += '--promote-existing'
    }
    if ($EnableLiveAi) {
        $bootstrapArguments += '--enable-live-ai'
    }

    Write-Host 'Bootstrapping the local administrator and demo Knowledge...'
    Invoke-Checked $venvPython @bootstrapArguments

    Write-Host 'Starting the product API in the foreground. Press Ctrl+C to stop.'
    Write-Host 'Liveness : http://127.0.0.1:8000/health/live'
    Write-Host 'Readiness: http://127.0.0.1:8000/health/ready'
    Write-Host 'Swagger  : http://127.0.0.1:8000/docs'
    Invoke-Checked $venvPython '-m' 'uvicorn' 'app.main:app' '--reload'
}
finally {
    Pop-Location
}
