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
& $Python -m PyInstaller "packaging\morkyn.spec" --noconfirm --distpath dist --workpath "packaging\build\work"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$out = Join-Path $root "dist\Morkyn"
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
Compress-Archive -Path (Join-Path $out "*") -DestinationPath $zip
Write-Host "Done: $out"
Write-Host "Zip:  $zip"
