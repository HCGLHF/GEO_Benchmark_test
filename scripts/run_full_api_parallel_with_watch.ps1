param(
  [string]$Config = "config\client_acquisition_simulator.yaml",
  [ValidateSet("test", "quick", "standard")]
  [string]$RunMode = "quick",
  [Nullable[int]]$QueriesPerModel = $null,
  [string]$RunRoot = "runs\full_api_parallel",
  [string]$RunStamp = "",
  [int]$MonitorIntervalSeconds = 30,
  [string]$SeedQueriesRunDir = "",
  [string]$ProgressHtmlPath = "",
  [Alias("Models")]
  [string[]]$SelectedModels = @(),
  [switch]$IncludeDoubao,
  [switch]$SkipMerge,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$runnerArgs = @(
  "scripts\full_api_parallel_runner.py",
  "--config", $Config,
  "--run-mode", $RunMode,
  "--run-root", $RunRoot,
  "--monitor-interval-seconds", "$MonitorIntervalSeconds"
)

if ($RunStamp) {
  $runnerArgs += @("--run-stamp", $RunStamp)
}

if ($null -ne $QueriesPerModel) {
  $runnerArgs += @("--queries-per-model", "$QueriesPerModel")
}

if ($SeedQueriesRunDir) {
  $runnerArgs += @("--seed-queries-run-dir", $SeedQueriesRunDir)
}

if ($ProgressHtmlPath) {
  $runnerArgs += @("--progress-html-path", $ProgressHtmlPath)
}

foreach ($modelEntry in $SelectedModels) {
  $runnerArgs += @("--models", $modelEntry)
}

if ($IncludeDoubao) {
  $runnerArgs += "--include-doubao"
}

if ($SkipMerge) {
  $runnerArgs += "--skip-merge"
}

if ($DryRun) {
  $runnerArgs += "--dry-run"
}

& python @runnerArgs
exit $LASTEXITCODE
