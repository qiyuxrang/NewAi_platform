# Parse/check helpers without launching or stopping services or reading secrets.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
foreach ($name in 'start-enterprise.ps1','stop-enterprise.ps1','start-business-workers.ps1','stop-business-workers.ps1') {
    $tokens = $null; $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw "$name has PowerShell parse errors: $parseErrors" }
    Write-Host "${name}: parse PASS"
    $source = $ast.Extent.Text
    if ($source.Contains('Aicompany_platform') -or $source.Contains('(Get-Command node.exe)')) { throw "$name contains a legacy/system fallback." }
    if (!$source.Contains('commandLine') -or !$source.Contains('startedTicks')) { throw "$name lacks strict process identity checks." }
    if ($name.StartsWith('start-') -and !$source.Contains('-WindowStyle Hidden')) { throw "$name lacks hidden process launch." }
    if ($name -eq 'start-enterprise.ps1') {
        $definition = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'ConvertTo-ServiceArguments' }, $true)
        Invoke-Expression $definition.Extent.Text
        $encoded = ConvertTo-ServiceArguments @('C:\bundle with spaces\entry.py','portal','--repository','C:\bundle with spaces\services\business')
        if ($encoded -cne '"C:\bundle with spaces\entry.py" portal --repository "C:\bundle with spaces\services\business"') { throw 'Windows argument quoting self-check failed.' }
        $identityDefinition = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-OwnedProcess' }, $true)
        Invoke-Expression $identityDefinition.Extent.Text
        $mockStart = [DateTime]::UtcNow
        $mockCommand = '"C:\bundle\python.exe" -m uvicorn app.main:app'
        function Get-Process { param($Id, $ErrorAction) return [pscustomobject]@{ Id = 123; StartTime = $mockStart; Path = 'C:\bundle\python.exe' } }
        function Get-CimInstance { param($ClassName, $Filter) return [pscustomobject]@{ CommandLine = $mockCommand } }
        $mockRecord = @{ pid = 123; startedTicks = $mockStart.Ticks; executable = 'C:\bundle\python.exe'; directory = 'C:\bundle\platform'; argumentLine = '-m uvicorn app.main:app'; commandLine = $mockCommand }
        if (!(Get-OwnedProcess $mockRecord 'C:\bundle\python.exe' '-m uvicorn app.main:app' 'C:\bundle\platform')) { throw 'Exact owned identity was rejected.' }
        $mockCommand += ' '
        $mockRecord.commandLine = $mockCommand
        if (!(Get-OwnedProcess $mockRecord)) { throw 'Saved exact command with trailing space was rejected.' }
        $mockRecord.commandLine = $mockCommand.TrimEnd()
        if (Get-OwnedProcess $mockRecord) { throw 'Actual command equality was incorrectly widened.' }
        $mockRecord.commandLine = $mockCommand
        $mockCommand += ' --changed'
        if (Get-OwnedProcess $mockRecord) { throw 'Changed command was incorrectly adopted.' }
        $mockRecord.Remove('commandLine')
        if (Get-OwnedProcess $mockRecord) { throw 'Legacy record was incorrectly adopted.' }
    }
}
& (Join-Path $repo '.runtime/python/Scripts/python.exe') (Join-Path $PSScriptRoot 'check-bundled-paths.py')
if ($LASTEXITCODE) { throw 'Bundled Python path self-check failed.' }
Write-Host 'Bundled helpers PASS; no service state was changed.'
