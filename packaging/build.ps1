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

# PyInstaller deletes its output folder whole, so it builds into a staging
# folder and only the program (Morkyn.exe, _internal) is replaced in dist\Morkyn.
# The player's own folders beside the exe (data, runtime, versions) are never
# touched: a rebuild once wiped a played copy's data\ and runtime\, and moving
# them aside failed on a file the web view still held (2026-10-22).
$out = Join-Path $root "dist\Morkyn"
$stage = Join-Path $root "dist\.staging"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
& $Python -m PyInstaller "packaging\morkyn.spec" --noconfirm --distpath $stage --workpath "packaging\build\work"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
New-Item -ItemType Directory -Force $out | Out-Null
foreach ($name in @("Morkyn.exe", "_internal")) {
    $old = Join-Path $out $name
    if (Test-Path $old) {
        try { Remove-Item -Recurse -Force $old }
        catch { throw "Close Mørkyn first: $old is in use." }
    }
    Move-Item -Force (Join-Path $stage "Morkyn\$name") $old
}
Remove-Item -Recurse -Force $stage
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
