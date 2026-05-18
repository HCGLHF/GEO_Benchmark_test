param(
  [string]$Config = "config\client_acquisition_simulator.yaml",
  [int]$QueriesPerModel = 200,
  [string]$RunRoot = "runs\full_api_parallel",
  [switch]$IncludeDoubao
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

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$root = Join-Path $RunRoot $stamp
New-Item -ItemType Directory -Force -Path $root | Out-Null

Write-Host "Starting full API single-model runs under $root"

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
