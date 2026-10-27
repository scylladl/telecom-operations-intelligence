<#
    Rebuilds everything from zero (acceptance criterion AC-01):
      1. creates or updates the database objects (database\deploy.ps1)
      2. generates the simulated client exports (generator\generate_source_data.py)
      3. loads them into the ops schema (database\load_source_data.ps1)

    Usage:  powershell -ExecutionPolicy Bypass -File build.ps1 [-Server localhost] [-Seed 42]
    Needs: SQL Server reachable with Windows authentication, Python 3.10+ on PATH.
#>
param(
    [string]$Server = "localhost",
    [int]$Seed = 42
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

& "$root\database\deploy.ps1" -Server $Server

python -X utf8 "$root\generator\generate_source_data.py" --seed $Seed --out "$root\data\generated"
if ($LASTEXITCODE -ne 0) { throw "Data generator failed (exit code $LASTEXITCODE)" }

& "$root\database\load_source_data.ps1" -Server $Server -DataFolder "$root\data\generated"
