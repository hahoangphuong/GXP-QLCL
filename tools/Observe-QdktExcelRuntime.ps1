# Requires Windows PowerShell 5.1/.NET Framework. Operator-run observation only.
# Never invoked automatically by the audit or by the coding agent.
param(
    [switch]$AuthorizedObservation,
    [int]$TargetExcelProcessId = 0,
    [string]$CollectorId = ''
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Fail-Observation([string]$Code) {
    [ordered]@{schema_version='qdkt-excel-observation-error/v1'; diagnostic_code=$Code;
        runtime_identity_verified=$false; blocker='UNVERIFIED_VERSION_BINDING'; ready_to_render=$false} |
        ConvertTo-Json -Depth 5 -Compress
    exit 2
}
if (-not $AuthorizedObservation) { Fail-Observation 'QDKT_OPERATOR_OBSERVATION_REQUIRED' }
if ($PSVersionTable.PSEdition -ne 'Desktop') { Fail-Observation 'QDKT_OBSERVATION_PLATFORM_UNSUPPORTED' }
if ($TargetExcelProcessId -le 0 -or [string]::IsNullOrWhiteSpace($CollectorId) -or $CollectorId.Length -gt 128) {
    Fail-Observation 'QDKT_OBSERVATION_CONTEXT_REQUIRED'
}
$excelApp = $null; $workbooks = $null; $workbook = $null; $addins = $null
try {
    $started = [DateTimeOffset]::UtcNow.ToString('o')
    $before = Get-Process -Id $TargetExcelProcessId
    if ($before.ProcessName -ne 'EXCEL') { throw 'Wrong process' }
    $processStarted = $before.StartTime.ToUniversalTime().ToString('o')
    # Attach only to an existing ROT object; never create or launch Excel.
    $excelApp = [Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application')
    if (-not ('QdktObservationWindow' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class QdktObservationWindow {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
}
'@ | Out-Null
    }
    $windowHandle = [IntPtr]([long]$excelApp.Hwnd)
    [uint32]$observedExcelProcessId = 0
    [void][QdktObservationWindow]::GetWindowThreadProcessId($windowHandle, [ref]$observedExcelProcessId)
    if ($observedExcelProcessId -ne $TargetExcelProcessId) { throw 'ROT instance mismatch' }
    # Loaded add-ins need explicit filename lookup; enumeration is not exhaustive.
    $workbooks = $excelApp.Workbooks
    $workbook = $workbooks.Item('GPs.xlam')
    $loaded = [ordered]@{workbook_name=[string]$workbook.Name; full_path=[string]$workbook.FullName;
        excel_version=[string]$excelApp.Version; excel_build=[string]$excelApp.Build}
    $available = @()
    $addins = $excelApp.AddIns
    if ($addins.Count -gt 1024) { throw 'Inventory budget exceeded' }
    for ($index = 1; $index -le $addins.Count; $index++) {
        $candidate = $null
        try {
            $candidate = $addins.Item($index)
            if ([string]$candidate.Name -ieq 'GPs.xlam') {
                $available += [ordered]@{name=[string]$candidate.Name; full_path=[string]$candidate.FullName;
                    installed=[bool]$candidate.Installed}
            }
        } finally {
            if ($null -ne $candidate -and [Runtime.InteropServices.Marshal]::IsComObject($candidate)) {
                [void][Runtime.InteropServices.Marshal]::ReleaseComObject($candidate)
            }
        }
    }
    $processIds = @(Get-Process -Name EXCEL | ForEach-Object { [int]$_.Id })
    if ($processIds.Count -gt 1024) { throw 'Process budget exceeded' }
    $after = Get-Process -Id $TargetExcelProcessId
    $afterStarted = $after.StartTime.ToUniversalTime().ToString('o')
    if ($processStarted -ne $afterStarted -or $after.ProcessName -ne 'EXCEL') { throw 'Process changed' }
    [ordered]@{
        schema_version='qdkt-excel-observation/v1'; collector_id=$CollectorId;
        acquisition_method='AUTHORIZED_OPERATOR_READ_ONLY_EXISTING_EXCEL_COM';
        capture_started_at=$started; capture_completed_at=[DateTimeOffset]::UtcNow.ToString('o');
        process=[ordered]@{pid=$TargetExcelProcessId; started_at=$processStarted; started_at_after=$afterStarted;
            session_id=[int]$after.SessionId; hwnd=('0x{0:X}' -f $windowHandle.ToInt64()); hwnd_pid=[int]$observedExcelProcessId};
        loaded_addin=$loaded; available_addins=@($available); excel_process_ids=@($processIds);
        inventory_scope='TARGET_ROT_INSTANCE_AVAILABLE_ADDINS_NOT_EXHAUSTIVE_LOADED_CODE';
        runtime_module_source_status='NOT_COLLECTED'; on_disk=$null
    } | ConvertTo-Json -Depth 8
} catch {
    Fail-Observation 'QDKT_EXCEL_OBSERVATION_UNAVAILABLE_OR_SESSION_MISMATCH'
} finally {
    foreach ($reference in @($workbook, $workbooks, $addins, $excelApp)) {
        if ($null -ne $reference -and [Runtime.InteropServices.Marshal]::IsComObject($reference)) {
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($reference)
        }
    }
}
