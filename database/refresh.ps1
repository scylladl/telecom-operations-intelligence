<#
    Processing cycle of the analytics layer, meant to run on a schedule before the
    Power BI refresh (sequence in docs/03-data-model.md, "Refresh"):
      1. dw.usp_Refresh   rebuilds dw when the source changed (or always with -Force)
      2. dq.usp_RunChecks runs the data quality checks
    Exits with an error when processing or any check fails, so an orchestrator can
    hold the Power BI refresh.

    Usage:  powershell -ExecutionPolicy Bypass -File database\refresh.ps1 [-Server localhost] [-Force]
#>
param(
    [string]$Server = "localhost",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$connection = New-Object System.Data.SqlClient.SqlConnection "Server=$Server;Database=NorthGridOps;Integrated Security=True;Encrypt=True;TrustServerCertificate=True"
$connection.Open()
try {
    Write-Host "Running dw.usp_Refresh"
    $command = $connection.CreateCommand()
    $command.CommandText = "EXEC dw.usp_Refresh @Force = @Force;"
    [void]$command.Parameters.AddWithValue("@Force", [bool]$Force)
    $command.CommandTimeout = 900
    [void]$command.ExecuteNonQuery()

    $command = $connection.CreateCommand()
    $command.CommandText = "SELECT TOP (1) Status, DurationMs, Message FROM dw.RefreshLog ORDER BY RefreshId DESC;"
    $reader = $command.ExecuteReader()
    [void]$reader.Read()
    Write-Host ("dw.usp_Refresh: {0} in {1} ms {2}" -f $reader["Status"], $reader["DurationMs"], $reader["Message"])
    $reader.Close()

    Write-Host "Running dq.usp_RunChecks"
    $command = $connection.CreateCommand()
    $command.CommandText = "EXEC dq.usp_RunChecks;"
    $command.CommandTimeout = 300
    $table = New-Object System.Data.DataTable
    $table.Load($command.ExecuteReader())
    $table | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

    $failed = @($table | Where-Object { $_.Result -ne 'Pass' })
    if ($failed.Count -gt 0) { throw "$($failed.Count) data quality check(s) failed" }
}
finally {
    $connection.Close()
}
