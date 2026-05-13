$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

function Resolve-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ FilePath = $python.Source; BaseArgs = @() }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ FilePath = $py.Source; BaseArgs = @("-3") }
    }

    $localPython = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $localPython) {
        return @{ FilePath = $localPython; BaseArgs = @() }
    }

    throw "Python was not found on PATH and was not found at $localPython."
}

function Test-PortOpen {
    param(
        [string] $HostName,
        [int] $Port
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync($HostName, $Port)
        $open = $task.Wait(300)
        $client.Dispose()
        return $open
    } catch {
        return $false
    }
}

function Test-HttpReady {
    param(
        [string] $Url,
        [int] $TimeoutMilliseconds = 1500
    )

    try {
        $request = [System.Net.WebRequest]::Create($Url)
        $request.Method = "GET"
        $request.Timeout = $TimeoutMilliseconds
        $request.ReadWriteTimeout = $TimeoutMilliseconds
        $response = $request.GetResponse()
        $statusCode = [int] $response.StatusCode
        $response.Close()
        return ($statusCode -ge 200 -and $statusCode -lt 300)
    } catch {
        if ($_.Exception.Response) {
            $_.Exception.Response.Close()
        }
        return $false
    }
}

function Wait-LlmServerReady {
    param(
        [string] $BaseUrl,
        [System.Diagnostics.Process] $Process = $null,
        [int] $TimeoutSeconds = 180
    )

    $modelsUrl = "$($BaseUrl.TrimEnd('/'))/v1/models"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    Write-Host "Waiting for llama.cpp server readiness at $modelsUrl ..."

    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process -and $Process.HasExited) {
            throw "Managed llama.cpp server stopped before it became ready."
        }
        if (Test-HttpReady -Url $modelsUrl) {
            Write-Host "llama.cpp server is ready."
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "Timed out waiting $TimeoutSeconds seconds for llama.cpp server readiness at $modelsUrl."
}

function Start-PythonProcess {
    param(
        [hashtable] $PythonCommand,
        [string[]] $Arguments,
        [string] $StandardOutputPath = "",
        [string] $StandardErrorPath = ""
    )

    $allArgs = @($PythonCommand.BaseArgs) + $Arguments
    $startArgs = @{
        FilePath = $PythonCommand.FilePath
        ArgumentList = $allArgs
        NoNewWindow = $true
        PassThru = $true
    }
    if ($StandardOutputPath) {
        $startArgs.RedirectStandardOutput = $StandardOutputPath
    }
    if ($StandardErrorPath) {
        $startArgs.RedirectStandardError = $StandardErrorPath
    }
    return Start-Process @startArgs
}

function Get-SavedModelConfig {
    param(
        [hashtable] $PythonCommand
    )

    $script = @'
import json
import os
import sqlite3
from pathlib import Path

db_path = Path(os.getenv("AI_RPG_DB", "data/world.db"))
result = {}
if db_path.exists():
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'model_config'").fetchone()
        if row:
            raw = json.loads(row[0])
            if isinstance(raw, dict):
                result = {
                    "provider": str(raw.get("provider") or ""),
                    "gguf_model_path": str(raw.get("gguf_model_path") or ""),
                    "llama_cpp_base_url": str(raw.get("llama_cpp_base_url") or ""),
                    "ollama_base_url": str(raw.get("ollama_base_url") or ""),
                }
    except Exception:
        result = {}
print(json.dumps(result, ensure_ascii=True))
'@

    try {
        $output = & $PythonCommand.FilePath @($PythonCommand.BaseArgs) -c $script 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) {
            return $null
        }
        return ($output | Select-Object -Last 1) | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-LanIPv4Candidates {
    function Get-AddressScore {
        param(
            [string] $IPAddress,
            [string] $InterfaceAlias,
            [string] $AddressState
        )

        $score = 100
        $alias = if ($InterfaceAlias) { $InterfaceAlias.ToLowerInvariant() } else { "" }
        if ($AddressState -eq "Preferred") { $score -= 5 }
        if ($alias -match "wi-?fi|wireless|ethernet") { $score -= 35 }
        if ($IPAddress -like "192.168.*") { $score -= 30 }
        elseif ($IPAddress -match "^172\.(1[6-9]|2[0-9]|3[0-1])\.") { $score -= 20 }
        elseif ($IPAddress -like "10.*") { $score -= 10 }
        if ($alias -match "vpn|proton|wireguard|tailscale|zerotier|vethernet|virtual|vmware|virtualbox|hyper-v|bluetooth|loopback") { $score += 80 }
        return $score
    }

    try {
        $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            ForEach-Object {
                $address = $_.IPAddress
                $alias = $_.InterfaceAlias
                [PSCustomObject]@{
                    IPAddress = $address
                    InterfaceAlias = $alias
                    Score = Get-AddressScore -IPAddress $address -InterfaceAlias $alias -AddressState $_.AddressState
                }
            } |
            Sort-Object -Property Score, InterfaceAlias, IPAddress)
        if ($addresses.Count -gt 0) {
            return $addresses
        }
    } catch {
        # Fall back to DNS address discovery below.
    }

    try {
        $addresses = @([System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object {
                $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
                -not [System.Net.IPAddress]::IsLoopback($_) -and
                $_.ToString() -notlike "169.254.*"
            } |
            ForEach-Object {
                $address = $_.ToString()
                [PSCustomObject]@{
                    IPAddress = $address
                    InterfaceAlias = "DNS"
                    Score = Get-AddressScore -IPAddress $address -InterfaceAlias "DNS" -AddressState ""
                }
            }
        )
        if ($addresses.Count -gt 0) {
            return $addresses | Sort-Object -Property Score, InterfaceAlias, IPAddress
        }
    } catch {
        return @()
    }
    return @()
}

function Get-LanIPv4Address {
    $candidate = @(Get-LanIPv4Candidates) | Select-Object -First 1
    if ($candidate) {
        return $candidate.IPAddress
    }
    return ""
}

function Get-VpnIPv4Candidates {
    $vpnPattern = "vpn|proton|wireguard|tailscale|zerotier|openvpn|tun|tap|hamachi|radmin"
    @(Get-LanIPv4Candidates |
        Where-Object {
            $alias = if ($_.InterfaceAlias) { $_.InterfaceAlias.ToLowerInvariant() } else { "" }
            $alias -match $vpnPattern
        } |
        ForEach-Object {
            $alias = if ($_.InterfaceAlias) { $_.InterfaceAlias.ToLowerInvariant() } else { "" }
            $score = 100
            if ($alias -match "tailscale|zerotier|wireguard") { $score -= 40 }
            elseif ($alias -match "vpn|proton|openvpn|tun|tap") { $score -= 30 }
            if ($_.IPAddress -match "^100\.(6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])\.") { $score -= 20 }
            elseif ($_.IPAddress -like "10.*") { $score -= 10 }
            [PSCustomObject]@{
                IPAddress = $_.IPAddress
                InterfaceAlias = $_.InterfaceAlias
                Score = $_.Score
                VpnScore = $score
            }
        } |
        Sort-Object -Property VpnScore, InterfaceAlias, IPAddress)
}

$pythonCommand = Resolve-PythonCommand

& $pythonCommand.FilePath @($pythonCommand.BaseArgs) -c "import fastapi, uvicorn, pydantic, llama_cpp" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Missing Python dependencies. Installing requirements..."
    & $pythonCommand.FilePath @($pythonCommand.BaseArgs) -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency install failed."
    }
    Write-Host ""
}

$savedModelConfig = Get-SavedModelConfig -PythonCommand $pythonCommand
$savedModelPath = if ($savedModelConfig -and $savedModelConfig.gguf_model_path) { [string]$savedModelConfig.gguf_model_path } else { "" }
$modelPath = if ($env:AI_RPG_GGUF_MODEL) { $env:AI_RPG_GGUF_MODEL } elseif ($savedModelPath) { $savedModelPath } else { "" }
$llmHost = if ($env:AI_RPG_LLM_HOST) { $env:AI_RPG_LLM_HOST } else { "127.0.0.1" }
$llmPort = if ($env:AI_RPG_LLM_PORT) { [int]$env:AI_RPG_LLM_PORT } else { 8080 }
$ctxTokens = if ($env:AI_RPG_LLAMA_CPP_CONTEXT) { [int]$env:AI_RPG_LLAMA_CPP_CONTEXT } else { 8192 }
$gpuLayers = if ($env:AI_RPG_LLAMA_CPP_GPU_LAYERS) { [int]$env:AI_RPG_LLAMA_CPP_GPU_LAYERS } else { -1 }
$flashAttention = if ($env:AI_RPG_LLAMA_CPP_FLASH_ATTN) { $env:AI_RPG_LLAMA_CPP_FLASH_ATTN } else { "True" }
$llmStartupTimeout = if ($env:AI_RPG_LLM_STARTUP_TIMEOUT) { [int]$env:AI_RPG_LLM_STARTUP_TIMEOUT } else { 180 }
$llmLogMode = if ($env:AI_RPG_LLM_LOG_MODE) { $env:AI_RPG_LLM_LOG_MODE.Trim().ToLowerInvariant() } else { "quiet" }
$baseUrl = "http://$($llmHost):$($llmPort)"
$appPort = if ($env:AI_RPG_APP_PORT) { [int]$env:AI_RPG_APP_PORT } else { 8000 }
$launchMode = if ($env:AI_RPG_LAUNCH_MODE) { $env:AI_RPG_LAUNCH_MODE.Trim().ToLowerInvariant() } else { "local" }
$vpnModes = @("vpn", "tunnel", "tailscale", "wireguard", "zerotier", "vpn-port", "vpn_port")
$networkModes = @("network", "lan", "web", "web-local", "web_local", "phone") + $vpnModes
$vpnMode = $vpnModes -contains $launchMode
$appHost = if ($env:AI_RPG_APP_HOST) {
    $env:AI_RPG_APP_HOST
} elseif ($networkModes -contains $launchMode) {
    "0.0.0.0"
} else {
    "127.0.0.1"
}
$lanCandidates = @(Get-LanIPv4Candidates)
$lanAddress = if ($lanCandidates.Count -gt 0) { $lanCandidates[0].IPAddress } else { "" }
$vpnCandidates = if ($vpnMode) { @(Get-VpnIPv4Candidates) } else { @() }
$vpnAddress = if ($vpnCandidates.Count -gt 0) { $vpnCandidates[0].IPAddress } else { "" }
$displayHost = if ($appHost -eq "0.0.0.0") {
    if ($vpnMode -and $vpnAddress) { $vpnAddress }
    elseif ($lanAddress) { $lanAddress }
    else { "127.0.0.1" }
} else { $appHost }
$appUrl = if ($env:AI_RPG_PUBLIC_URL) { $env:AI_RPG_PUBLIC_URL } else { "http://$($displayHost):$($appPort)" }
$localAppUrl = "http://127.0.0.1:$($appPort)"
$browserUrl = if ($env:AI_RPG_BROWSER_URL) { $env:AI_RPG_BROWSER_URL } elseif ($appHost -eq "0.0.0.0") { $localAppUrl } else { $appUrl }

Write-Host "Starting AI RPG..."
Write-Host "Launch mode: $(if ($vpnMode) { 'VPN / virtual network' } elseif ($appHost -eq '0.0.0.0') { 'local network / phone' } else { 'this machine only' })"
if ($appHost -eq "0.0.0.0") {
    Write-Host "Local PC URL: $localAppUrl"
    if ($vpnMode) {
        if ($vpnAddress) {
            Write-Host "VPN URL: $appUrl ($($vpnCandidates[0].InterfaceAlias))"
            if ($vpnCandidates.Count -gt 1) {
                Write-Host "Other detected VPN URLs:"
                foreach ($candidate in ($vpnCandidates | Select-Object -Skip 1 -First 4)) {
                    Write-Host "  http://$($candidate.IPAddress):$appPort ($($candidate.InterfaceAlias))"
                }
            }
        } else {
            Write-Host "No VPN IPv4 address was detected. Connect the VPN/overlay network or set AI_RPG_PUBLIC_URL before launching."
        }
        if ($lanCandidates.Count -gt 0) {
            Write-Host "Detected local URLs:"
            foreach ($candidate in ($lanCandidates | Select-Object -First 4)) {
                Write-Host "  http://$($candidate.IPAddress):$appPort ($($candidate.InterfaceAlias))"
            }
        }
        Write-Host "Use this only on a trusted VPN or private overlay network. If it times out, allow Python/Uvicorn through Windows Firewall for that network profile."
    } elseif ($lanAddress) {
        Write-Host "Phone/tablet URL: $appUrl ($($lanCandidates[0].InterfaceAlias))"
        if ($lanCandidates.Count -gt 1) {
            Write-Host "Other detected local URLs:"
            foreach ($candidate in ($lanCandidates | Select-Object -Skip 1 -First 4)) {
                Write-Host "  http://$($candidate.IPAddress):$appPort ($($candidate.InterfaceAlias))"
            }
        }
    } else {
        Write-Host "No LAN IPv4 address was detected. Check Wi-Fi/Ethernet before using a phone."
    }
    if (-not $vpnMode) {
        Write-Host "Use this only on a trusted local network. If a phone times out, allow Python/Uvicorn through Windows Firewall and use the Wi-Fi/Ethernet URL, not a VPN URL."
    }
} else {
    Write-Host "App URL: $appUrl"
}
Write-Host "Close this terminal to stop the app and managed LLM server."
Write-Host ""

$explicitProvider = if ($env:AI_RPG_MODEL_PROVIDER) { $env:AI_RPG_MODEL_PROVIDER.Trim().ToLowerInvariant() } else { "" }
if ($modelPath -and -not $env:AI_RPG_GGUF_MODEL -and $savedModelPath) {
    Write-Host "Using saved GGUF model path from Model Settings."
}
if ($explicitProvider) {
    $env:AI_RPG_MODEL_PROVIDER = $explicitProvider
} else {
    $env:AI_RPG_MODEL_PROVIDER = "llama_cpp"
}
if ($modelPath) {
    $env:AI_RPG_GGUF_MODEL = $modelPath
} else {
    Remove-Item Env:AI_RPG_GGUF_MODEL -ErrorAction SilentlyContinue
}
$env:LLAMA_CPP_BASE_URL = $baseUrl
$env:OLLAMA_CONTEXT_TOKENS = "$ctxTokens"

$managedProcesses = @()
$llmProcess = $null
$appProcess = $null

try {
    if (-not $modelPath) {
        Write-Host "No GGUF model path is configured."
        Write-Host "No managed llama.cpp server will start. Start Ollama/llama.cpp yourself or set AI_RPG_GGUF_MODEL before generation; otherwise turns use deterministic fallback."
    } elseif (-not (Test-Path -LiteralPath $modelPath)) {
        Write-Host "Model file not found: $modelPath"
        Write-Host "No managed llama.cpp server will start until the path is fixed. Update AI_RPG_GGUF_MODEL or save a valid model path in LLM Settings and restart."
    } elseif (Test-PortOpen -HostName $llmHost -Port $llmPort) {
        Write-Host "LLM server already appears to be running at $baseUrl."
        Wait-LlmServerReady -BaseUrl $baseUrl -TimeoutSeconds $llmStartupTimeout
        Write-Host "Using the existing server. Restart it if you need a different context window or GPU layer setting."
    } else {
        $gpuSupport = & $pythonCommand.FilePath @($pythonCommand.BaseArgs) -c "from llama_cpp import llama_cpp as lc; print(lc.llama_supports_gpu_offload())"
        $gpuSupport = ($gpuSupport | Select-Object -Last 1).Trim()
        if ($gpuSupport -ne "True" -and $gpuLayers -ne 0) {
            Write-Host "Installed llama-cpp-python does not report GPU offload support. Starting CPU-only."
            $gpuLayers = 0
        }

        Write-Host "Starting managed llama.cpp server..."
        Write-Host "Model: $modelPath"
        Write-Host "Context: $ctxTokens tokens"
        Write-Host "GPU layers: $gpuLayers"

        $llmStdoutPath = ""
        $llmStderrPath = ""
        if ($llmLogMode -ne "console") {
            $logDir = Join-Path $env:TEMP "ai-rpg-logs"
            New-Item -ItemType Directory -Force $logDir | Out-Null
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $llmStdoutPath = Join-Path $logDir "llama-$stamp.out.log"
            $llmStderrPath = Join-Path $logDir "llama-$stamp.err.log"
            Write-Host "llama.cpp console logs are quiet. Raw logs: $llmStdoutPath and $llmStderrPath"
            Write-Host "Set AI_RPG_LLM_LOG_MODE=console before launching to show raw llama.cpp access logs."
        }

        $llmArgs = @(
            "-m", "llama_cpp.server",
            "--model", $modelPath,
            "--model_alias", "ai-rpg-local",
            "--host", $llmHost,
            "--port", "$llmPort",
            "--n_ctx", "$ctxTokens",
            "--n_gpu_layers", "$gpuLayers",
            "--flash_attn", $flashAttention,
            "--verbose", "False"
        )
        $llmProcess = Start-PythonProcess -PythonCommand $pythonCommand -Arguments $llmArgs -StandardOutputPath $llmStdoutPath -StandardErrorPath $llmStderrPath
        $managedProcesses += $llmProcess
        Wait-LlmServerReady -BaseUrl $baseUrl -Process $llmProcess -TimeoutSeconds $llmStartupTimeout
    }

    Write-Host ""
    Write-Host "Starting FastAPI app server..."
    $appArgs = @("-m", "uvicorn", "app.main:app", "--host", $appHost, "--port", "$appPort")
    $appProcess = Start-PythonProcess -PythonCommand $pythonCommand -Arguments $appArgs
    $managedProcesses += $appProcess

    Start-Process $browserUrl | Out-Null

    while ($true) {
        Start-Sleep -Seconds 1
        if ($appProcess -and $appProcess.HasExited) {
            Write-Host "App server stopped."
            break
        }
        if ($llmProcess -and $llmProcess.HasExited) {
            Write-Host "LLM server stopped."
            break
        }
    }
} finally {
    Write-Host ""
    Write-Host "Stopping managed processes..."
    foreach ($process in $managedProcesses) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
