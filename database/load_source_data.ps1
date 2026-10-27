<#
    Loads the simulated client exports (data/generated/*.csv) into the ops schema.
    Replaces the previous content of each ops table, inside one transaction.
    Uses Windows authentication and the .NET client built into Windows PowerShell.

    Usage:  powershell -ExecutionPolicy Bypass -File database\load_source_data.ps1 [-Server localhost]
#>
param(
    [string]$Server = "localhost",
    [string]$DataFolder = (Join-Path $PSScriptRoot "..\data\generated")
)

$ErrorActionPreference = "Stop"
$invariant = [System.Globalization.CultureInfo]::InvariantCulture

# CSV file -> target table, in load order
$files = [ordered]@{
    "customers.csv"           = "ops.Customer"
    "circuits.csv"            = "ops.Circuit"
    "incidents.csv"           = "ops.Incident"
    "improvement_actions.csv" = "ops.ImprovementAction"
}

function ConvertTo-ColumnValue([string]$text, [type]$type) {
    if ($text -eq "") { return [DBNull]::Value }   # the exports write NULL as an empty field
    switch ($type) {
        ([datetime]) { return [datetime]::Parse($text, $invariant) }
        ([int])      { return [int]::Parse($text, $invariant) }
        ([bool])     { return $text -eq "1" }
        default      { return $text }
    }
}

$connection = New-Object System.Data.SqlClient.SqlConnection "Server=$Server;Database=NorthGridOps;Integrated Security=True;Encrypt=True;TrustServerCertificate=True"
$connection.Open()
$transaction = $connection.BeginTransaction()
try {
    foreach ($file in $files.Keys) {
        $table = $files[$file]
        $path = Join-Path $DataFolder $file
        if (-not (Test-Path $path)) { throw "Missing $path. Run generator\generate_source_data.py first." }

        # an empty DataTable with the target table's column types
        $schema = New-Object System.Data.DataTable
        $adapter = New-Object System.Data.SqlClient.SqlDataAdapter "SELECT * FROM $table WHERE 1 = 0", $connection
        $adapter.SelectCommand.Transaction = $transaction
        [void]$adapter.FillSchema($schema, [System.Data.SchemaType]::Source)

        foreach ($row in (Import-Csv -Path $path -Encoding UTF8)) {
            $values = foreach ($column in $schema.Columns) {
                ConvertTo-ColumnValue $row.($column.ColumnName) $column.DataType
            }
            [void]$schema.Rows.Add([object[]]$values)
        }

        $delete = $connection.CreateCommand()
        $delete.Transaction = $transaction
        $delete.CommandText = "DELETE FROM $table"
        [void]$delete.ExecuteNonQuery()

        $bulk = New-Object System.Data.SqlClient.SqlBulkCopy($connection, [System.Data.SqlClient.SqlBulkCopyOptions]::Default, $transaction)
        $bulk.DestinationTableName = $table
        $bulk.BulkCopyTimeout = 600
        foreach ($column in $schema.Columns) { [void]$bulk.ColumnMappings.Add($column.ColumnName, $column.ColumnName) }
        $bulk.WriteToServer($schema)
        Write-Host ("{0,-24} {1,7} rows" -f $table, $schema.Rows.Count)
    }
    $transaction.Commit()
}
catch {
    $transaction.Rollback()
    throw
}
finally {
    $connection.Close()
}
