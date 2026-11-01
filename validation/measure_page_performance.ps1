<#
    Measures the query time of every report page against the model open in Power BI Desktop.
    For each page: clears the engine cache, then runs the DAX query of every data visual (extracted
    with `pbir visuals query`) one after another. Desktop runs them in parallel, so the sequential
    total is an upper bound of the page's query time; rendering time is not included.

    Needs: Power BI Desktop with the report open, and the pbir CLI.
    Usage:  powershell -ExecutionPolicy Bypass -File validation\measure_page_performance.ps1
#>
param(
    [string]$Pbir = "pbir",
    [string[]]$Pages = @("Overview", "SLA and Restoration", "Repeat and Chronic", "Backlog and Aging",
                         "Improvement Actions", "Data Quality", "Circuit Detail")
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "PbiDesktop.ps1")

$report = Join-Path $PSScriptRoot "..\powerbi\NorthGridOps.Report"
$work = Join-Path $env:TEMP "ngo_page_queries"
New-Item -ItemType Directory -Force -Path $work | Out-Null

$connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$script:PbiPort"
$connection.Open()
$databaseId = $connection.Database

$results = foreach ($page in $Pages) {
    $listing = & $Pbir -q --output-format json ls "$report/$page.Page" | ConvertFrom-Json
    $visuals = $listing.visuals | Where-Object { $_.type -notin @("textbox", "pageNavigator", "actionButton", "shape", "image") }

    $clear = $connection.CreateCommand()
    $clear.CommandText = "<ClearCache xmlns=""http://schemas.microsoft.com/analysisservices/2003/engine""><Object><DatabaseID>$databaseId</DatabaseID></Object></ClearCache>"
    [void]$clear.ExecuteNonQuery()

    $notMeasured = @()
    $times = foreach ($visual in $visuals) {
        $file = Join-Path $work "$($visual.id).dax"
        Remove-Item $file -ErrorAction SilentlyContinue
        & $Pbir -q visuals query "$report/$page.Page/$($visual.id).Visual" -o $file | Out-Null
        if (-not (Test-Path $file)) { $notMeasured += $visual.id; continue }
        $command = $connection.CreateCommand()
        $command.CommandText = Get-Content $file -Raw
        try {
            $watch = [Diagnostics.Stopwatch]::StartNew()
            $reader = $command.ExecuteReader()
            while ($reader.Read()) { }
            $reader.Close()
            $watch.Stop()
            $watch.Elapsed.TotalMilliseconds
        }
        catch {
            # the extracted query is an approximation of Desktop's; a few shapes are not valid DAX
            $notMeasured += $visual.id
        }
    }
    [pscustomobject]@{
        Page            = $page
        Measured        = @($times).Count
        TotalMs         = [math]::Round(($times | Measure-Object -Sum).Sum)
        SlowestVisualMs = [math]::Round(($times | Measure-Object -Maximum).Maximum)
        NotMeasured     = $notMeasured -join ", "
    }
}
$connection.Close()

$results | Format-Table -AutoSize | Out-String | Write-Host
