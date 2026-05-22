param(
  [string]$Config = "config\client_acquisition_simulator.yaml",
  [ValidateSet("quick", "standard")]
  [string]$RunMode = "quick",
  [Nullable[int]]$QueriesPerModel = $null,
  [string]$RunRoot = "runs\full_api_parallel",
  [int]$MonitorIntervalSeconds = 30,
  [string]$SeedQueriesRunDir = "",
  [string]$ProgressHtmlPath = "",
  [switch]$IncludeDoubao,
  [switch]$SkipMerge,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($null -eq $QueriesPerModel) {
  if ($RunMode -eq "standard") {
    $QueriesPerModel = 200
  } else {
    $QueriesPerModel = 50
  }
}

$models = @(
  "openai/gpt-4.1-mini",
  "google/gemini-2.5-flash",
  "perplexity/sonar-pro",
  "deepseek/deepseek-chat"
)

if ($IncludeDoubao) {
  $models += "bytedance-seed/seed-2.0-pro"
}

function ConvertTo-SafeName {
  param([string]$Value)
  return $Value.Replace("/", "_").Replace(":", "_")
}

function Quote-Arg {
  param([string]$Value)
  return '"' + $Value.Replace('"', '\"') + '"'
}

function Get-SeedQueries {
  param(
    [string]$SeedRunDir,
    [string]$Model,
    [int]$Limit = 0
  )
  if (-not $SeedRunDir) {
    return @()
  }
  $seedPath = Join-Path $SeedRunDir "api_queries.csv"
  if (-not (Test-Path $seedPath)) {
    throw "Seed queries file not found: $seedPath"
  }
  $rows = @(Import-Csv $seedPath | Where-Object { $_.scenario_model -eq $Model })
  if ($Limit -gt 0) {
    $rows = @($rows | Select-Object -First $Limit)
  }
  return $rows
}

function Write-SeedQueries {
  param(
    [string]$SeedRunDir,
    [string]$Model,
    [string]$OutDir
  )
  if (-not $SeedRunDir) {
    return 0
  }
  $rows = @(Get-SeedQueries -SeedRunDir $SeedRunDir -Model $Model -Limit $QueriesPerModel)
  if ($rows.Count -eq 0) {
    throw "No seeded queries found for model $Model in $SeedRunDir"
  }
  $seedArgs = @(
    "scripts\seed_api_queries.py",
    "--seed-run-dir", $SeedRunDir,
    "--model", $Model,
    "--output-dir", $OutDir,
    "--limit", "$QueriesPerModel"
  )
  & python @seedArgs | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to seed queries for model $Model from $SeedRunDir"
  }
  return $rows.Count
}

function Render-ProgressHtml {
  param(
    [array]$RunDirs,
    [string]$OutputPath
  )
  $htmlArgs = @(
    "scripts\render_full_api_progress_html.py",
    "--run-dirs"
  ) + $RunDirs + @(
    "--output", $OutputPath,
    "--title", "Full API Parallel Progress"
  )
  & python @htmlArgs | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not render progress HTML at $OutputPath"
  }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$root = Join-Path $RunRoot $stamp
$cacheRoot = Join-Path $root "cache"
$mergedDir = Join-Path $root "merged"
if (-not $ProgressHtmlPath) {
  $ProgressHtmlPath = Join-Path $root "progress.html"
}

$runDirs = @()
$workers = @()

foreach ($model in $models) {
  $safeName = ConvertTo-SafeName $model
  $outDir = Join-Path $root $safeName
  $cachePath = Join-Path $cacheRoot "$safeName.sqlite"
  $runDirs += $outDir
  $pythonArgs = @(
    "scripts\run_full_api_client_acquisition.py",
    "--config", $Config,
    "--include-model", $model,
    "--queries-per-model", "$QueriesPerModel",
    "--output-dir", $outDir,
    "--cache-path", $cachePath
  )
  $command = "python " + (($pythonArgs | ForEach-Object { Quote-Arg $_ }) -join " ")
  $workers += [pscustomobject]@{
    Model = $model
    SafeName = $safeName
    RunDir = $outDir
    CachePath = $cachePath
    SeededQueryCount = if ($SeedQueriesRunDir) { @(Get-SeedQueries -SeedRunDir $SeedQueriesRunDir -Model $model -Limit $QueriesPerModel).Count } else { 0 }
    Command = $command
    Process = $null
  }
}

$mergeArgs = @(
  "scripts\merge_full_api_runs.py",
  "--config", $Config,
  "--runs"
) + $runDirs + @("--output-dir", $mergedDir)
$mergeCommand = "python " + (($mergeArgs | ForEach-Object { Quote-Arg $_ }) -join " ")

if ($DryRun) {
  Write-Host "DRY RUN: full API parallel run with monitoring"
  Write-Host "Run root: $root"
  Write-Host "Run mode: $RunMode"
  Write-Host "Queries per model: $QueriesPerModel"
  Write-Host "Progress HTML: $ProgressHtmlPath"
  if ($SeedQueriesRunDir) {
    Write-Host "Seed queries run: $SeedQueriesRunDir"
    Write-Host "Scenario generation will resume from seeded api_queries.csv"
  }
  Write-Host ""
  foreach ($worker in $workers) {
    Write-Host "Model: $($worker.Model)"
    Write-Host "Run dir: $($worker.RunDir)"
    Write-Host "Cache: $($worker.CachePath)"
    if ($SeedQueriesRunDir) {
      Write-Host "Seeded queries: $($worker.SeededQueryCount)"
    }
    Write-Host $worker.Command
    Write-Host "Watch: python scripts\watch_full_api_run.py --run-dir $($worker.RunDir)"
    Write-Host ""
  }
  Write-Host "Merge:"
  Write-Host $mergeCommand
  exit 0
}

New-Item -ItemType Directory -Force -Path $root | Out-Null
New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null

Write-Host "Starting full API single-model runs under $root"
Write-Host "Run mode: $RunMode"
Write-Host "Queries per model: $QueriesPerModel"
Write-Host "Monitor interval: $MonitorIntervalSeconds seconds"
Write-Host "Progress HTML: $ProgressHtmlPath"
Write-Host ""

foreach ($worker in $workers) {
  New-Item -ItemType Directory -Force -Path $worker.RunDir | Out-Null
  if ($SeedQueriesRunDir) {
    $seededCount = Write-SeedQueries -SeedRunDir $SeedQueriesRunDir -Model $worker.Model -OutDir $worker.RunDir
    Write-Host "Seeded $seededCount existing queries for $($worker.Model)"
  }
  $exitCodePath = Join-Path $worker.RunDir "worker_exit_code.txt"
  $logPath = Join-Path $worker.RunDir "worker.log"
  $workerCommand = @"
`$ErrorActionPreference = 'Continue'
Set-Location "$(Get-Location)"
Write-Host "Running $($worker.Model)"
$($worker.Command) *>&1 | Tee-Object -FilePath "$logPath"
`$exitCode = `$LASTEXITCODE
  Set-Content -Path "$exitCodePath" -Value `$exitCode
exit `$exitCode
"@
  Write-Host "Launching $($worker.Model) -> $($worker.RunDir)"
  $process = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $workerCommand) -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
  $worker.Process = $process
}

Write-Host ""
Write-Host "Monitoring active runs. Press Ctrl+C to stop this monitor; child model processes will continue."
Render-ProgressHtml -RunDirs $runDirs -OutputPath $ProgressHtmlPath

while (($workers | Where-Object { -not $_.Process.HasExited }).Count -gt 0) {
  Write-Host ""
  Write-Host "===== Full API parallel progress $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====="
  foreach ($worker in $workers) {
    Write-Host ""
    Write-Host "----- $($worker.Model) -----"
    python scripts\watch_full_api_run.py --run-dir $worker.RunDir
  }
  Render-ProgressHtml -RunDirs $runDirs -OutputPath $ProgressHtmlPath
  Start-Sleep -Seconds $MonitorIntervalSeconds
}

Write-Host ""
Write-Host "All model processes exited. Final status:"
Render-ProgressHtml -RunDirs $runDirs -OutputPath $ProgressHtmlPath
$failed = @()
foreach ($worker in $workers) {
  $exitCodePath = Join-Path $worker.RunDir "worker_exit_code.txt"
  $exitCode = if (Test-Path $exitCodePath) { [int](Get-Content $exitCodePath -TotalCount 1) } else { $worker.Process.ExitCode }
  Write-Host "$($worker.Model): exit $exitCode"
  if ($exitCode -ne 0) {
    $failed += $worker
  }
}

if ($failed.Count -gt 0) {
  Write-Error "One or more model runs failed. Skipping merge. Inspect worker.log files under $root."
  exit 1
}

if ($SkipMerge) {
  Write-Host "SkipMerge set. Merge command:"
  Write-Host $mergeCommand
  exit 0
}

Write-Host ""
Write-Host "Merging model runs..."
Invoke-Expression $mergeCommand
Write-Host ""
Write-Host "Merged report: $(Join-Path $mergedDir 'competitive_gap_report.md')"
