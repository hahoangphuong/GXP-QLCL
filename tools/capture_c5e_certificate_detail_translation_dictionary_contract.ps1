param(
    [string]$LegacyRoot = ".\legacy",
    [string]$Output = ".\artifacts\legacy_audit\c5e_certificate_detail_translation_dictionary_capture.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"


# ============================================================
# C.5e translation dictionary contract
# ASCII-only source for Windows PowerShell 5.1 compatibility.
# ============================================================

$TargetNames = @(
    "TV_Words",
    "TA_Words",
    "TV_Words2",
    "TA_Words2",
    "TA_Words2_Loc",
    "TV_Words4",
    "TA_Words4",
    "TV_Words6",
    "TA_Words6"
)

$ExpectedShapes = @{
    "TV_Words"      = @(426, 1)
    "TA_Words"      = @(426, 1)

    "TV_Words2"     = @(36, 1)
    "TA_Words2"     = @(36, 1)
    "TA_Words2_Loc" = @(36, 2)

    "TV_Words4"     = @(108, 1)
    "TA_Words4"     = @(108, 1)

    "TV_Words6"     = @(60, 1)
    "TA_Words6"     = @(60, 1)
}

$ExpectedAddresses = @{
    "TV_Words"      = '$B$5:$B$430'
    "TA_Words"      = '$C$5:$C$430'

    "TV_Words2"     = '$E$5:$E$40'
    "TA_Words2"     = '$F$5:$F$40'
    "TA_Words2_Loc" = '$G$5:$H$40'

    "TV_Words4"     = '$N$5:$N$112'
    "TA_Words4"     = '$O$5:$O$112'

    "TV_Words6"     = '$T$5:$T$64'
    "TA_Words6"     = '$U$5:$U$64'
}


# ============================================================
# Helpers
# ============================================================

function Release-ComObject {
    param($Object)

    if ($null -eq $Object) {
        return
    }

    try {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject(
            $Object
        )
    }
    catch {
    }
}


function Get-Sha256 {
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


function Get-StringSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()

    try {
        $hash = $sha.ComputeHash($bytes)

        return (
            [System.BitConverter]::ToString($hash)
        ).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}


function Convert-CellValue {
    param($Value)

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [string]) {
        return [string]$Value
    }

    if ($Value -is [bool]) {
        return [bool]$Value
    }

    if (
        $Value -is [byte] -or
        $Value -is [int16] -or
        $Value -is [int32] -or
        $Value -is [int64] -or
        $Value -is [single] -or
        $Value -is [double] -or
        $Value -is [decimal]
    ) {
        return $Value
    }

    return [string]$Value
}


function Get-RangeMatrix {
    param(
        [Parameter(Mandatory = $true)]
        $Range
    )

    $rowCount = [int]$Range.Rows.Count
    $columnCount = [int]$Range.Columns.Count

    $rows = New-Object System.Collections.ArrayList

    for ($r = 1; $r -le $rowCount; $r++) {
        $rowValues = New-Object System.Collections.ArrayList

        for ($c = 1; $c -le $columnCount; $c++) {
            $cell = $null

            try {
                $cell = $Range.Cells.Item($r, $c)
                $value = Convert-CellValue -Value $cell.Value2

                [void]$rowValues.Add(
                    $value
                )
            }
            finally {
                Release-ComObject $cell
            }
        }

        [void]$rows.Add(
            [object[]]$rowValues.ToArray()
        )
    }

    Write-Output -NoEnumerate (
        [object[]]$rows.ToArray()
    )
}


function Get-Diagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Values,

        [Parameter(Mandatory = $true)]
        [int]$ColumnCount
    )

    $blankCount = 0

    foreach ($row in $Values) {
        foreach ($value in $row) {
            if ($null -eq $value) {
                $blankCount++
                continue
            }

            if ($value -is [string]) {
                if ([string]::IsNullOrWhiteSpace([string]$value)) {
                    $blankCount++
                }
            }
        }
    }

    $duplicates = @()

    if ($ColumnCount -eq 1) {
        $allValues = @()

        foreach ($row in $Values) {
            if ($null -eq $row[0]) {
                $allValues += "<NULL>"
            }
            else {
                $allValues += [string]$row[0]
            }
        }

        $duplicateGroups = (
            $allValues |
            Group-Object |
            Where-Object {
                $_.Count -gt 1
            }
        )

        foreach ($group in $duplicateGroups) {
            $duplicates += [ordered]@{
                value = $group.Name
                count = [int]$group.Count
            }
        }
    }

    return [ordered]@{
        blank_cells = [int]$blankCount
        duplicate_value_count = [int]$duplicates.Count
        duplicate_values = $duplicates
    }
}


function Get-LeafName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FullName
    )

    $value = $FullName

    if ($value.Contains("!")) {
        $parts = $value.Split("!")
        $value = $parts[$parts.Length - 1]
    }

    return $value.Trim("'")
}


function Find-WorkbookName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,

        [Parameter(Mandatory = $true)]
        [string]$TargetName
    )

    $names = $null

    try {
        $names = $Workbook.Names

        for ($i = 1; $i -le [int]$names.Count; $i++) {
            $candidate = $null

            try {
                $candidate = $names.Item($i)

                $fullName = [string]$candidate.Name
                $leafName = Get-LeafName -FullName $fullName

                if ($leafName -ieq $TargetName) {
                    return $candidate
                }
            }
            catch {
            }

            if ($null -ne $candidate) {
                Release-ComObject $candidate
            }
        }
    }
    finally {
        Release-ComObject $names
    }

    return $null
}


# ============================================================
# Resolve legacy workbooks without Unicode filename literals
# ============================================================

$LegacyRoot = (
    Resolve-Path `
        -LiteralPath $LegacyRoot
).Path


$xlsbFiles = @(
    Get-ChildItem `
        -LiteralPath $LegacyRoot `
        -File |
    Where-Object {
        $_.Extension -ieq ".xlsb"
    }
)

$xlamFiles = @(
    Get-ChildItem `
        -LiteralPath $LegacyRoot `
        -File |
    Where-Object {
        $_.Extension -ieq ".xlam"
    }
)


if ($xlsbFiles.Count -ne 1) {
    throw (
        "Expected exactly one .xlsb in legacy root; found " +
        $xlsbFiles.Count
    )
}

if ($xlamFiles.Count -ne 1) {
    throw (
        "Expected exactly one .xlam in legacy root; found " +
        $xlamFiles.Count
    )
}


$WorkbookPaths = @(
    $xlsbFiles[0].FullName,
    $xlamFiles[0].FullName
)


Write-Host (
    "SOURCE_XLSB=" +
    $xlsbFiles[0].FullName
)

Write-Host (
    "SOURCE_XLAM=" +
    $xlamFiles[0].FullName
)


# ============================================================
# Open Excel read-only
# ============================================================

$excel = $null
$openedWorkbooks = @()

try {
    $excel = (
        New-Object `
            -ComObject Excel.Application
    )

    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false


    foreach ($path in $WorkbookPaths) {
        $workbook = $excel.Workbooks.Open(
            $path,
            0,
            $true
        )

        $openedWorkbooks += [pscustomobject]@{
            filename = (
                [System.IO.Path]::GetFileName(
                    $path
                )
            )

            path = $path

            sha256 = (
                Get-Sha256 `
                    -Path $path
            )

            workbook = $workbook
        }
    }


    # ========================================================
    # Capture named ranges
    # ========================================================

    $captures = @{}
    $blockers = @()


    foreach ($targetName in $TargetNames) {
        $owners = @()


        foreach ($opened in $openedWorkbooks) {
            $nameObject = $null
            $range = $null
            $sheet = $null

            try {
                $nameObject = (
                    Find-WorkbookName `
                        -Workbook $opened.workbook `
                        -TargetName $targetName
                )

                if ($null -eq $nameObject) {
                    continue
                }

                $refersTo = (
                    [string]$nameObject.RefersTo
                )

                try {
                    $range = (
                        $nameObject.RefersToRange
                    )
                }
                catch {
                    $range = $null
                }


                if ($null -eq $range) {
                    $owners += [pscustomobject]@{
                        workbook = $opened.filename
                        workbook_path = $opened.path
                        workbook_sha256 = $opened.sha256
                        refers_to = $refersTo
                        resolvable_range = $false
                        worksheet = $null
                        address = $null
                        rows = $null
                        columns = $null
                    }

                    continue
                }


                $sheet = (
                    $range.Worksheet
                )

                $owners += [pscustomobject]@{
                    workbook = $opened.filename
                    workbook_path = $opened.path
                    workbook_sha256 = $opened.sha256
                    refers_to = $refersTo
                    resolvable_range = $true
                    worksheet = [string]$sheet.Name
                    address = [string]$range.Address(
                        $true,
                        $true,
                        1,
                        $false
                    )
                    rows = [int]$range.Rows.Count
                    columns = [int]$range.Columns.Count
                }
            }
            finally {
                Release-ComObject $sheet
                Release-ComObject $range
                Release-ComObject $nameObject
            }
        }


        # ----------------------------------------------------
        # Exact owner cardinality
        # ----------------------------------------------------

        if ($owners.Count -ne 1) {
            $blockers += [ordered]@{
                code = "NAMED_RANGE_OWNER_CARDINALITY"
                name = $targetName
                expected_owner_count = 1
                actual_owner_count = [int]$owners.Count
                owners = $owners
            }

            continue
        }


        $owner = $owners[0]


        if (-not [bool]$owner.resolvable_range) {
            $blockers += [ordered]@{
                code = "NAMED_RANGE_NOT_RESOLVABLE"
                name = $targetName
                owner = $owner
            }

            continue
        }


        # ----------------------------------------------------
        # Shape + address validation
        # ----------------------------------------------------

        $expectedShape = (
            $ExpectedShapes[
                $targetName
            ]
        )

        $shapeIsCorrect = (
            ([int]$owner.rows -eq [int]$expectedShape[0]) -and
            ([int]$owner.columns -eq [int]$expectedShape[1])
        )

        if (-not $shapeIsCorrect) {
            $blockers += [ordered]@{
                code = "NAMED_RANGE_SHAPE_MISMATCH"
                name = $targetName
                expected_rows = [int]$expectedShape[0]
                expected_columns = [int]$expectedShape[1]
                actual_rows = [int]$owner.rows
                actual_columns = [int]$owner.columns
            }

            continue
        }


        $expectedAddress = (
            [string]$ExpectedAddresses[
                $targetName
            ]
        )

        if ([string]$owner.address -cne $expectedAddress) {
            $blockers += [ordered]@{
                code = "NAMED_RANGE_ADDRESS_MISMATCH"
                name = $targetName
                expected = $expectedAddress
                actual = [string]$owner.address
                worksheet = [string]$owner.worksheet
                refers_to = [string]$owner.refers_to
            }

            continue
        }


        # ----------------------------------------------------
        # Resolve already-open owner workbook
        # ----------------------------------------------------

        $openedOwner = $null

        foreach ($opened in $openedWorkbooks) {
            if ($opened.filename -eq $owner.workbook) {
                if ($null -ne $openedOwner) {
                    throw (
                        "Duplicate opened owner for named range " +
                        $targetName
                    )
                }

                $openedOwner = $opened
            }
        }


        if ($null -eq $openedOwner) {
            throw (
                "Internal owner resolution error for " +
                $targetName
            )
        }


        # ----------------------------------------------------
        # Capture Value2
        # ----------------------------------------------------

        $captureName = $null
        $captureRange = $null
        $captureSheet = $null

        try {
            $captureName = (
                Find-WorkbookName `
                    -Workbook $openedOwner.workbook `
                    -TargetName $targetName
            )

            if ($null -eq $captureName) {
                throw (
                    "Named range disappeared during capture: " +
                    $targetName
                )
            }


            $captureRange = (
                $captureName.RefersToRange
            )

            $captureSheet = (
                $captureRange.Worksheet
            )


            [object[]]$values = (
                Get-RangeMatrix `
                    -Range $captureRange
            )


            $diagnostics = (
                Get-Diagnostics `
                    -Values $values `
                    -ColumnCount (
                        [int]$captureRange.Columns.Count
                    )
            )


            $valuesJson = (
                $values |
                ConvertTo-Json `
                    -Depth 30 `
                    -Compress
            )


            $captures[$targetName] = [ordered]@{
                name = $targetName

                source = [ordered]@{
                    workbook = $openedOwner.filename
                    workbook_path = $openedOwner.path
                    workbook_sha256 = $openedOwner.sha256
                    worksheet = [string]$captureSheet.Name
                    refers_to = [string]$captureName.RefersTo
                    address = [string]$captureRange.Address(
                        $true,
                        $true,
                        1,
                        $false
                    )
                }

                shape = [ordered]@{
                    rows = [int]$captureRange.Rows.Count
                    columns = [int]$captureRange.Columns.Count
                }

                values_sha256 = (
                    Get-StringSha256 `
                        -Text $valuesJson
                )

                diagnostics = $diagnostics
                values = $values
            }
        }
        finally {
            Release-ComObject $captureSheet
            Release-ComObject $captureRange
            Release-ComObject $captureName
        }
    }


    # ========================================================
    # Pair alignment
    # ========================================================

    $TranslationPairs = @(
        @("TV_Words", "TA_Words"),
        @("TV_Words2", "TA_Words2"),
        @("TV_Words4", "TA_Words4"),
        @("TV_Words6", "TA_Words6")
    )


    foreach ($pair in $TranslationPairs) {
        $leftName = [string]$pair[0]
        $rightName = [string]$pair[1]

        if (-not $captures.ContainsKey($leftName)) {
            continue
        }

        if (-not $captures.ContainsKey($rightName)) {
            continue
        }

        $leftRows = [int]$captures[$leftName].shape.rows
        $rightRows = [int]$captures[$rightName].shape.rows

        if ($leftRows -ne $rightRows) {
            $blockers += [ordered]@{
                code = "TRANSLATION_PAIR_ROW_MISMATCH"
                left = $leftName
                right = $rightName
                left_rows = $leftRows
                right_rows = $rightRows
            }
        }
    }


    if (
        $captures.ContainsKey("TV_Words2") -and
        $captures.ContainsKey("TA_Words2_Loc")
    ) {
        $tvRows = [int]$captures["TV_Words2"].shape.rows
        $locRows = [int]$captures["TA_Words2_Loc"].shape.rows
        $locColumns = [int]$captures["TA_Words2_Loc"].shape.columns

        if ($tvRows -ne $locRows) {
            $blockers += [ordered]@{
                code = "ADDRESS_LOCATION_ROW_MISMATCH"
                tv_words2_rows = $tvRows
                ta_words2_loc_rows = $locRows
            }
        }

        if ($locColumns -ne 2) {
            $blockers += [ordered]@{
                code = "ADDRESS_LOCATION_COLUMN_MISMATCH"
                expected_columns = 2
                actual_columns = $locColumns
            }
        }
    }


    # ========================================================
    # Report
    # ========================================================

    if ($blockers.Count -eq 0) {
        $status = "TRANSLATION_DICTIONARIES_CAPTURED"
    }
    else {
        $status = "TRANSLATION_DICTIONARIES_BLOCKED"
    }


    $sourceWorkbookReports = @()

    foreach ($opened in $openedWorkbooks) {
        $sourceWorkbookReports += [ordered]@{
            filename = $opened.filename
            path = $opened.path
            sha256 = $opened.sha256
        }
    }


    $dictionaryReports = [ordered]@{}

    foreach ($targetName in $TargetNames) {
        if ($captures.ContainsKey($targetName)) {
            $dictionaryReports[$targetName] = (
                $captures[$targetName]
            )
        }
    }


    $report = [ordered]@{
        schema_version = (
            "c5e-certificate-detail-" +
            "translation-dictionary-capture/v4"
        )

        status = $status

        source_workbooks = (
            $sourceWorkbookReports
        )

        summary = [ordered]@{
            requested_named_ranges = [int]$TargetNames.Count
            captured_named_ranges = [int]$dictionaryReports.Count
            blockers = [int]$blockers.Count
        }

        dictionaries = (
            $dictionaryReports
        )

        blockers = (
            $blockers
        )

        invariants = [ordered]@{
            ascii_only_script = $true
            excel_opened_read_only = $true
            xlsb_discovered_by_extension = $true
            xlam_discovered_by_extension = $true
            owner_cardinality_must_equal_one = $true
            address_checked_against_inventory = $true
            exact_shape_checked = $true
            worksheet_name_recorded_not_hardcoded = $true
            values_captured_from_refers_to_range = $true
            source_workbook_sha256_captured = $true
            values_sha256_captured = $true
            translation_pair_cardinality_checked = $true
            blanks_and_duplicates_profiled_not_removed = $true
            source_values_not_normalized = $true
            gdp_in_scope = $false
            unkeyed_entries_used = $false
        }
    }


    # ========================================================
    # Persist JSON UTF-8 without BOM
    # ========================================================

    $outputPath = (
        [System.IO.Path]::GetFullPath(
            $Output
        )
    )

    $outputDirectory = (
        Split-Path `
            -Parent `
            $outputPath
    )


    New-Item `
        -ItemType Directory `
        -Force `
        -Path $outputDirectory |
        Out-Null


    $json = (
        $report |
        ConvertTo-Json `
            -Depth 40
    )


    $utf8NoBom = (
        New-Object `
            System.Text.UTF8Encoding(
                $false
            )
    )


    [System.IO.File]::WriteAllText(
        $outputPath,
        $json + [Environment]::NewLine,
        $utf8NoBom
    )


    # ========================================================
    # Console output
    # ========================================================

    Write-Host (
        "STATUS=" +
        $report.status
    )

    Write-Host (
        "REQUESTED_NAMED_RANGES=" +
        $report.summary.requested_named_ranges
    )

    Write-Host (
        "CAPTURED_NAMED_RANGES=" +
        $report.summary.captured_named_ranges
    )

    Write-Host (
        "BLOCKERS=" +
        $report.summary.blockers
    )


    foreach ($targetName in $TargetNames) {
        if (-not $captures.ContainsKey($targetName)) {
            continue
        }

        $item = (
            $captures[$targetName]
        )

        Write-Host (
            "RANGE=" +
            $targetName +
            "|" +
            $item.source.workbook +
            "|" +
            $item.source.worksheet +
            "|" +
            $item.source.address +
            "|rows=" +
            $item.shape.rows +
            "|cols=" +
            $item.shape.columns +
            "|blank=" +
            $item.diagnostics.blank_cells +
            "|duplicates=" +
            $item.diagnostics.duplicate_value_count +
            "|sha256=" +
            $item.values_sha256
        )
    }


    foreach ($blocker in $blockers) {
        $blockerJson = (
            $blocker |
            ConvertTo-Json `
                -Depth 15 `
                -Compress
        )

        Write-Host (
            "BLOCKER=" +
            $blockerJson
        )
    }


    Write-Host (
        "OUTPUT=" +
        $outputPath
    )


    if ($blockers.Count -gt 0) {
        exit 1
    }
}
finally {
    # ========================================================
    # Always close source workbooks without saving
    # ========================================================

    foreach ($opened in $openedWorkbooks) {
        if ($null -eq $opened.workbook) {
            continue
        }

        try {
            $opened.workbook.Close(
                $false
            )
        }
        catch {
        }

        Release-ComObject (
            $opened.workbook
        )
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