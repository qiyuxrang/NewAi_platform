[CmdletBinding()]
param(
    [switch]$BuildImage,
    [switch]$BuildOnly,
    [switch]$BusinessOnly,
    [switch]$GatewayOnly,
    [switch]$ModelGatewayOnly,
    [switch]$CheckOnly,
    [string]$PythonPath = '',
    [string]$EnvFile = ''
)

$ErrorActionPreference = 'Stop'
if ($ModelGatewayOnly -and ($GatewayOnly -or $BuildOnly -or $BuildImage)) { throw 'ModelGatewayOnly cannot be combined with GatewayOnly or image build switches.' }
$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repo '.runtime/enterprise'
$compose = Join-Path $repo 'docker-compose.enterprise.yml'
if (!$EnvFile) { $EnvFile = Join-Path $repo '.env' }
if (!$PythonPath) { $PythonPath = Join-Path $repo '.runtime/python/Scripts/python.exe' }
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

# Read data, never evaluate .env as shell code; retain matching quoted values.
foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        if ($name -match '(_API_KEY|_API_BASE)$' -or $name -in 'JWT_SECRET','DEFAULT_MODEL','ROUTE_MODEL','ADMIN_USERNAME','ADMIN_PASSWORD','DEPLOY_VERSION') {
            if (!$name.StartsWith('PLATFORM_')) { [Environment]::SetEnvironmentVariable("PLATFORM_$name", $value, 'Process') }
        }
    }
}
if (!$env:PLATFORM_ADMIN_PASSWORD -and $env:PLATFORM_ADMIN_PASSWORD_FILE) {
    $passwordFile = $env:PLATFORM_ADMIN_PASSWORD_FILE
    if (![IO.Path]::IsPathRooted($passwordFile)) { $passwordFile = Join-Path $repo $passwordFile }
    $env:PLATFORM_ADMIN_PASSWORD = (Get-Content -LiteralPath $passwordFile -Raw -Encoding UTF8).Trim()
}

if ($env:PLATFORM_SHARED_OPENCLAW_ENABLED -ne 'false') { throw 'Enterprise deployment requires PLATFORM_SHARED_OPENCLAW_ENABLED=false.' }
if ($env:PLATFORM_CONTAINER_NETWORK -ne 'aicompany-claw-internal') { throw 'Enterprise deployment requires its isolated container network.' }
if ($env:PLATFORM_OPENCLAW_IMAGE -ne 'aicompany-claw:20261008') { throw 'Set PLATFORM_OPENCLAW_IMAGE=aicompany-claw:20261008.' }
foreach ($name in 'POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_DB','PLATFORM_JWT_SECRET','PLATFORM_ADMIN_PASSWORD') {
    if (![Environment]::GetEnvironmentVariable($name, 'Process')) { throw "Missing required setting: $name" }
}
if ($env:POSTGRES_PASSWORD.Length -lt 16 -or $env:PLATFORM_ADMIN_PASSWORD.Length -lt 12 -or $env:PLATFORM_JWT_SECRET.Length -lt 32) {
    throw 'Use PostgreSQL passwords of at least 16 characters, admin passwords of at least 12, and JWT secrets of at least 32.'
}

& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE) { throw 'Docker Desktop is unavailable.' }
$composeArgs = @('compose','--project-name','aicompany-claw','--env-file',$EnvFile,'-f',$compose)
& docker @composeArgs config --quiet
if ($LASTEXITCODE) { throw 'Enterprise Compose configuration is invalid.' }
if ($BuildImage) {
    foreach ($service in 'native-core-build','runtime-image') {
        & docker @composeArgs --profile build build $service
        if ($LASTEXITCODE) { throw "Image build failed: $service" }
    }
}
if ($BuildOnly) { return }
if (!$BusinessOnly -and !$ModelGatewayOnly) {
    & docker image inspect aicompany-claw:20261008 --format '{{.Id}}' | Out-Null
    if ($LASTEXITCODE) { throw 'Runtime image is absent; run this script with -BuildImage first.' }
}

$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$vite = Join-Path $repo 'frontend/node_modules/vite/bin/vite.js'
$node = Join-Path $repo '.runtime/node/node.exe'
$business = Join-Path $repo 'services/business'
$businessPython = Join-Path $business '.runtime/main-acceptance-venv/Scripts/python.exe'
$businessRunner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run-business-service.py')).Path
$next = Join-Path $repo 'manage_front/node_modules/next/dist/bin/next'
if (!$GatewayOnly) {
    $node = (Resolve-Path -LiteralPath $node).Path
    $business = (Resolve-Path -LiteralPath $business).Path
    $businessPython = (Resolve-Path -LiteralPath $businessPython).Path
    if (!(Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies are absent; run npm ci in frontend first.' }
    foreach ($required in @($next, (Join-Path $repo 'manage_front/.next/BUILD_ID'), (Join-Path $repo 'frontend/dist/index.html'),
            (Join-Path $business '.runtime/local.env'), (Join-Path $business '.runtime/model-gateway.env'))) {
        if (!(Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required bundled dependency/build/config is absent: $required" }
    }
}
$stateFile = Join-Path $runtime 'processes.json'
$state = @{}
if (Test-Path -LiteralPath $stateFile) {
    $old = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    foreach ($property in $old.PSObject.Properties) { $state[$property.Name] = $property.Value }
}

function ConvertTo-ServiceArguments([string[]]$values) {
    return (($values | ForEach-Object {
        if ($_ -ne '' -and $_ -notmatch '[\s"]') { $_ } else {
            '"' + [regex]::Replace([regex]::Replace($_, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
        }
    }) -join ' ')
}

function Get-OwnedProcess($record, [string]$executable = '', [string]$argumentLine = '', [string]$directory = '') {
    if (!$record -or !$record.commandLine -or !$record.argumentLine -or !$record.directory) { return $null }
    if ($executable -and ($record.executable -ne $executable -or $record.argumentLine -cne $argumentLine -or $record.directory -ne $directory)) { return $null }
    $proc = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($proc -and $proc.StartTime.ToUniversalTime().Ticks -eq [long]$record.startedTicks -and $proc.Path -eq $record.executable) {
        $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)"
        if ($native -and $native.CommandLine -ceq $record.commandLine -and $native.CommandLine.TrimEnd().EndsWith(' ' + $record.argumentLine, [StringComparison]::Ordinal)) { return $proc }
    }
    return $null
}

function Wait-Url([string]$url, [int]$seconds = 60) {
    $deadline = (Get-Date).AddSeconds($seconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Service did not become healthy: $url. See logs in $runtime"
}

function Start-OwnedService([string]$name, [int]$port, [string]$executable, [string[]]$arguments, [string]$directory) {
    $argumentLine = ConvertTo-ServiceArguments $arguments
    $existing = Get-OwnedProcess $state[$name] $executable $argumentLine $directory
    if ($existing) { return }
    $duplicates = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='node.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.TrimEnd().EndsWith(' ' + $argumentLine, [StringComparison]::Ordinal) })
    if ($duplicates.Count) { throw "$name has an unowned matching command; no duplicate was started." }
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is occupied by an unowned process; it was left running." }
    $proc = Start-Process -FilePath $executable -ArgumentList $argumentLine -WorkingDirectory $directory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtime "$name.stdout.log") -RedirectStandardError (Join-Path $runtime "$name.stderr.log")
    $startedTicks = $proc.StartTime.ToUniversalTime().Ticks
    $native = $null
    try {
        $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)"
        if (!$native -or !$native.CommandLine -or !$native.CommandLine.TrimEnd().EndsWith(' ' + $argumentLine, [StringComparison]::Ordinal)) { throw "$name exited or command identity could not be verified; see its private log." }
        $state[$name] = @{ pid = $proc.Id; startedTicks = $startedTicks; executable = $executable;
                           argumentLine = $argumentLine; commandLine = $native.CommandLine; directory = $directory }
        $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8
    } catch {
        # This is only the process just launched here. Failure evidence is never
        # an ownership record; recheck its PID/time/exe/exact actual command.
        if (!$native -or !$native.CommandLine) { $native = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue }
        $failure = @{ pid = $proc.Id; startedTicks = $startedTicks; executable = $executable;
                      commandLine = if ($native) { $native.CommandLine } else { $null }; argumentLine = $argumentLine }
        $failure | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime "failed-launch-$name.json") -Encoding UTF8
        $current = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
        $currentNative = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue
        if ($current -and $failure.commandLine -and $current.Path -eq $executable -and $current.StartTime.ToUniversalTime().Ticks -eq $startedTicks -and $currentNative -and $currentNative.CommandLine -ceq $failure.commandLine) {
            & taskkill.exe /PID $current.Id /T /F | Out-Null
        }
        [void]$state.Remove($name)
        throw
    }
}

if (!$GatewayOnly) {
    $env:PYTHONIOENCODING = 'utf-8'
    $pathOutput = & $businessPython $businessRunner paths-check --repository $business
    if ($LASTEXITCODE) { throw 'Bundled business path validation failed.' }
    $bundledPaths = ($pathOutput -join "`n") | ConvertFrom-Json
    foreach ($pathKey in 'PORTAL_ENGINEERING_PYTHON','PORTAL_ENGINEERING_COST_CLI','PORTAL_PRODUCT_PARSER_PYTHON','PORTAL_PRODUCT_DOCUMENT_PYTHON') {
        if (!(Test-Path -LiteralPath $bundledPaths.$pathKey -PathType Leaf)) { throw "Required bundled business runtime/tool is absent: $pathKey" }
    }
    if (!(Test-Path -LiteralPath $bundledPaths.engineering_data_library -PathType Container)) { throw 'Bundled engineering data/library is absent.' }
}
if ($CheckOnly) {
    if (!$GatewayOnly) { $pathOutput | Write-Output }
    Write-Host 'Bundled entry preflight passed; no service was started.'
    return
}
$mutex = [System.Threading.Mutex]::new($false, 'Local\MultiUserClawEnterpriseServices')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'Another enterprise service helper is active; no duplicate was started.' }
if ($ModelGatewayOnly) {
    Start-OwnedService 'modelgateway' 18411 $businessPython @($businessRunner,'gateway','--repository',$business) $business
    Wait-Url 'http://127.0.0.1:18411/health'
    Write-Host 'Owned model gateway is healthy; other services retained.'
    return
}
& docker @composeArgs up --detach --wait postgres
if ($LASTEXITCODE) { throw 'Enterprise PostgreSQL did not become healthy.' }
if (!$GatewayOnly) {
    & (Join-Path $PSScriptRoot 'start-search.ps1') -EnvFile $EnvFile
    Start-OwnedService 'modelgateway' 18411 $businessPython @($businessRunner,'gateway','--repository',$business) $business
    Wait-Url 'http://127.0.0.1:18411/health'
    Start-OwnedService 'portal' 8100 $businessPython @($businessRunner,'portal','--repository',$business) $business
    Wait-Url 'http://127.0.0.1:8100/health/'
    & (Join-Path $PSScriptRoot 'start-business-workers.ps1') -Workers product,hr,engineering,baichuan,tender -BusinessRepository $business
    $businessWorkers = @('product','hr','engineering')
    $workerSnapshot = Get-Content -LiteralPath (Join-Path $runtime 'legacy-worker-preflight.json') -Raw | ConvertFrom-Json
    if ($workerSnapshot.baichuan.enabled) { $businessWorkers += 'baichuan' }
    if ($workerSnapshot.tender.enabled -and ($workerSnapshot.tender.manual_refresh_enabled -or $workerSnapshot.tender.schedule_enabled)) { $businessWorkers += 'tender' }
}
Start-OwnedService 'gateway' 8080 $PythonPath @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8080','--no-access-log','--log-level','warning') (Join-Path $repo 'platform')
Wait-Url 'http://127.0.0.1:8080/api/ping'
if ($GatewayOnly) { Write-Host 'Owned enterprise gateway is healthy.'; return }
Start-OwnedService 'frontend' 3080 $node @($vite,'preview','--host','0.0.0.0','--port','3080','--strictPort') (Join-Path $repo 'frontend')
Wait-Url 'http://127.0.0.1:3080/'
# Keep the original management application separate from the employee workspace.
& {
    $env:API_URL = 'http://127.0.0.1:8080'
    if (!(Test-Path -LiteralPath (Join-Path $repo 'manage_front/.next/BUILD_ID'))) { throw 'Management build is absent; run npm run build in manage_front first.' }
    Start-OwnedService 'management' 3081 $node @($next,'start','--hostname','127.0.0.1','--port','3081') (Join-Path $repo 'manage_front')
    Wait-Url 'http://127.0.0.1:3081/login'
}
foreach ($worker in $businessWorkers) {
    $workerFile = Join-Path $runtime "legacy-worker-$worker-process.json"
    $workerRecord = Get-Content -LiteralPath $workerFile -Raw | ConvertFrom-Json
    $workerArguments = '"' + $businessRunner + '" ' + "$worker-worker" + ' --repository "' + $business + '"'
    $workerProcess = Get-Process -Id $workerRecord.pid -ErrorAction SilentlyContinue
    $workerNative = if ($workerProcess) { Get-CimInstance Win32_Process -Filter "ProcessId=$($workerProcess.Id)" } else { $null }
    if ($workerRecord.service -ne "$worker-worker" -or $workerRecord.executable -ne $businessPython -or $workerRecord.repository -ne $business -or $workerRecord.argumentLine -cne $workerArguments -or
        !$workerProcess -or $workerProcess.Path -ne $workerRecord.executable -or $workerProcess.StartTime.ToUniversalTime().Ticks -ne [long]$workerRecord.startedTicks -or !$workerNative -or $workerNative.CommandLine -cne $workerRecord.commandLine) {
        throw "$worker worker exited or changed identity before final health acceptance."
    }
}
@{ checkedAt = (Get-Date).ToString('o'); portal = 'http://127.0.0.1:8100/health/'; modelGateway = 'http://127.0.0.1:18411/health'; gateway = 'http://127.0.0.1:8080/api/ping'; frontend = 'http://127.0.0.1:3080/'; management = 'http://127.0.0.1:3081/login'; workers = $businessWorkers; image = 'aicompany-claw:20261008'; runtimeImageChecked = !$BusinessOnly } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'health.json') -Encoding UTF8
Write-Host "Portal, model gateway, $($businessWorkers.Count) workers, enterprise gateway and both frontends are healthy: http://127.0.0.1:3080/"
if ($BusinessOnly) { Write-Host 'Agent runtime image has not passed acceptance; only the business entry is verified.' }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
