param(
  [string]$Config = "config\client_acquisition_simulator.yaml",
  [int]$QueriesPerModel = 200,
  [string]$RunRoot = "runs\full_api_parallel",
  [int]$MonitorIntervalSeconds = 30,
  [switch]$IncludeDoubao,
  [switch]$SkipMerge,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

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

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$root = Join-Path $RunRoot $stamp
$cacheRoot = Join-Path $root "cache"
$mergedDir = Join-Path $root "merged"

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
  Write-Host "Queries per model: $QueriesPerModel"
  Write-Host ""
  foreach ($worker in $workers) {
    Write-Host "Model: $($worker.Model)"
    Write-Host "Run dir: $($worker.RunDir)"
    Write-Host "Cache: $($worker.CachePath)"
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
Write-Host "Queries per model: $QueriesPerModel"
Write-Host "Monitor interval: $MonitorIntervalSeconds seconds"
Write-Host ""

foreach ($worker in $workers) {
  New-Item -ItemType Directory -Force -Path $worker.RunDir | Out-Null
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
  $process = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $workerCommand) -WorkingDirectory (Get-Location) -PassThru
  $worker.Process = $process
}

Write-Host ""
Write-Host "Monitoring active runs. Press Ctrl+C to stop this monitor; child model windows will continue."

while (($workers | Where-Object { -not $_.Process.HasExited }).Count -gt 0) {
  Write-Host ""
  Write-Host "===== Full API parallel progress $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====="
  foreach ($worker in $workers) {
    Write-Host ""
    Write-Host "----- $($worker.Model) -----"
    python scripts\watch_full_api_run.py --run-dir $worker.RunDir
  }
  Start-Sleep -Seconds $MonitorIntervalSeconds
}

Write-Host ""
Write-Host "All model processes exited. Final status:"
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
