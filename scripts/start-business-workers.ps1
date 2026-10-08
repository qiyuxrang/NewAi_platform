[CmdletBinding()]
param(
    [ValidateSet('product', 'hr', 'engineering')][string[]]$Workers = @(),
    [string]$BusinessRepository = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (!$BusinessRepository) { $BusinessRepository = Join-Path $repo 'services/business' }
$BusinessRepository = (Resolve-Path -LiteralPath $BusinessRepository).Path
$python = (Resolve-Path -LiteralPath (Join-Path $BusinessRepository '.runtime/main-acceptance-venv/Scripts/python.exe')).Path
$runner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run-business-service.py')).Path
$runtime = (Resolve-Path -LiteralPath (Join-Path $repo '.runtime/enterprise')).Path
if (!$CheckOnly -and !$Workers.Count) { throw 'Specify -Workers product,hr,engineering (or a subset). No worker was started.' }
if (!$Workers.Count) { $Workers = @('product', 'hr', 'engineering') }
$Workers = @($Workers | Select-Object -Unique)

function Get-BusinessOwnedProcess($record, [string]$service) {
    if (!$record -or !$record.commandLine -or $record.argumentLine -cne (Get-WorkerArguments $service) -or $record.service -ne $service -or $record.executable -ne $python -or $record.repository -ne $BusinessRepository) { return $null }
    $workerProcess = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (!$workerProcess -or $workerProcess.Path -ne $record.executable -or $workerProcess.StartTime.ToUniversalTime().Ticks -ne [long]$record.startedTicks) { return $null }
    $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($workerProcess.Id)"
    if (!$native -or $native.CommandLine -cne $record.commandLine -or !$native.CommandLine.TrimEnd().EndsWith(' ' + $record.argumentLine, [StringComparison]::Ordinal)) { return $null }
    return $workerProcess
}

function Get-WorkerArguments([string]$service) {
    return '"' + $runner + '" ' + $service + ' --repository "' + $BusinessRepository + '"'
}

# A cross-process lock prevents two helper invocations from creating duplicates.
$mutex = [System.Threading.Mutex]::new($false, 'Local\MultiUserClawBusinessWorkers')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'Another business worker helper is active; no process was changed.' }
    $env:PYTHONIOENCODING = 'utf-8'
    $snapshotFile = Join-Path $runtime 'legacy-worker-preflight.json'
    $snapshotOutput = & $python $runner workers-check --repository $BusinessRepository --output $snapshotFile
    if ($LASTEXITCODE) { throw 'Read-only worker preflight failed; no worker was started.' }
    $snapshot = ($snapshotOutput -join "`n") | ConvertFrom-Json
    if (!$snapshot.read_only -or !$snapshot.model_gateway_loopback_18411) { throw 'Business model gateway must be loopback:18411.' }
    if ('product' -in $Workers -and !$snapshot.product.enabled) { throw 'Business PRODUCT_P1_ENABLED is false.' }
    if ('engineering' -in $Workers -and $snapshot.engineering.runtime_status -ne 'ready') { throw 'Bundled engineering runtime is not ready.' }
    $workerProcesses = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")
    $checks = @()
    foreach ($worker in $Workers) {
        $service = "$worker-worker"
        $recordFile = Join-Path $runtime "legacy-worker-$worker-process.json"
        $record = if (Test-Path -LiteralPath $recordFile) { Get-Content -LiteralPath $recordFile -Raw | ConvertFrom-Json } else { $null }
        $owned = Get-BusinessOwnedProcess $record $service
        $command = "run_${worker}_worker"
        $matching = @($workerProcesses | Where-Object { $_.CommandLine -and ($_.CommandLine -match ('(?i)(?:^|\s)' + $command + '(?:\s|$)') -or
            $_.CommandLine -match ('(?i)run-business-service\.py.*\s' + [regex]::Escape($service) + '(?:\s|$)')) })
        # Venv python's real interpreter is a child of the recorded launcher.
        # Conditional output unwraps a single PID to UInt32; keep an array even
        # when only the launcher exists, before appending interpreter children.
        [uint32[]]$ownedTree = @()
        if ($owned) { $ownedTree = @($owned.Id) }
        do {
            $children = @($workerProcesses | Where-Object { $_.ParentProcessId -in $ownedTree -and $_.ProcessId -notin $ownedTree })
            foreach ($child in $children) { $ownedTree += $child.ProcessId }
        } while ($children.Count)
        $external = @($matching | Where-Object { $_.ProcessId -notin $ownedTree })
        $checks += @{ service = $service; ownedPid = if ($owned) { $owned.Id } else { $null }; externalCount = $external.Count }
    }
    @{ checkedAt = (Get-Date).ToUniversalTime().ToString('o'); checkOnly = [bool]$CheckOnly; workers = $checks } |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runtime 'legacy-worker-process-check.json') -Encoding UTF8
    if (@($checks | Where-Object { $_.externalCount -gt 0 }).Count) { throw 'An unowned worker was found; it was left running and no duplicate was started.' }
    if ($CheckOnly) {
        $checks | ConvertTo-Json -Depth 4
        return
    }
    foreach ($check in $checks) {
        if ($check.ownedPid) { Write-Host "$($check.service): already running as owned PID $($check.ownedPid)"; continue }
        $worker = $check.service.Replace('-worker', '')
        $argumentLine = Get-WorkerArguments $check.service
        $started = Start-Process -FilePath $python -ArgumentList $argumentLine -WorkingDirectory $BusinessRepository -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $runtime "legacy-worker-$worker.stdout.log") `
            -RedirectStandardError (Join-Path $runtime "legacy-worker-$worker.stderr.log")
        $startedTicks = $started.StartTime.ToUniversalTime().Ticks
        $native = $null
        try {
            $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($started.Id)"
            if (!$native -or !$native.CommandLine -or !$native.CommandLine.TrimEnd().EndsWith(' ' + $argumentLine, [StringComparison]::Ordinal)) { throw "$($check.service) command identity could not be verified." }
            $record = @{ service = $check.service; pid = $started.Id; startedTicks = $startedTicks;
                         executable = $python; repository = $BusinessRepository; argumentLine = $argumentLine; commandLine = $native.CommandLine }
            $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime "legacy-worker-$worker-process.json") -Encoding UTF8
        } catch {
            if (!$native -or !$native.CommandLine) { $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($started.Id)" -ErrorAction SilentlyContinue }
            $failure = @{ pid = $started.Id; startedTicks = $startedTicks; executable = $python;
                          commandLine = if ($native) { $native.CommandLine } else { $null }; argumentLine = $argumentLine }
            $failure | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime "failed-launch-$worker-worker.json") -Encoding UTF8
            $current = Get-Process -Id $started.Id -ErrorAction SilentlyContinue
            $currentNative = Get-CimInstance Win32_Process -Filter "ProcessId=$($started.Id)" -ErrorAction SilentlyContinue
            if ($current -and $failure.commandLine -and $current.Path -eq $python -and $current.StartTime.ToUniversalTime().Ticks -eq $startedTicks -and $currentNative -and $currentNative.CommandLine -ceq $failure.commandLine) {
                & taskkill.exe /PID $current.Id /T /F | Out-Null
            }
            throw
        }
        Start-Sleep -Seconds 2
        if (!(Get-BusinessOwnedProcess $record $check.service)) { throw "$($check.service) exited during startup; check its private stderr log. Existing services were left running." }
        Write-Host "$($check.service): started owned PID $($started.Id)"
    }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
