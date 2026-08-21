param(
    [string]$ConfigPath = "infra/cloudrun/storage_bridge_bootstrap.example.json",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$resolvedConfigPath = Join-Path $repoRoot $ConfigPath

$validationJson = python (Join-Path $repoRoot "tools\validate_phase18_storage_bridge_bootstrap.py") $resolvedConfigPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Phase 18 bridge bootstrap validation failed.`n$validationJson"
}

$validation = $validationJson | ConvertFrom-Json

$deployCommand = @()
foreach ($item in $validation.deploy_command_preview) {
    $deployCommand += [string]$item
}

$invokerCommand = @()
foreach ($item in $validation.invoker_binding_preview) {
    $invokerCommand += [string]$item
}

Write-Host "Validated bridge deploy command preview:" -ForegroundColor Cyan
Write-Host ($deployCommand -join " ")
Write-Host ""
Write-Host "Validated bridge invoker binding preview:" -ForegroundColor Cyan
Write-Host ($invokerCommand -join " ")

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

& $deployCommand[0] $deployCommand[1..($deployCommand.Length - 1)]
& $invokerCommand[0] $invokerCommand[1..($invokerCommand.Length - 1)]
