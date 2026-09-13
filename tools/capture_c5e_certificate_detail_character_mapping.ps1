param(
    [string]$LegacyRoot = ".\legacy",
    [string]$Output = ".\artifacts\legacy_audit\c5e_certificate_detail_character_mapping_capture.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Release-ComObject {
    param($Object)

    if ($null -eq $Object) {
        return
    }

    try {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
    catch {
    }
}

function Get-StringSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [Security.Cryptography.SHA256]::Create()

    try {
        return (
            [BitConverter]::ToString(
                $sha.ComputeHash($bytes)
            )
        ).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-FileSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return (
        Get-FileHash `
            -LiteralPath $Path `
            -Algorithm SHA256
    ).Hash.ToLowerInvariant()
}

function Get-LeafName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $value = $Name

    if ($value.Contains("!")) {
        $parts = $value.Split("!")
        $value = $parts[$parts.Length - 1]
    }

    return $value.Trim("'")
}

function Find-WorkbookNameRecord {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,

        [Parameter(Mandatory = $true)]
        [string]$TargetName
    )

    $names = $null
    $result = $null

    try {
        $names = $Workbook.Names

        for ($i = 1; $i -le [int]$names.Count; $i++) {
            $item = $null

            try {
                $item = $names.Item($i)
                $leaf = Get-LeafName -Name ([string]$item.Name)

                if ($leaf -ieq $TargetName) {
                    if ($null -ne $result) {
                        throw "Duplicate workbook name: $TargetName"
                    }

                    $result = [pscustomobject]@{
                        name = $TargetName
                        full_name = [string]$item.Name
                        refers_to = [string]$item.RefersTo
                    }
                }
            }
            finally {
                Release-ComObject $item
            }
        }
    }
    finally {
        Release-ComObject $names
    }

    return $result
}

function Extract-StringConstant {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RefersTo
    )

    if (-not $RefersTo.StartsWith('="')) {
        throw "Unexpected RefersTo prefix for string constant."
    }

    if (-not $RefersTo.EndsWith('"')) {
        throw "Unexpected RefersTo suffix for string constant."
    }

    if ($RefersTo.Length -lt 3) {
        throw "RefersTo string constant is too short."
    }

    return $RefersTo.Substring(
        2,
        $RefersTo.Length - 3
    )
}


# ------------------------------------------------------------
# Resolve the single legacy XLSB without hardcoding Unicode name
# ------------------------------------------------------------

$LegacyRoot = (Resolve-Path -LiteralPath $LegacyRoot).Path

$xlsbFiles = @(
    Get-ChildItem `
        -LiteralPath $LegacyRoot `
        -File |
    Where-Object { $_.Extension -ieq ".xlsb" }
)

if ($xlsbFiles.Count -ne 1) {
    throw "Expected exactly one .xlsb; found $($xlsbFiles.Count)"
}

$sourcePath = $xlsbFiles[0].FullName
$sourceSha256 = Get-FileSha256 -Path $sourcePath

Write-Host "SOURCE_XLSB=$sourcePath"


# ------------------------------------------------------------
# Capture
# ------------------------------------------------------------

$excel = $null
$workbook = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    $workbook = $excel.Workbooks.Open(
        $sourcePath,
        0,
        $true
    )

    $records = [ordered]@{}

    foreach ($targetName in @("AcChS", "RgChS")) {
        $record = Find-WorkbookNameRecord `
            -Workbook $workbook `
            -TargetName $targetName

        if ($null -eq $record) {
            throw "Workbook name not found: $targetName"
        }

        $refersTo = [string]$record.refers_to
        $value = Extract-StringConstant -RefersTo $refersTo

        $records[$targetName] = [ordered]@{
            name = $targetName
            full_name = [string]$record.full_name
            refers_to = $refersTo
            refers_to_length = [int]$refersTo.Length
            refers_to_sha256 = Get-StringSha256 -Text $refersTo
            value = $value
            value_length = [int]$value.Length
            value_sha256 = Get-StringSha256 -Text $value
        }
    }

    $ac = $records["AcChS"]
    $rg = $records["RgChS"]

    $blockers = @()

    $expectedAcHash = "e2c11944987d991cff291d40429b6d1fbe733ab847487ec9b42e650f013d3422"
    $expectedRgHash = "e69c5ba617a3b7a6f0453baac433507231ed16a860768823e9ba59d3d92359da"

    if ($ac.refers_to_sha256 -ne $expectedAcHash) {
        $blockers += [ordered]@{
            code = "ACCHS_REFERS_TO_SHA256_MISMATCH"
            expected = $expectedAcHash
            actual = $ac.refers_to_sha256
        }
    }

    if ($rg.refers_to_sha256 -ne $expectedRgHash) {
        $blockers += [ordered]@{
            code = "RGCHS_REFERS_TO_SHA256_MISMATCH"
            expected = $expectedRgHash
            actual = $rg.refers_to_sha256
        }
    }

    if ($ac.refers_to_length -ne 137) {
        $blockers += [ordered]@{
            code = "ACCHS_REFERS_TO_LENGTH_MISMATCH"
            expected = 137
            actual = $ac.refers_to_length
        }
    }

    if ($rg.refers_to_length -ne 137) {
        $blockers += [ordered]@{
            code = "RGCHS_REFERS_TO_LENGTH_MISMATCH"
            expected = 137
            actual = $rg.refers_to_length
        }
    }

    if ($ac.value_length -ne $rg.value_length) {
        $blockers += [ordered]@{
            code = "CHARACTER_MAPPING_CARDINALITY_MISMATCH"
            acchs = $ac.value_length
            rgchs = $rg.value_length
        }
    }

    if ($ac.value_length -eq 0) {
        $blockers += [ordered]@{
            code = "CHARACTER_MAPPING_EMPTY"
        }
    }

    if ($blockers.Count -eq 0) {
        $status = "CHARACTER_MAPPING_CAPTURED"
    }
    else {
        $status = "CHARACTER_MAPPING_BLOCKED"
    }

    $report = [ordered]@{
        schema_version = "c5e-certificate-detail-character-mapping-capture/v3"
        status = $status

        source = [ordered]@{
            workbook = [IO.Path]::GetFileName($sourcePath)
            workbook_path = $sourcePath
            workbook_sha256 = $sourceSha256
        }

        mappings = $records

        summary = [ordered]@{
            mappings = [int]$records.Count
            mapping_length = [int]$ac.value_length
            blockers = [int]$blockers.Count
        }

        blockers = $blockers

        invariants = [ordered]@{
            excel_opened_read_only = $true
            unicode_not_reconstructed_manually = $true
            source_refers_to_checksum_checked = $true
            mapping_cardinality_checked = $true
            gdp_in_scope = $false
            unkeyed_entries_used = $false
        }
    }

    $outputPath = [IO.Path]::GetFullPath($Output)
    $outputDirectory = Split-Path -Parent $outputPath

    New-Item `
        -ItemType Directory `
        -Force `
        -Path $outputDirectory |
    Out-Null

    $json = $report | ConvertTo-Json -Depth 20

    $utf8NoBom = New-Object Text.UTF8Encoding($false)

    [IO.File]::WriteAllText(
        $outputPath,
        $json + [Environment]::NewLine,
        $utf8NoBom
    )

    Write-Host "STATUS=$status"
    Write-Host "MAPPINGS=$($records.Count)"
    Write-Host "MAPPING_LENGTH=$($ac.value_length)"
    Write-Host "ACCHS_REFERS_TO_LENGTH=$($ac.refers_to_length)"
    Write-Host "RGCHS_REFERS_TO_LENGTH=$($rg.refers_to_length)"
    Write-Host "ACCHS_REFERS_TO_SHA256=$($ac.refers_to_sha256)"
    Write-Host "RGCHS_REFERS_TO_SHA256=$($rg.refers_to_sha256)"
    Write-Host "ACCHS_VALUE_SHA256=$($ac.value_sha256)"
    Write-Host "RGCHS_VALUE_SHA256=$($rg.value_sha256)"
    Write-Host "BLOCKERS=$($blockers.Count)"
    Write-Host "OUTPUT=$outputPath"

    foreach ($blocker in $blockers) {
        $line = $blocker | ConvertTo-Json -Depth 10 -Compress
        Write-Host "BLOCKER=$line"
    }

    if ($blockers.Count -gt 0) {
        exit 1
    }
}
finally {
    if ($null -ne $workbook) {
        try {
            $workbook.Close($false)
        }
        catch {
        }

        Release-ComObject $workbook
    }

    if ($null -ne $excel) {
        try {
            $excel.Quit()
        }
        catch {
        }

        Release-ComObject $excel
    }

    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}