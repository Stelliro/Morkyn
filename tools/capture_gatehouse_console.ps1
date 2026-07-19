# Capture real Morkyn.ps1 preview output (Write-Host) to a text log for screenshot render.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$outDir = Join-Path $PSScriptRoot "..\benchmarks\reports"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outDir = (Resolve-Path $outDir).Path
$log = Join-Path $outDir "gatehouse-live-preview.txt"

# Transcript does not capture Write-Host colors well; use host UI redirection via Start-Transcript + info
# Instead: run preview and capture console buffer is hard. Dot-source approach won't work due to main body.
# Run child process and redirect *>&1 which captures Write-Host in PS 5+ as Information records.

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell.exe"
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PWD\Morkyn.ps1`" preview"
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = $PWD
$p = [System.Diagnostics.Process]::Start($psi)
$stdout = $p.StandardOutput.ReadToEnd()
$stderr = $p.StandardError.ReadToEnd()
$p.WaitForExit(15000) | Out-Null
$text = ($stdout + "`n" + $stderr).Trim()
Set-Content -LiteralPath $log -Value $text -Encoding UTF8
Write-Host "exit=$($p.ExitCode) bytes=$($text.Length) -> $log"
if ($p.ExitCode -ne 0) { exit $p.ExitCode }
if ($text -notmatch 'GATEHOUSE|G A T E H O U S E') { Write-Host "WARN: board title missing"; exit 2 }
if ($text -notmatch '\[1\].*PLAY') { Write-Host "WARN: PLAY action missing"; exit 3 }
Write-Host "LIVE PREVIEW CAPTURE OK"
exit 0
