param(
  [string]$Config = "config\client_acquisition_simulator.yaml",
  [ValidateSet("quick", "standard")]
  [string]$RunMode = "quick",
  [Nullable[int]]$QueriesPerModel = $null,
  [string]$RunRoot = "runs\full_api_parallel",
  [switch]$IncludeDoubao
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
  "google/gemini-3.5-flash",
  "perplexity/sonar-pro",
  "deepseek/deepseek-v4-flash",
  "qwen/qwen3.7-max",
  "x-ai/grok-build-0.1"
)

if ($IncludeDoubao) {
  $models += "bytedance-seed/seed-2.0-pro"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$root = Join-Path $RunRoot $stamp
New-Item -ItemType Directory -Force -Path $root | Out-Null

Write-Host "Starting full API single-model runs under $root"
Write-Host "Run mode: $RunMode"
Write-Host "Queries per model: $QueriesPerModel"

foreach ($model in $models) {
  $safeName = $model.Replace("/", "_").Replace(":", "_")
  $outDir = Join-Path $root $safeName
  $argsList = @(
    "scripts\run_full_api_client_acquisition.py",
    "--config", $Config,
    "--include-model", $model,
    "--queries-per-model", "$QueriesPerModel",
    "--output-dir", $outDir
  )
  Write-Host "Launching $model -> $outDir"
  Start-Process -FilePath "python" -ArgumentList $argsList -WorkingDirectory (Get-Location)
}

Write-Host ""
Write-Host "All model windows launched."
Write-Host "After they finish, merge with:"
Write-Host "python scripts\merge_full_api_runs.py --config $Config --runs $($models | ForEach-Object { Join-Path $root ($_.Replace('/', '_').Replace(':', '_')) }) --output-dir $root\merged"
