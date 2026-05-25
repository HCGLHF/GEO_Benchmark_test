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

if ($null -eq $QueriesPerModel) {
  if ($RunMode -eq "test") {
    $QueriesPerModel = 2
  } elseif ($RunMode -eq "standard") {
    $QueriesPerModel = 200
  } else {
    $QueriesPerModel = 50
  }
}

$modelList = @(
  "openai/gpt-4.1-mini",
  "google/gemini-3.5-flash",
  "perplexity/sonar-pro",
  "deepseek/deepseek-v4-flash",
  "qwen/qwen3.7-max",
  "x-ai/grok-build-0.1"
)

if ($IncludeDoubao) {
  $modelList += "bytedance-seed/seed-2.0-pro"
}

if ($SelectedModels.Count -gt 0) {
  $parsedModels = @()
  foreach ($entry in $SelectedModels) {
    $parsedModels += @($entry -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  }
  $modelList = @($parsedModels | Select-Object -Unique)
}

if ($modelList.Count -eq 0) {
  throw "No models selected. Pass -Models with at least one model id or use the defaults."
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
  $allRows = @(Import-Csv $seedPath)
  $rows = @($allRows | Where-Object { $_.scenario_model -eq $Model })
  if ($rows.Count -eq 0 -and $allRows.Count -gt 0) {
    $fallbackGroup = @($allRows | Group-Object -Property scenario_model | Sort-Object Count -Descending | Select-Object -First 1)
    if ($fallbackGroup.Count -gt 0) {
      $rows = @($fallbackGroup[0].Group)
    }
  }
  if ($Limit -gt 0) {
    $rows = @($rows | Select-Object -First $Limit)
  }
  if ($rows.Count -eq 0) {
    throw "No seeded queries found for model $Model in $SeedRunDir"
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

function Write-PipelineInit {
  param(
    [string]$RunRootPath,
    [array]$ModelList
  )
  $metadataJson = @{
    run_mode = $RunMode
    queries_per_model = $QueriesPerModel
  } | ConvertTo-Json -Compress
  $metadataJson = $metadataJson.Replace('"', '\"')
  $stateArgs = @(
    "scripts\pipeline_state.py",
    "init",
    "--run-root", $RunRootPath,
    "--run-type", "full_api_parallel",
    "--stage", "crawl",
    "--stage", "clean",
    "--stage", "chunk",
    "--stage", "index",
    "--stage", "AWS sync",
    "--stage", "scenario_generation",
    "--stage", "rerank",
    "--stage", "answer",
    "--stage", "merge",
    "--stage", "report",
    "--metadata-json", $metadataJson
  )
  foreach ($model in $ModelList) {
    $stateArgs += @("--model", $model)
  }
  & python @stateArgs | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to initialize pipeline manifest for $RunRootPath"
  }
}

function Write-PipelineEvent {
  param(
    [string]$RunRootPath,
    [string]$Stage,
    [string]$Status,
    [string]$Message = "",
    [string]$Model = "",
    [string]$DetailsJson = "{}"
  )
  $eventArgs = @(
    "scripts\pipeline_state.py",
    "append",
    "--run-root", $RunRootPath,
    "--stage", $Stage,
    "--status", $Status,
    "--message", $Message,
    "--details-json", $DetailsJson
  )
  if ($Model) {
    $eventArgs += @("--model", $Model)
  }
  & python @eventArgs | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to write pipeline event for $Stage/$Status under $RunRootPath"
  }
}

function Write-OpsEvent {
  param(
    [string]$RunRootPath,
    [string]$Level,
    [string]$EventType,
    [string]$Stage = "",
    [string]$Model = "",
    [string]$Message = "",
    [string]$DetailsJson = "{}"
  )
  $opsArgs = @(
    "scripts\ops_logs.py",
    "record",
    "--run-root", $RunRootPath,
    "--level", $Level,
    "--event-type", $EventType,
    "--message", $Message,
    "--details-json", $DetailsJson,
    "--source", "scripts/run_full_api_parallel_with_watch.ps1"
  )
  if ($Stage) {
    $opsArgs += @("--stage", $Stage)
  }
  if ($Model) {
    $opsArgs += @("--model", $Model)
  }
  & python @opsArgs | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not write ops event $EventType for $RunRootPath"
  }
}

function Write-OpsSummary {
  param([string]$RunRootPath)
  & python "scripts\ops_logs.py" "doctor" "--run-root" $RunRootPath | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not write ops summary for $RunRootPath"
  }
}

function Test-WorkerExitCodeReady {
  param([string]$ExitCodePath)
  if (-not (Test-Path $ExitCodePath)) {
    return $false
  }
  $rawExitCode = Get-Content $ExitCodePath -TotalCount 1
  return -not [string]::IsNullOrWhiteSpace($rawExitCode)
}

function Read-WorkerExitCode {
  param(
    [string]$ExitCodePath,
    [object]$Process,
    [int]$TimeoutMilliseconds = 5000
  )
  $deadline = (Get-Date).AddMilliseconds($TimeoutMilliseconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-WorkerExitCodeReady -ExitCodePath $ExitCodePath) {
      $rawExitCode = Get-Content $ExitCodePath -TotalCount 1
      return [int]$rawExitCode
    }
    Start-Sleep -Milliseconds 100
  }
  if ($null -ne $Process -and $null -ne $Process.ExitCode) {
    return [int]$Process.ExitCode
  }
  return 1
}

if ($RunStamp) {
  $stamp = $RunStamp
} else {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
}
$root = Join-Path $RunRoot $stamp
$cacheRoot = Join-Path $root "cache"
$mergedDir = Join-Path $root "merged"
if (-not $ProgressHtmlPath) {
  $ProgressHtmlPath = Join-Path $root "progress.html"
}

$runDirs = @()
$workers = @()

foreach ($model in $modelList) {
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
  Write-Host "Selected models: $($modelList -join ', ')"
  Write-Host "Progress HTML: $ProgressHtmlPath"
  Write-Host "Pipeline manifest: $(Join-Path $root 'run_manifest.json')"
  Write-Host "Pipeline state: $(Join-Path $root 'pipeline_state.jsonl')"
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
Write-PipelineInit -RunRootPath $root -ModelList $modelList
Write-OpsEvent -RunRootPath $root -Level "info" -EventType "run_started" -Message "Full API parallel run started." -DetailsJson "{`"run_mode`":`"$RunMode`",`"queries_per_model`":$QueriesPerModel}"
Write-PipelineEvent -RunRootPath $root -Stage "scenario_generation" -Status "running" -Message "Parallel model workers are starting."

Write-Host "Starting full API single-model runs under $root"
Write-Host "Run mode: $RunMode"
Write-Host "Queries per model: $QueriesPerModel"
Write-Host "Selected models: $($modelList -join ', ')"
Write-Host "Monitor interval: $MonitorIntervalSeconds seconds"
Write-Host "Progress HTML: $ProgressHtmlPath"
Write-Host "Pipeline manifest: $(Join-Path $root 'run_manifest.json')"
Write-Host "Pipeline state: $(Join-Path $root 'pipeline_state.jsonl')"
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
python "scripts\pipeline_state.py" "append" "--run-root" "$root" "--stage" "rerank" "--status" "running" "--model" "$($worker.Model)" "--message" "Worker started."
$($worker.Command) *>&1 | Tee-Object -FilePath "$logPath"
`$exitCode = `$LASTEXITCODE
if (`$exitCode -eq 0) {
  python "scripts\pipeline_state.py" "append" "--run-root" "$root" "--stage" "answer" "--status" "completed" "--model" "$($worker.Model)" "--message" "Worker completed."
} else {
  python "scripts\pipeline_state.py" "append" "--run-root" "$root" "--stage" "answer" "--status" "failed" "--model" "$($worker.Model)" "--message" "Worker failed." "--details-json" "{`"exit_code`":`$exitCode}"
  python "scripts\ops_logs.py" "record" "--run-root" "$root" "--level" "error" "--event-type" "worker_failed" "--stage" "answer" "--model" "$($worker.Model)" "--message" "Worker failed." "--details-json" "{`"exit_code`":`$exitCode}" "--source" "scripts/run_full_api_parallel_with_watch.ps1" | Out-Null
  if (`$LASTEXITCODE -ne 0) {
    Write-Warning "Could not write ops event worker_failed for $root"
  }
}
  Set-Content -Path "$exitCodePath" -Value `$exitCode
exit `$exitCode
"@
  Write-Host "Launching $($worker.Model) -> $($worker.RunDir)"
  $process = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $workerCommand) -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
  $worker.Process = $process
}

if ($SeedQueriesRunDir) {
  Write-PipelineEvent -RunRootPath $root -Stage "scenario_generation" -Status "completed" -Message "Seeded queries copied; scenario generation skipped."
}

Write-Host ""
Write-Host "Monitoring active runs. Press Ctrl+C to stop this monitor; child model processes will continue."
Render-ProgressHtml -RunDirs $runDirs -OutputPath $ProgressHtmlPath

while (($workers | Where-Object { -not (Test-WorkerExitCodeReady -ExitCodePath (Join-Path $_.RunDir "worker_exit_code.txt")) }).Count -gt 0) {
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
$exitCodes = @{}
foreach ($worker in $workers) {
  $exitCodePath = Join-Path $worker.RunDir "worker_exit_code.txt"
  $exitCode = Read-WorkerExitCode -ExitCodePath $exitCodePath -Process $worker.Process
  $exitCodes[$worker.SafeName] = "$exitCode"
  Write-Host "$($worker.Model): exit $exitCode"
}
$exitCodeJsonPath = Join-Path $root "worker_exit_codes.json"
$exitCodes | ConvertTo-Json -Compress | Set-Content -Path $exitCodeJsonPath -Encoding UTF8

$statusArgs = @(
  "scripts\full_api_run_status.py"
)
foreach ($runDir in $runDirs) {
  $statusArgs += @("--run-dir", $runDir)
}
$statusArgs += @("--exit-code-file", $exitCodeJsonPath)
$runStatusRaw = & python @statusArgs
if ($LASTEXITCODE -ne 0) {
  Write-PipelineEvent -RunRootPath $root -Stage "answer" -Status "failed" -Message "Could not classify model worker outputs."
  Write-Error "Could not classify model worker outputs. Inspect worker.log files under $root."
  exit 1
}
$runStatus = $runStatusRaw | ConvertFrom-Json

if ([int]$runStatus.fatal_count -gt 0) {
  $fatalMessages = @($runStatus.fatals | ForEach-Object { $_.message } | Where-Object { $_ })
  Write-PipelineEvent -RunRootPath $root -Stage "answer" -Status "failed" -Message "One or more model workers produced incomplete outputs."
  Write-OpsEvent -RunRootPath $root -Level "error" -EventType "stage_failed" -Stage "answer" -Message "One or more model workers produced incomplete outputs."
  Write-OpsSummary -RunRootPath $root
  if ($fatalMessages.Count -gt 0) {
    $fatalMessages | ForEach-Object { Write-Error $_ }
  }
  Write-Error "One or more model runs are incomplete. Skipping merge. Inspect worker.log files under $root."
  exit 1
}

if ([int]$runStatus.warning_count -gt 0) {
  $warningMessages = @($runStatus.warnings | ForEach-Object { $_.message } | Where-Object { $_ })
  Write-PipelineEvent -RunRootPath $root -Stage "answer" -Status "complete_with_model_warnings" -Message "Model workers completed with API warnings."
  Write-OpsEvent -RunRootPath $root -Level "warning" -EventType "stage_completed" -Stage "answer" -Message "Model workers completed with API warnings."
  foreach ($warning in $warningMessages) {
    Write-Warning $warning
  }
} else {
  Write-PipelineEvent -RunRootPath $root -Stage "answer" -Status "completed" -Message "All model workers completed."
  Write-OpsEvent -RunRootPath $root -Level "info" -EventType "stage_completed" -Stage "answer" -Message "All model workers completed."
}

if ($SkipMerge) {
  Write-PipelineEvent -RunRootPath $root -Stage "merge" -Status "skipped" -Message "SkipMerge set; merge not executed."
  Write-Host "SkipMerge set. Merge command:"
  Write-Host $mergeCommand
  Write-OpsEvent -RunRootPath $root -Level "info" -EventType "run_completed" -Stage "merge" -Message "Run completed without merge because SkipMerge was set."
  Write-OpsSummary -RunRootPath $root
  exit 0
}

Write-Host ""
Write-Host "Merging model runs..."
if ([int]$runStatus.warning_count -gt 0) {
  Write-PipelineEvent -RunRootPath $root -Stage "merge" -Status "running" -Message "Merging model workers with warnings."
} else {
  Write-PipelineEvent -RunRootPath $root -Stage "merge" -Status "running" -Message "Merging successful model workers."
}
Invoke-Expression $mergeCommand
Write-PipelineEvent -RunRootPath $root -Stage "merge" -Status "completed" -Message "Merged model workers."
Write-PipelineEvent -RunRootPath $root -Stage "report" -Status "completed" -Message "Merged report available."
Write-OpsEvent -RunRootPath $root -Level "info" -EventType "run_completed" -Stage "report" -Message "Merged report available."
Write-OpsSummary -RunRootPath $root
Write-Host ""
Write-Host "Merged report: $(Join-Path $mergedDir 'competitive_gap_report.md')"
