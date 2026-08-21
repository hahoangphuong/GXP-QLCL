param(
    [string]$ConfigPath = "infra/cloudrun/service_bootstrap.example.json",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$resolvedConfigPath = Join-Path $repoRoot $ConfigPath

$validationJson = python (Join-Path $repoRoot "tools\validate_phase15_service_bootstrap.py") $resolvedConfigPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Phase 15 bootstrap validation failed.`n$validationJson"
}

$validation = $validationJson | ConvertFrom-Json
$command = @()
foreach ($item in $validation.deploy_command_preview) {
    $command += [string]$item
}

Write-Host "Validated deploy command preview:" -ForegroundColor Cyan
Write-Host ($command -join " ")

if ($validation.warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Warnings:" -ForegroundColor Yellow
    foreach ($warning in $validation.warnings) {
        Write-Host "- $warning"
    }
}

if ($DryRun) {
    exit 0
}

& $command[0] $command[1..($command.Length - 1)]
