# Build Mørkyn's packaged Windows folder and zip it.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-Console] [-Python path\to\python.exe]
#
# Needs: the repo's requirements installed, plus pyinstaller sse-starlette
# starlette-context pydantic-settings (the llama.cpp server extras).
# Result: dist\Morkyn\ (run Morkyn.exe) and dist\Morkyn-<version>-windows-x64.zip
param(
    [switch]$Console,
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not $Python) {
    $Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
}
$version = (Select-String -Path "app\main.py" -Pattern 'APP_VERSION = "V?([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Building Morkyn $version with $Python"

& $Python -m pip install --quiet pyinstaller sse-starlette starlette-context pydantic-settings
if ($Console) { $env:MORKYN_BUILD_CONSOLE = "1" } else { Remove-Item Env:MORKYN_BUILD_CONSOLE -ErrorAction SilentlyContinue }

# PyInstaller deletes dist\Morkyn whole. The player's own folders beside the exe
# (saves and settings, engine packs, installed versions) are moved aside and put
# back: a rebuild once wiped a played copy's data\ and runtime\ (2026-10-22).
$out = Join-Path $root "dist\Morkyn"
$keep = Join-Path $root "dist\.keep-player-folders"
$kept = @()
foreach ($folder in @("data", "runtime", "versions")) {
    $src = Join-Path $out $folder
    if (Test-Path $src) {
        New-Item -ItemType Directory -Force $keep | Out-Null
        Move-Item -Force $src (Join-Path $keep $folder)
        $kept += $folder
    }
}
& $Python -m PyInstaller "packaging\morkyn.spec" --noconfirm --distpath dist --workpath "packaging\build\work"
$built = $LASTEXITCODE
foreach ($folder in $kept) {
    New-Item -ItemType Directory -Force $out | Out-Null
    Move-Item -Force (Join-Path $keep $folder) (Join-Path $out $folder)
}
if (Test-Path $keep) { Remove-Item -Recurse -Force $keep }
if ($built -ne 0) { throw "PyInstaller failed" }
foreach ($folder in @("static", "content", "config", "Media")) {
    $dest = Join-Path $out $folder
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse -Force (Join-Path $root $folder) $dest
}
foreach ($file in @("README.md", "LICENSE.md", "PRIVACY_POLICY.md", "CHANGELOG.md")) {
    Copy-Item -Force (Join-Path $root $file) (Join-Path $out $file)
}
Copy-Item -Force (Join-Path $root "packaging\README-package.md") (Join-Path $out "README-package.md")
New-Item -ItemType Directory -Force (Join-Path $out "data") | Out-Null

$zip = Join-Path $root ("dist\Morkyn-{0}-windows-x64.zip" -f $version)
if (Test-Path $zip) { Remove-Item -Force $zip }
# The player's own folders kept above never go into the archive.
$items = Get-ChildItem -LiteralPath $out | Where-Object { $_.Name -notin @("runtime", "versions") -and -not ($_.Name -eq "data" -and (Get-ChildItem -LiteralPath $_.FullName -Force | Select-Object -First 1)) }
Compress-Archive -Path ($items | ForEach-Object { $_.FullName }) -DestinationPath $zip
Write-Host "Done: $out"
Write-Host "Zip:  $zip"
