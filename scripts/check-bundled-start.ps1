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
    if ($name.EndsWith('business-workers.ps1')) {
        if (!$source.Contains("'baichuan'") -or !$source.Contains("'tender'")) { throw "$name excludes a managed worker." }
        & {
            $python = 'C:\isolated\python.exe'; $runner = 'C:\isolated\run-business-service.py'; $BusinessRepository = 'C:\isolated\business'
            $identity = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-BusinessOwnedProcess' }, $true)
            $arguments = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-WorkerArguments' }, $true)
            if ($arguments) { Invoke-Expression $arguments.Extent.Text }
            Invoke-Expression $identity.Extent.Text
            $mockStart = [DateTime]::UtcNow
            $argumentLine = '"' + $runner + '" baichuan-worker --repository "' + $BusinessRepository + '"'
            $mockCommand = '"' + $python + '" ' + $argumentLine
            function Get-Process { param($Id, $ErrorAction) return [pscustomobject]@{ Id = 123; StartTime = $mockStart; Path = $python } }
            function Get-CimInstance { param($ClassName, $Filter) return [pscustomobject]@{ CommandLine = $mockCommand } }
            $record = @{ pid = 123; startedTicks = $mockStart.Ticks; executable = $python; repository = $BusinessRepository;
                service = 'baichuan-worker'; argumentLine = $argumentLine; commandLine = $mockCommand }
            if (!(Get-BusinessOwnedProcess $record 'baichuan-worker')) { throw "$name rejected owned Baichuan identity." }
            if (Get-BusinessOwnedProcess $record 'product-worker') { throw "$name adopted another worker identity." }
            $mockCommand += ' --changed'
            if (Get-BusinessOwnedProcess $record 'baichuan-worker') { throw "$name adopted a changed Baichuan command." }
        }
    } elseif (!$source.Contains('-Workers product,hr,engineering,baichuan,tender')) {
        throw "$name excludes a worker from enterprise worker management."
    }
    if ($name -eq 'start-business-workers.ps1') {
        $tenderSelection = $ast.Find({ param($node) $node -is [Management.Automation.Language.IfStatementAst] -and $node.Clauses[0].Item1.Extent.Text.StartsWith("'tender' -in `$Workers") }, $true)
        if (!$tenderSelection) { throw 'Missing tender feature selection.' }
        & {
            $Workers = @('product','tender')
            $snapshot = @{ tender = @{ enabled = $false; manual_refresh_enabled = $true; schedule_enabled = $true } }
            Invoke-Expression $tenderSelection.Extent.Text
            if (($Workers -join ',') -ne 'product') { throw 'Disabled tender worker was retained.' }
            $Workers += 'tender'
            $snapshot.tender.enabled = $true
            Invoke-Expression $tenderSelection.Extent.Text
            if (($Workers -join ',') -ne 'product,tender') { throw 'Enabled tender worker was skipped.' }
            $snapshot.tender.manual_refresh_enabled = $false
            $snapshot.tender.schedule_enabled = $false
            Invoke-Expression $tenderSelection.Extent.Text
            if (($Workers -join ',') -ne 'product') { throw 'Tender without queue triggers was retained.' }
        }
        $selection = $ast.Find({ param($node) $node -is [Management.Automation.Language.IfStatementAst] -and $node.Clauses[0].Item1.Extent.Text -eq "'baichuan' -in `$Workers" }, $true)
        if (!$selection) { throw 'Missing Baichuan feature selection.' }
        & {
            $Workers = @('product','hr','engineering','baichuan')
            $snapshot = @{ baichuan = @{ enabled = $false } }
            Invoke-Expression $selection.Extent.Text
            if (($Workers -join ',') -ne 'product,hr,engineering') { throw 'Disabled assistant changed the existing worker set.' }
            $Workers += 'baichuan'
            $snapshot.baichuan = @{ enabled = $true; scope_confirmed = $true; scope = 'isolated-check' }
            Invoke-Expression $selection.Extent.Text
            if (($Workers -join ',') -ne 'product,hr,engineering,baichuan') { throw 'Enabled assistant worker was skipped.' }
            $snapshot.baichuan.scope_confirmed = $false
            $rejected = $false
            try { Invoke-Expression $selection.Extent.Text } catch { $rejected = $true }
            if (!$rejected) { throw 'Unconfirmed Baichuan scope was accepted.' }
        }
    }
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
