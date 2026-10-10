[CmdletBinding()]
param([switch]$KeepDatabase, [switch]$GatewayOnly, [switch]$ModelGatewayOnly, [switch]$CheckOnly, [string]$EnvFile = '')

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $repo '.runtime/enterprise/processes.json'
if (!$EnvFile) { $EnvFile = Join-Path $repo '.env' }
$mutex = [System.Threading.Mutex]::new($false, 'Local\MultiUserClawEnterpriseServices')
$locked = $false
if ($GatewayOnly -and $ModelGatewayOnly) { throw 'Choose either GatewayOnly or ModelGatewayOnly.' }
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'Another enterprise service helper is active; no process was stopped.' }
if (!$GatewayOnly -and !$ModelGatewayOnly) {
    & (Join-Path $PSScriptRoot 'stop-business-workers.ps1') -Workers product,hr,engineering -CheckOnly:$CheckOnly
}
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $names = if ($ModelGatewayOnly) { @('modelgateway') } elseif ($GatewayOnly) { @('gateway') } else { @('portal','modelgateway','management','frontend','gateway') }
    foreach ($name in $names) {
        $record = $state.$name
        if (!$record -or !$record.commandLine -or !$record.argumentLine -or !$record.directory) { continue }
        $expectedExecutable = switch ($name) {
            'gateway' { Join-Path $repo '.runtime/python/Scripts/python.exe' }
            { $_ -in 'portal','modelgateway' } { Join-Path $repo 'services/business/.runtime/main-acceptance-venv/Scripts/python.exe' }
            default { Join-Path $repo '.runtime/node/node.exe' }
        }
        if ($record.executable -ne $expectedExecutable -or !([IO.Path]::GetFullPath($record.directory).StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))) { continue }
        $proc = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
        if ($proc -and $proc.StartTime.ToUniversalTime().Ticks -eq [long]$record.startedTicks -and $proc.Path -eq $record.executable) {
            $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)"
            if (!$native -or $native.CommandLine -cne $record.commandLine -or !$native.CommandLine.TrimEnd().EndsWith(' ' + $record.argumentLine, [StringComparison]::Ordinal)) { continue }
            if ($CheckOnly) { Write-Host "${name}: matching owned PID $($proc.Id), stop skipped."; continue }
            # Windows venv python.exe launches the real interpreter as a child.
            # Verify the saved parent identity before stopping its owned tree.
            & taskkill.exe /PID $proc.Id /T /F | Out-Null
            if ($LASTEXITCODE) { throw "Could not stop the owned $name process tree." }
        }
    }
}
if ($CheckOnly) { Write-Host 'Owned process identities checked; no process/container was stopped.'; return }
if ($ModelGatewayOnly) {
    Write-Host 'Owned model gateway stopped; other services retained.'
    return
}
if ($GatewayOnly) {
    Write-Host 'Owned gateway stopped; frontend, database and user runtimes retained.'
    return
}

# Stop only this project's per-user runtimes, matched by their dedicated
# network and exact image. Keep every container and volume for the next start.
$ids = & docker ps --quiet --filter 'network=aicompany-claw-internal' --filter 'ancestor=aicompany-claw:20261008'
if ($LASTEXITCODE) { throw 'Could not inspect enterprise runtimes.' }
if ($ids) {
    & docker stop @ids
    if ($LASTEXITCODE) { throw 'Some enterprise runtimes could not be stopped.' }
}
if (!$KeepDatabase) {
    & docker compose --project-name aicompany-claw --env-file $EnvFile -f (Join-Path $repo 'docker-compose.enterprise.yml') stop postgres
    if ($LASTEXITCODE) { throw 'Enterprise PostgreSQL could not be stopped.' }
}
Write-Host 'Enterprise services stopped; containers and volumes retained.'
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
