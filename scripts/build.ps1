#Requires -Version 5.1
param(
    [switch]$SkipShortcut,
    [switch]$Console,
    [switch]$Release,
    [switch]$Sign,
    [switch]$SkipSign
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "py"
}

$buildArgs = @("scripts\build.py")
if ($Release) { $buildArgs += "--release" }
if ($SkipShortcut) { $buildArgs += "--skip-shortcut" }
if ($Console) { $buildArgs += "--console" }
if ($Sign) { $buildArgs += "--sign" }
if ($SkipSign) { $buildArgs += "--skip-sign" }

if ($python -eq "py") {
    & py -3 @buildArgs
} else {
    & $python @buildArgs
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
