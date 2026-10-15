[CmdletBinding()]
param([string]$EnvFile = '')

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (!$EnvFile) { $EnvFile = Join-Path $repo '.env' }
$configDirectory = Join-Path $repo '.runtime/search'
$settingsFile = Join-Path $configDirectory 'settings.yml'
if (!(Test-Path -LiteralPath $settingsFile)) {
    New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
    $secret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $settings = @"
use_default_settings:
  engines:
    keep_only: [sogou, 360search]
server:
  secret_key: '$secret'
  limiter: false
  image_proxy: false
search:
  formats: [html, json]
outgoing:
  request_timeout: 5.0
  max_request_timeout: 6.0
engines:
  - name: sogou
    disabled: false
  - name: 360search
    disabled: false
    timeout: 5.0
"@
    [IO.File]::WriteAllText($settingsFile, $settings, [Text.UTF8Encoding]::new($false))
}
& docker compose --project-name aicompany-claw --env-file $EnvFile -f (Join-Path $repo 'docker-compose.enterprise.yml') up --detach searxng
if ($LASTEXITCODE) { throw 'Local search container failed to start.' }
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        if ((Invoke-WebRequest -Uri 'http://127.0.0.1:19881/healthz' -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200) {
            Write-Host 'Local public search is healthy on http://127.0.0.1:19881 (JSON /search API).'
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'Local search did not become healthy; inspect docker compose logs searxng.'
