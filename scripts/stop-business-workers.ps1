[CmdletBinding()]
param(
    [ValidateSet('product', 'hr', 'engineering', 'baichuan', 'tender')][string[]]$Workers = @(),
    [string]$BusinessRepository = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (!$BusinessRepository) { $BusinessRepository = Join-Path $repo 'services/business' }
$BusinessRepository = [IO.Path]::GetFullPath($BusinessRepository)
$python = Join-Path $BusinessRepository '.runtime/main-acceptance-venv/Scripts/python.exe'
$runner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run-business-service.py')).Path
$runtime = (Resolve-Path -LiteralPath (Join-Path $repo '.runtime/enterprise')).Path
if (!$CheckOnly -and !$Workers.Count) { throw 'Specify -Workers product,hr,engineering,baichuan,tender (or a subset). No process was stopped.' }
if (!$Workers.Count) { $Workers = @('product', 'hr', 'engineering', 'baichuan', 'tender') }

function Get-BusinessOwnedProcess($record, [string]$service) {
    $argumentLine = '"' + $runner + '" ' + $service + ' --repository "' + $BusinessRepository + '"'
    if (!$record -or !$record.commandLine -or $record.argumentLine -cne $argumentLine -or $record.service -ne $service -or $record.executable -ne $python -or $record.repository -ne $BusinessRepository) { return $null }
    $workerProcess = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (!$workerProcess -or $workerProcess.Path -ne $record.executable -or $workerProcess.StartTime.ToUniversalTime().Ticks -ne [long]$record.startedTicks) { return $null }
    $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($workerProcess.Id)"
    if (!$native -or $native.CommandLine -cne $record.commandLine -or !$native.CommandLine.TrimEnd().EndsWith(' ' + $record.argumentLine, [StringComparison]::Ordinal)) { return $null }
    return $workerProcess
}

$mutex = [System.Threading.Mutex]::new($false, 'Local\MultiUserClawBusinessWorkers')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'Another business worker helper is active; no process was changed.' }
    foreach ($worker in ($Workers | Select-Object -Unique)) {
        $service = "$worker-worker"
        $recordFile = Join-Path $runtime "legacy-worker-$worker-process.json"
        $record = if (Test-Path -LiteralPath $recordFile) { Get-Content -LiteralPath $recordFile -Raw | ConvertFrom-Json } else { $null }
        $owned = Get-BusinessOwnedProcess $record $service
        if (!$owned) { Write-Host "${service}: no matching owned process; every other process was retained."; continue }
        if ($CheckOnly) { Write-Host "${service}: matching owned PID $($owned.Id), stop skipped."; continue }
        # Check PID, exact interpreter, UTC ticks and command identity immediately
        # before terminating only this recorded launcher's interpreter/CLI tree.
        $current = Get-BusinessOwnedProcess $record $service
        if (!$current) { throw "$service process identity changed; no process was stopped." }
        & taskkill.exe /PID $current.Id /T /F | Out-Null
        if ($LASTEXITCODE) { throw "Could not stop the owned $service process tree." }
        Write-Host "${service}: stopped owned PID $($current.Id)"
    }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
