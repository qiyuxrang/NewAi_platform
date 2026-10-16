# Isolated synthetic-data verification; never reads the deployment .env.
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$pythonPath = Join-Path $repoPath 'services/business/.runtime/main-acceptance-venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Configured test Python is unavailable.' }
$runId = [Guid]::NewGuid().ToString('N')
$runtimePath = Join-Path $repoPath '.runtime'
$runnerPath = Join-Path $runtimePath "baichuan-evidence-$runId.py"
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
foreach ($databaseVariable in @('PORTAL_DB_NAME', 'PORTAL_DB_USER', 'PORTAL_DB_PASSWORD', 'PORTAL_DB_HOST', 'PORTAL_DB_PORT', 'DATABASE_URL', 'PGHOST', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGPORT', 'PGSERVICE', 'PGSERVICEFILE', 'PGPASSFILE')) {
    Remove-Item -LiteralPath "Env:$databaseVariable" -ErrorAction SilentlyContinue
}
$env:PORTAL_SECRET_KEY = 'baichuan-isolated-test-only-secret-key-20261016'
$env:PORTAL_DEBUG = '1'
$env:PORTAL_HTTPS = '0'
$env:PORTAL_SQLITE_PATH = Join-Path $runtimePath "baichuan-base-$runId.sqlite3"
$env:BAICHUAN_TEST_DB = Join-Path $runtimePath "baichuan-test-$runId.sqlite3"
$env:BAICHUAN_BACKEND_PATH = Join-Path $repoPath 'services/business/backend'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$testCode = @'
import os, sys
sys.stderr = sys.stdout
sys.path.insert(0, os.environ["BAICHUAN_BACKEND_PATH"])
os.chdir(os.environ["BAICHUAN_BACKEND_PATH"])
import django
from datetime import datetime, timezone
print("Python", sys.version)
print("Django", django.get_version())
print("UTC start", datetime.now(timezone.utc).isoformat())
print("Database: isolated file SQLite; synthetic users only; deployment .env is not loaded")
print("PORTAL_DEBUG=1; PORTAL_HTTPS=0; synthetic PORTAL_SECRET_KEY; real database variables removed")
print("PORTAL_SQLITE_PATH", os.environ["PORTAL_SQLITE_PATH"])
print("TEST database", os.environ["BAICHUAN_TEST_DB"])
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings
settings.DATABASES["default"]["TEST"] = {"NAME": os.environ["BAICHUAN_TEST_DB"]}
commands = {
    "tests": ["test", "portal.tests.test_baichuan", "portal.tests.test_baichuan_import", "--noinput", "--verbosity=2"],
    "migration": ["makemigrations", "portal", "--check", "--dry-run"],
    "check": ["check"],
}
command = commands[sys.argv[1]]
print("Django command: manage.py", " ".join(command))
from django.core.management import execute_from_command_line
execute_from_command_line(["manage.py", *command])
print("UTC end", datetime.now(timezone.utc).isoformat())
'@
[System.IO.File]::WriteAllText($runnerPath, $testCode, (New-Object System.Text.UTF8Encoding($false)))

function Invoke-BackendEvidence($mode, $logName, $append) {
    $logPath = Join-Path $PSScriptRoot $logName
    $header = "Reproduce: powershell -NoProfile -File doc/baichuan-sdd/evidence/backend-command.ps1`r`nPowerShell $($PSVersionTable.PSVersion)`r`nNative command: $pythonPath $runnerPath $mode"
    if ($append) { Add-Content -LiteralPath $logPath -Value $header -Encoding UTF8 }
    else { Set-Content -LiteralPath $logPath -Value $header -Encoding UTF8 }
    # PS5 turns native stderr into ErrorRecords. Keep it non-terminating and
    # inspect the process exit code; the Python runner also joins stderr/stdout.
    $ErrorActionPreference = 'Continue'
    & $pythonPath $runnerPath $mode 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8 -ErrorAction Stop
        Write-Output $line
    }
    $nativeExit = $LASTEXITCODE
    Add-Content -LiteralPath $logPath -Value "Native exit code: $nativeExit" -Encoding UTF8 -ErrorAction Stop
    if ($nativeExit -ne 0) { throw "Backend $mode failed with exit code $nativeExit" }
}

try {
    Invoke-BackendEvidence 'tests' 'backend-tests.txt' $false
    Invoke-BackendEvidence 'migration' 'backend-checks.txt' $false
    Invoke-BackendEvidence 'check' 'backend-checks.txt' $true
} finally {
    Remove-Item -LiteralPath $runnerPath -ErrorAction SilentlyContinue
}
