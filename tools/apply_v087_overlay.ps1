param(
    [Parameter(Mandatory=$true)]
    [string]$RepoPath
)

$ErrorActionPreference = "Stop"
$overlay = Split-Path -Parent $PSScriptRoot
$repo = (Resolve-Path $RepoPath).Path

if (-not (Test-Path (Join-Path $repo "pyproject.toml"))) {
    throw "RepoPath não parece ser a raiz do repositório Armilar: $repo"
}

$files = Get-ChildItem -Path $overlay -Recurse -File | Where-Object {
    $_.FullName -notlike "*\tools\apply_v087_overlay.ps1" -and
    $_.FullName -notlike "*\__pycache__\*" -and
    $_.Extension -ne ".pyc" -and
    $_.Name -ne "README_APPLY.md" -and
    $_.Name -ne "CODEX_DOWNLOAD_ONLY.txt" -and
    $_.Name -ne "PACKAGE_MANIFEST.sha256"
}

foreach ($file in $files) {
    $relative = $file.FullName.Substring($overlay.Length).TrimStart('\','/')
    $target = Join-Path $repo $relative
    if ((Resolve-Path $file.FullName).Path -eq (Resolve-Path $target -ErrorAction SilentlyContinue).Path) {
        continue
    }
    $targetDir = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -Force $file.FullName $target
}

Write-Host "Overlay v0.8.7 aplicado em $repo"
Write-Host "Executa localmente: py -m unittest tests.test_eurostat_vertical_v087 -v"
