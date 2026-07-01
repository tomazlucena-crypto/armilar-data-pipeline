param(
    [Parameter(Mandatory=$true)]
    [string]$RepoPath
)

$ErrorActionPreference = "Stop"
$toolRoot = $PSScriptRoot
$repo = (Resolve-Path $RepoPath).Path

& (Join-Path $toolRoot "apply_v087_overlay.ps1") -RepoPath $repo

Push-Location $repo
try {
    Write-Host "A executar os testes dedicados da v0.8.7..."
    py -m unittest tests.test_eurostat_vertical_v087 -v
    if ($LASTEXITCODE -ne 0) { throw "Os testes dedicados falharam." }

    Write-Host "A validar compilação Python..."
    py -m compileall -q src tests scripts
    if ($LASTEXITCODE -ne 0) { throw "A compilação Python falhou." }

    Write-Host "A executar a única aquisição/replay oficial local..."
    py scripts\validate_official_v087.py --repo-root .
    if ($LASTEXITCODE -ne 0) { throw "O gate oficial local falhou." }

    Write-Host "Gate concluído. Revê artifacts\v087\eurostat_vertical\ECONOMIC_REPORT.md"
    Write-Host "Relatório do gate: artifacts\v087\OFFICIAL_GATE_REPORT.json"
}
finally {
    Pop-Location
}
