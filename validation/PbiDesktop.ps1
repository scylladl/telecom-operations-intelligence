<#
    Helpers to query the semantic model open in Power BI Desktop through its local
    Analysis Services engine (the same route DAX Studio uses). Dot-source this file:
        . .\validation\PbiDesktop.ps1
        Invoke-Dax "EVALUATE ROW(""Incidents"", [Incidents])"
#>

function Get-PbiDesktopPort {
    $files = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces\*\Data\msmdsrv.port.txt",
                                 "$env:USERPROFILE\Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces\*\Data\msmdsrv.port.txt" `
                           -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    if (-not $files) { throw "Power BI Desktop is not running with a model open." }
    [IO.File]::ReadAllText($files[0].FullName, [Text.Encoding]::Unicode).Trim()
}

function Import-PbiClientLibraries {
    $desktop = Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop | Select-Object -First 1
    $bin = if ($desktop) { Join-Path $desktop.InstallLocation "bin" } else { "C:\Program Files\Microsoft Power BI Desktop\bin" }
    Add-Type -Path (Join-Path $bin "Microsoft.PowerBI.AdomdClient.dll")
    Add-Type -Path (Join-Path $bin "Microsoft.PowerBI.Tabular.dll")
}

function Invoke-Dax([string]$Query) {
    $connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$script:PbiPort"
    $connection.Open()
    try {
        $command = $connection.CreateCommand()
        $command.CommandText = $Query
        $adapter = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdDataAdapter $command
        $table = New-Object System.Data.DataTable
        [void]$adapter.Fill($table)
        , $table
    }
    finally { $connection.Close() }
}

Import-PbiClientLibraries
$script:PbiPort = Get-PbiDesktopPort
