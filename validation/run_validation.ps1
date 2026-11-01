<#
    AC-03: compares K1, K3, K4, K5, K7 and K9 between SQL (validation_queries.sql, straight
    from the source tables) and the Power BI measures of the model open in Power BI Desktop.

    Needs: the report open in Power BI Desktop with its data refreshed after the last
    dw.usp_Refresh run.

    Usage:  powershell -ExecutionPolicy Bypass -File validation\run_validation.ps1 [-Server localhost]
    Writes: validation\results.csv
#>
param(
    [string]$Server = "localhost"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "PbiDesktop.ps1")

# ---------- SQL side
$connection = New-Object System.Data.SqlClient.SqlConnection "Server=$Server;Database=NorthGridOps;Integrated Security=True;Encrypt=True;TrustServerCertificate=True"
$connection.Open()
$command = $connection.CreateCommand()
$command.CommandText = Get-Content (Join-Path $PSScriptRoot "validation_queries.sql") -Raw
$command.CommandTimeout = 300
$sql = New-Object System.Data.DataTable
$sql.Load($command.ExecuteReader())
$connection.Close()

# ---------- DAX side: the same three cases as filters on the model
$filters = @{
    1 = "TREATAS ( { ""2025-12"" }, 'Date'[Year Month] )"
    2 = "TREATAS ( { ""2025-12"" }, 'Date'[Year Month] ), TREATAS ( { ""South"" }, 'Circuit'[Region] )"
    3 = "TREATAS ( { ""NG-FWA-001453"" }, 'Circuit'[Circuit Id] )"
}
$kpis = [ordered]@{
    K1_Incidents = @{ Measure = "[Incidents]";               Tolerance = 0 }
    K3_MttrHours = @{ Measure = "[MTTR (h)]";                Tolerance = 0.01 }   # dw stores hours with 2 decimals
    K4_SlaPct    = @{ Measure = "[SLA Compliance %]";        Tolerance = 0.000001 }
    K5_RepeatPct = @{ Measure = "[Repeat Rate %]";           Tolerance = 0.000001 }
    K7_Backlog   = @{ Measure = "[Open Backlog]";            Tolerance = 0 }
    K9_Before    = @{ Measure = "[Incidents Before Action]"; Tolerance = 0 }
    K9_After     = @{ Measure = "[Incidents After Action]";  Tolerance = 0 }
}

$results = foreach ($row in $sql.Rows) {
    $columns = ($kpis.GetEnumerator() | ForEach-Object { """$($_.Key)"", $($_.Value.Measure)" }) -join ", "
    $dax = Invoke-Dax "EVALUATE CALCULATETABLE ( ROW ( $columns ), $($filters[[int]$row.CaseId]) )"
    foreach ($kpi in $kpis.Keys) {
        $sqlValue = if ($row[$kpi] -is [DBNull]) { $null } else { [double]$row[$kpi] }
        $daxRaw = $dax.Rows[0]["[$kpi]"]
        $daxValue = if ($daxRaw -is [DBNull]) { $null } else { [double]$daxRaw }
        # COUNTROWS over an empty set is BLANK in DAX where SQL COUNT gives 0: same value for counts
        if ($null -eq $daxValue -and $sqlValue -eq 0 -and $kpis[$kpi].Tolerance -eq 0) { $daxValue = 0 }
        $match = if ($null -eq $sqlValue -or $null -eq $daxValue) { $sqlValue -eq $daxValue }
                 else { [math]::Abs($sqlValue - $daxValue) -le $kpis[$kpi].Tolerance }
        [pscustomobject]@{ TestCase = $row.CaseName; Kpi = $kpi; Sql = $sqlValue; PowerBI = $daxValue; Match = $match }
    }
}

$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
$results | Export-Csv -Path (Join-Path $PSScriptRoot "results.csv") -NoTypeInformation -Encoding UTF8
$failed = @($results | Where-Object { -not $_.Match })
Write-Host ("{0} checks, {1} mismatches" -f $results.Count, $failed.Count)
if ($failed.Count -gt 0) { exit 1 }
