# Mørkyn Gatehouse launcher — interactive pre-play board + server start.
# Usage:
#   .\Morkyn.bat
#   .\Morkyn.ps1
#   .\Morkyn.bat local | lan | vpn [port]     (skip menu, launch)
#   .\Morkyn.ps1 -Play                        (skip menu with saved prefs)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# --- CLI args (skip menu when mode provided) ---------------------------------
$script:SkipMenu = $false
$script:PreviewOnly = $false
$script:ArgMode = ""
$script:ArgPort = 0
foreach ($a in $args) {
    $t = [string]$a
    if ($t -match '^(?i)(-play|--play|play)$') { $script:SkipMenu = $true; continue }
    if ($t -match '^(?i)(-preview|--preview|preview)$') { $script:PreviewOnly = $true; continue }
    if ($t -match '^(?i)(local|machine)$') { $script:ArgMode = "local"; $script:SkipMenu = $true; continue }
    if ($t -match '^(?i)(lan|network|web|phone)$') { $script:ArgMode = "network"; $script:SkipMenu = $true; continue }
    if ($t -match '^(?i)(vpn|tunnel|tailscale|wireguard|zerotier)$') { $script:ArgMode = "vpn"; $script:SkipMenu = $true; continue }
    if ($t -match '^\d{2,5}$') { $script:ArgPort = [int]$t; continue }
}
if ($env:AI_RPG_LAUNCH_MODE) {
    $script:SkipMenu = $true
    if (-not $script:ArgMode) { $script:ArgMode = $env:AI_RPG_LAUNCH_MODE.Trim().ToLowerInvariant() }
}

# --- helpers -----------------------------------------------------------------

function Resolve-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ FilePath = $python.Source; BaseArgs = @() } }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @{ FilePath = $py.Source; BaseArgs = @("-3") } }
    $localPython = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $localPython) { return @{ FilePath = $localPython; BaseArgs = @() } }
    throw "Python was not found on PATH and was not found at $localPython."
}

function Test-PortOpen {
    param([string]$HostName, [int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $open = $client.ConnectAsync($HostName, $Port).Wait(300)
        $client.Dispose()
        return $open
    } catch { return $false }
}

function Test-HttpReady {
    param([string]$Url, [int]$TimeoutMilliseconds = 1500)
    try {
        $request = [System.Net.WebRequest]::Create($Url)
        $request.Method = "GET"
        $request.Timeout = $TimeoutMilliseconds
        $request.ReadWriteTimeout = $TimeoutMilliseconds
        $response = $request.GetResponse()
        $statusCode = [int]$response.StatusCode
        $response.Close()
        return ($statusCode -ge 200 -and $statusCode -lt 300)
    } catch {
        if ($_.Exception.Response) { $_.Exception.Response.Close() }
        return $false
    }
}

function Wait-LlmServerReady {
    param([string]$BaseUrl, [System.Diagnostics.Process]$Process = $null, [int]$TimeoutSeconds = 180)
    $modelsUrl = "$($BaseUrl.TrimEnd('/'))/v1/models"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    Write-Host "Waiting for llama.cpp server readiness at $modelsUrl ..."
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process -and $Process.HasExited) { throw "Managed llama.cpp server stopped before it became ready." }
        if (Test-HttpReady -Url $modelsUrl) { Write-Host "llama.cpp server is ready."; return }
        Start-Sleep -Seconds 1
    }
    throw "Timed out waiting $TimeoutSeconds seconds for llama.cpp server readiness at $modelsUrl."
}

function Start-PythonProcess {
    param(
        [hashtable]$PythonCommand,
        [string[]]$Arguments,
        [string]$StandardOutputPath = "",
        [string]$StandardErrorPath = ""
    )
    $allArgs = @($PythonCommand.BaseArgs) + $Arguments
    $startArgs = @{
        FilePath = $PythonCommand.FilePath
        ArgumentList = $allArgs
        NoNewWindow = $true
        PassThru = $true
    }
    if ($StandardOutputPath) { $startArgs.RedirectStandardOutput = $StandardOutputPath }
    if ($StandardErrorPath) { $startArgs.RedirectStandardError = $StandardErrorPath }
    return Start-Process @startArgs
}

function Get-SavedModelConfig {
    param([hashtable]$PythonCommand)
    $script = @'
import json, os, sqlite3
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
                    "ollama_model": str(raw.get("ollama_model") or ""),
                }
    except Exception:
        result = {}
print(json.dumps(result, ensure_ascii=True))
'@
    try {
        $output = & $PythonCommand.FilePath @($PythonCommand.BaseArgs) -c $script 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }
        return ($output | Select-Object -Last 1) | ConvertFrom-Json
    } catch { return $null }
}

function Get-LanIPv4Candidates {
    function Get-AddressScore {
        param([string]$IPAddress, [string]$InterfaceAlias, [string]$AddressState)
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
                $_.IPAddress -and $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0" -and $_.PrefixOrigin -ne "WellKnown"
            } |
            ForEach-Object {
                [PSCustomObject]@{
                    IPAddress = $_.IPAddress
                    InterfaceAlias = $_.InterfaceAlias
                    Score = Get-AddressScore -IPAddress $_.IPAddress -InterfaceAlias $_.InterfaceAlias -AddressState $_.AddressState
                }
            } | Sort-Object -Property Score, InterfaceAlias, IPAddress)
        if ($addresses.Count -gt 0) { return $addresses }
    } catch { }
    try {
        $addresses = @([System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object {
                $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
                -not [System.Net.IPAddress]::IsLoopback($_) -and $_.ToString() -notlike "169.254.*"
            } |
            ForEach-Object {
                [PSCustomObject]@{
                    IPAddress = $_.ToString()
                    InterfaceAlias = "DNS"
                    Score = Get-AddressScore -IPAddress $_.ToString() -InterfaceAlias "DNS" -AddressState ""
                }
            })
        if ($addresses.Count -gt 0) { return $addresses | Sort-Object -Property Score, InterfaceAlias, IPAddress }
    } catch { return @() }
    return @()
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
        } | Sort-Object -Property VpnScore, InterfaceAlias, IPAddress)
}

# --- Gatehouse prefs ---------------------------------------------------------

$PrefsPath = Join-Path $PSScriptRoot "data\launcher_prefs.json"

function New-DefaultPrefs {
    [ordered]@{
        launch_mode              = "local"
        app_port                 = 8000
        model_provider           = "ollama"
        ollama_model             = "qwen3:8b"
        ollama_base_url          = "http://127.0.0.1:11434"
        ollama_think             = $false
        gguf_model_path          = ""
        api_base_url             = "https://api.x.ai/v1"
        api_model                = "grok-4.5"
        api_preset               = "xai"
        llama_cpp_context        = 8192
        llama_cpp_gpu_layers     = -1
        llama_cpp_flash_attn     = $true
        llm_log_mode             = "quiet"
        soft_response_tokens     = 1000
        hard_response_tokens     = 1500
        draft_mode               = "dsl"
        narration_pipeline       = $true
        narration_consolidate    = $true
        fast_verification        = $true
        dsl_skip_verify          = $false
        open_browser             = $true
        llm_startup_timeout      = 180
    }
}

function Load-Prefs {
    $prefs = New-DefaultPrefs
    if (Test-Path -LiteralPath $PrefsPath) {
        try {
            $raw = Get-Content -LiteralPath $PrefsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($key in $prefs.Keys) {
                if ($null -ne $raw.$key) { $prefs[$key] = $raw.$key }
            }
        } catch { }
    }
    # Seed from env / saved model when empty
    if ($env:AI_RPG_LAUNCH_MODE) { $prefs.launch_mode = $env:AI_RPG_LAUNCH_MODE.Trim().ToLowerInvariant() }
    if ($env:AI_RPG_APP_PORT) { $prefs.app_port = [int]$env:AI_RPG_APP_PORT }
    if ($env:AI_RPG_MODEL_PROVIDER) { $prefs.model_provider = $env:AI_RPG_MODEL_PROVIDER.Trim().ToLowerInvariant() }
    if ($env:OLLAMA_MODEL) { $prefs.ollama_model = $env:OLLAMA_MODEL }
    if ($env:AI_RPG_NARRATION_PIPELINE) {
        $prefs.narration_pipeline = @("1", "true", "yes", "on") -contains $env:AI_RPG_NARRATION_PIPELINE.Trim().ToLowerInvariant()
    }
    return $prefs
}

function Save-Prefs {
    param($Prefs)
    $dir = Split-Path -Parent $PrefsPath
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    ($Prefs | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $PrefsPath -Encoding UTF8
}

function Apply-PrefsToEnvironment {
    param($Prefs)
    $mode = [string]$Prefs.launch_mode
    if ($mode -in @("lan", "web", "phone")) { $mode = "network" }
    $env:AI_RPG_LAUNCH_MODE = $mode
    $env:AI_RPG_APP_PORT = [string][int]$Prefs.app_port
    $env:AI_RPG_MODEL_PROVIDER = [string]$Prefs.model_provider
    $env:OLLAMA_MODEL = [string]$Prefs.ollama_model
    $env:OLLAMA_BASE_URL = [string]$Prefs.ollama_base_url
    $env:OLLAMA_THINK = if ($Prefs.ollama_think) { "1" } else { "0" }
    if ($Prefs.api_base_url) { $env:AI_RPG_API_BASE_URL = [string]$Prefs.api_base_url }
    if ($Prefs.api_model) { $env:AI_RPG_API_MODEL = [string]$Prefs.api_model }
    if ($Prefs.api_preset) { $env:AI_RPG_API_PRESET = [string]$Prefs.api_preset }
    if ($Prefs.gguf_model_path) { $env:AI_RPG_GGUF_MODEL = [string]$Prefs.gguf_model_path }
    else { Remove-Item Env:AI_RPG_GGUF_MODEL -ErrorAction SilentlyContinue }
    $env:AI_RPG_LLAMA_CPP_CONTEXT = [string][int]$Prefs.llama_cpp_context
    $env:AI_RPG_LLAMA_CPP_GPU_LAYERS = [string][int]$Prefs.llama_cpp_gpu_layers
    $env:AI_RPG_LLAMA_CPP_FLASH_ATTN = if ($Prefs.llama_cpp_flash_attn) { "True" } else { "False" }
    $env:AI_RPG_LLM_LOG_MODE = [string]$Prefs.llm_log_mode
    $env:AI_RPG_MAX_RESPONSE_TOKENS = [string][int]$Prefs.soft_response_tokens
    $env:AI_RPG_RESPONSE_HARD_CAP_TOKENS = [string][int]$Prefs.hard_response_tokens
    $env:AI_RPG_DRAFT_MODE = [string]$Prefs.draft_mode
    $env:AI_RPG_NARRATION_PIPELINE = if ($Prefs.narration_pipeline) { "1" } else { "0" }
    $env:AI_RPG_NARRATION_PIPELINE_CONSOLIDATE = if ($Prefs.narration_consolidate) { "1" } else { "0" }
    $env:AI_RPG_FAST_VERIFICATION = if ($Prefs.fast_verification) { "1" } else { "0" }
    $env:AI_RPG_DSL_SKIP_VERIFY = if ($Prefs.dsl_skip_verify) { "1" } else { "0" }
    $env:AI_RPG_LLM_STARTUP_TIMEOUT = [string][int]$Prefs.llm_startup_timeout
    $env:OLLAMA_CONTEXT_TOKENS = [string][int]$Prefs.llama_cpp_context
    if (-not $Prefs.open_browser) { $env:AI_RPG_NO_BROWSER = "1" }
    else { Remove-Item Env:AI_RPG_NO_BROWSER -ErrorAction SilentlyContinue }
}

function Lamp([bool]$On) {
    if ($On) { return @{ Text = "[ON ]"; Color = "Green" } }
    return @{ Text = "[OFF]"; Color = "DarkGray" }
}

function Cycle-Value {
    param($Current, [string[]]$Options)
    $i = [array]::IndexOf($Options, [string]$Current)
    if ($i -lt 0) { return $Options[0] }
    return $Options[($i + 1) % $Options.Count]
}

# --- Mouse + keyboard input (Windows console) --------------------------------
# Console mouse/keyboard input.
# IMPORTANT: never P/Invoke ReadConsoleInput with managed INPUT_RECORD[] — the CLR
# marshaler can return zeroed mouse fields. We read 20 raw bytes via IntPtr instead
# (verified with AllocConsole round-trip: mouse (11,22) and keys round-trip correctly).
$script:ConsoleMouseReady = $false
$script:ConsoleMousePrevMode = [uint32]0
$script:ConsoleInputTypeOk = $null
$script:ConsoleInputWarned = $false
$script:MouseDebug = $false
if ($env:MORKYN_MOUSE_DEBUG -match '^(1|true|yes|on)$') { $script:MouseDebug = $true }

function Ensure-ConsoleInputType {
    if ($null -ne $script:ConsoleInputTypeOk) { return [bool]$script:ConsoleInputTypeOk }
    try {
        if (-not ("MorkynConsoleInput" -as [type])) {
            Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Runtime.InteropServices;
public static class MorkynConsoleInput {
    public const int STD_INPUT_HANDLE = -10;
    public const int STD_OUTPUT_HANDLE = -11;
    public const uint ENABLE_MOUSE_INPUT = 0x0010;
    public const uint ENABLE_EXTENDED_FLAGS = 0x0080;
    public const uint ENABLE_QUICK_EDIT_MODE = 0x0040;
    public const uint ENABLE_PROCESSED_INPUT = 0x0001;
    public const uint ENABLE_LINE_INPUT = 0x0002;
    public const uint ENABLE_ECHO_INPUT = 0x0004;
    public const uint ENABLE_WINDOW_INPUT = 0x0008;
    public const uint ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200;
    public const ushort KEY_EVENT = 0x0001;
    public const ushort MOUSE_EVENT = 0x0002;

    [StructLayout(LayoutKind.Sequential)]
    public struct COORD { public short X; public short Y; }
    [StructLayout(LayoutKind.Sequential)]
    public struct SMALL_RECT { public short Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct CONSOLE_SCREEN_BUFFER_INFO {
        public COORD dwSize;
        public COORD dwCursorPosition;
        public ushort wAttributes;
        public SMALL_RECT srWindow;
        public COORD dwMaximumWindowSize;
    }

    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr GetStdHandle(int nStdHandle);
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern IntPtr CreateFileW(string name, uint access, uint share, IntPtr sec, uint disp, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
    [DllImport("kernel32.dll", SetLastError=true, EntryPoint="ReadConsoleInputW")]
    public static extern bool ReadConsoleInputW(IntPtr hConsoleInput, IntPtr lpBuffer, uint nLength, out uint lpNumberOfEventsRead);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool FlushConsoleInputBuffer(IntPtr hConsoleInput);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetConsoleScreenBufferInfo(IntPtr hConsoleOutput, out CONSOLE_SCREEN_BUFFER_INFO info);

    static IntPtr _conIn = IntPtr.Zero;

    public static IntPtr GetConIn() {
        if (_conIn != IntPtr.Zero && _conIn != new IntPtr(-1)) return _conIn;
        // CONIN$ is more reliable than STD_INPUT when hosts wrap stdin.
        _conIn = CreateFileW("CONIN$", 0xC0000000 /*GENERIC_READ|WRITE*/, 0x3, IntPtr.Zero, 3 /*OPEN_EXISTING*/, 0, IntPtr.Zero);
        if (_conIn == IntPtr.Zero || _conIn == new IntPtr(-1))
            _conIn = GetStdHandle(STD_INPUT_HANDLE);
        return _conIn;
    }

    public static IntPtr GetConOut() {
        IntPtr h = CreateFileW("CONOUT$", 0xC0000000, 0x3, IntPtr.Zero, 3, 0, IntPtr.Zero);
        if (h == IntPtr.Zero || h == new IntPtr(-1)) h = GetStdHandle(STD_OUTPUT_HANDLE);
        return h;
    }

    /// <summary>kind: 0=other, 1=key, 2=mouse. Returns 1 if an event was consumed.</summary>
    public static int TryReadEvent(
        out int kind, out int keyDown, out int vk, out int unicode,
        out int mx, out int my, out uint buttons, out uint flags)
    {
        kind = 0; keyDown = 0; vk = 0; unicode = 0; mx = 0; my = 0; buttons = 0; flags = 0;
        IntPtr h = GetConIn();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return 0;

        // 20-byte native INPUT_RECORD — parse manually (do NOT use managed struct arrays).
        IntPtr p = Marshal.AllocHGlobal(20);
        try {
            uint n = 0;
            if (!ReadConsoleInputW(h, p, 1, out n) || n < 1) return 0;
            ushort et = unchecked((ushort)Marshal.ReadInt16(p, 0));
            if (et == KEY_EVENT) {
                kind = 1;
                keyDown = Marshal.ReadInt32(p, 4);
                vk = unchecked((ushort)Marshal.ReadInt16(p, 10));
                unicode = unchecked((ushort)Marshal.ReadInt16(p, 14));
                return 1;
            }
            if (et == MOUSE_EVENT) {
                kind = 2;
                mx = Marshal.ReadInt16(p, 4);
                my = Marshal.ReadInt16(p, 6);
                buttons = unchecked((uint)Marshal.ReadInt32(p, 8));
                flags = unchecked((uint)Marshal.ReadInt32(p, 16));
                return 1;
            }
            return 1; // consumed focus/menu/resize/etc.
        } finally {
            Marshal.FreeHGlobal(p);
        }
    }

    public static bool WaitInput(uint timeoutMs) {
        IntPtr h = GetConIn();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return false;
        return WaitForSingleObject(h, timeoutMs) == 0;
    }

    public static bool ApplyMouseMode(out uint previousMode) {
        previousMode = 0;
        IntPtr h = GetConIn();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return false;
        uint mode = 0;
        if (!GetConsoleMode(h, out mode)) return false;
        previousMode = mode;
        // EXTENDED_FLAGS first so QUICK_EDIT can be cleared; drop VT input (WT).
        SetConsoleMode(h, ENABLE_EXTENDED_FLAGS);
        uint newMode = ENABLE_EXTENDED_FLAGS
            | ENABLE_MOUSE_INPUT
            | ENABLE_WINDOW_INPUT
            | ENABLE_PROCESSED_INPUT;
        // no QUICK_EDIT, LINE, ECHO, VT_INPUT
        if (!SetConsoleMode(h, newMode)) return false;
        FlushConsoleInputBuffer(h);
        return true;
    }

    public static void RestoreMode(uint mode) {
        IntPtr h = GetConIn();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return;
        SetConsoleMode(h, mode);
    }

    public static void Flush() {
        IntPtr h = GetConIn();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return;
        FlushConsoleInputBuffer(h);
    }

    public static int GetCursorY() {
        IntPtr h = GetConOut();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return -1;
        CONSOLE_SCREEN_BUFFER_INFO info;
        if (!GetConsoleScreenBufferInfo(h, out info)) return -1;
        return info.dwCursorPosition.Y;
    }

    public static int GetWindowTop() {
        IntPtr h = GetConOut();
        if (h == IntPtr.Zero || h == new IntPtr(-1)) return 0;
        CONSOLE_SCREEN_BUFFER_INFO info;
        if (!GetConsoleScreenBufferInfo(h, out info)) return 0;
        return info.srWindow.Top;
    }
}
"@
        }
        $script:ConsoleInputTypeOk = $true
        return $true
    } catch {
        $script:ConsoleInputTypeOk = $false
        return $false
    }
}

function Write-MouseDebug {
    param([string]$Message)
    if (-not $script:MouseDebug) { return }
    try {
        $dir = Join-Path $PSScriptRoot "data"
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $Message
        Add-Content -LiteralPath (Join-Path $dir "mouse_debug.log") -Value $line -Encoding UTF8
    } catch { }
}

function Initialize-ConsoleMouse {
    if ($script:ConsoleMouseReady) { return $true }
    try {
        if (-not (Ensure-ConsoleInputType)) { return $false }
        $prev = [uint32]0
        if (-not [MorkynConsoleInput]::ApplyMouseMode([ref]$prev)) {
            $script:ConsoleMouseReady = $false
            Write-MouseDebug "ApplyMouseMode failed"
            return $false
        }
        $script:ConsoleMousePrevMode = $prev
        $script:ConsoleMouseReady = $true
        Write-MouseDebug "mouse mode on (prev=0x$('{0:X}' -f $prev))"
        return $true
    } catch {
        $script:ConsoleMouseReady = $false
        Write-MouseDebug "init exception $($_.Exception.Message)"
        return $false
    }
}

function Restore-ConsoleMouse {
    if (-not $script:ConsoleMouseReady) { return }
    try {
        if (Ensure-ConsoleInputType) {
            [MorkynConsoleInput]::RestoreMode([uint32]$script:ConsoleMousePrevMode)
        }
    } catch { }
    $script:ConsoleMouseReady = $false
}

function Read-HostSafe {
    param([string]$Prompt)
    $wasMouse = $script:ConsoleMouseReady
    Restore-ConsoleMouse
    try {
        return Read-Host $Prompt
    } finally {
        if ($wasMouse) { [void](Initialize-ConsoleMouse) }
    }
}

function Resolve-HitChar {
    param([hashtable]$HitMap, [int]$Y)
    if ($null -eq $HitMap -or $HitMap.Count -lt 1) { return $null }

    $windowTop = 0
    try {
        if (Ensure-ConsoleInputType) { $windowTop = [MorkynConsoleInput]::GetWindowTop() }
        else { $windowTop = [int][Console]::WindowTop }
    } catch { $windowTop = 0 }

    # Exact buffer Y first (Win32 mouse + Win32 cursor marks share this space).
    $candidates = @($Y, ($Y + 1), ($Y - 1), ($Y - $windowTop), ($Y - $windowTop + 1), ($Y - $windowTop - 1))
    foreach ($cand in $candidates) {
        if ($HitMap.ContainsKey($cand)) { return [string]$HitMap[$cand] }
        if ($HitMap.ContainsKey([string]$cand)) { return [string]$HitMap[[string]$cand] }
    }
    return $null
}

function Clear-ConsoleInputQueue {
    try {
        if (Ensure-ConsoleInputType) { [MorkynConsoleInput]::Flush() }
    } catch { }
}

function Get-MarkRowY {
    # Prefer Win32 buffer cursor Y (same coordinate space as mouse events).
    try {
        if (Ensure-ConsoleInputType) {
            $y = [MorkynConsoleInput]::GetCursorY()
            if ($y -ge 0) { return [int]$y }
        }
    } catch { }
    try { return [int][Console]::CursorTop } catch { return -1 }
}

function Convert-ConsoleKeyToChar {
    param($KeyInfo)
    if ($null -eq $KeyInfo) { return "" }
    $ch = ""
    try { $ch = $KeyInfo.KeyChar.ToString() } catch { $ch = "" }
    if ([string]::IsNullOrEmpty($ch) -or ([int][char]$ch -lt 32)) {
        $k = $KeyInfo.Key
        if ($k -eq "D0" -or $k -eq "NumPad0") { return "0" }
        if ($k -eq "D1" -or $k -eq "NumPad1") { return "1" }
        if ($k -eq "D2" -or $k -eq "NumPad2") { return "2" }
        if ($k -eq "D3" -or $k -eq "NumPad3") { return "3" }
        if ($k -eq "D4" -or $k -eq "NumPad4") { return "4" }
        if ($k -eq "D5" -or $k -eq "NumPad5") { return "5" }
        if ($k -eq "D6" -or $k -eq "NumPad6") { return "6" }
        if ($k -eq "D7" -or $k -eq "NumPad7") { return "7" }
        if ($k -eq "D8" -or $k -eq "NumPad8") { return "8" }
        if ($k -eq "D9" -or $k -eq "NumPad9") { return "9" }
        if ($k -eq "Enter") { return "1" }
        if ($k -eq "Escape") { return "0" }
        return ""
    }
    return $ch.ToUpperInvariant()
}

function Convert-VkToChar {
    param([int]$Vk, [int]$Unicode)
    if ($Unicode -ge 32 -and $Unicode -le 0xFFFF) {
        return ([char]$Unicode).ToString().ToUpperInvariant()
    }
    if ($Vk -ge 0x30 -and $Vk -le 0x39) { return ([char]$Vk).ToString() }
    if ($Vk -ge 0x60 -and $Vk -le 0x69) { return ([char](0x30 + ($Vk - 0x60))).ToString() }
    if ($Vk -ge 0x41 -and $Vk -le 0x5A) { return ([char]$Vk).ToString() }
    if ($Vk -eq 0x0D) { return "1" }
    if ($Vk -eq 0x1B) { return "0" }
    if ($Vk -eq 0xBF -or $Vk -eq 0xE2) { return "?" }
    return ""
}

function Read-KeyOnly {
    while ($true) {
        $key = [Console]::ReadKey($true)
        $s = Convert-ConsoleKeyToChar -KeyInfo $key
        if (-not $s) { continue }
        return @{ Kind = "key"; Char = $s.ToUpperInvariant(); Y = -1 }
    }
}

function Read-MenuChoice {
    <#
      Waits for keyboard or left-click.
      $HitMap: hashtable of console buffer Y -> action char
    #>
    param(
        [hashtable] $HitMap = @{}
    )

    $mouseOk = $false
    try { $mouseOk = Initialize-ConsoleMouse } catch { $mouseOk = $false }

    if (-not $mouseOk) {
        Write-MouseDebug "mouse unavailable; keyboard only"
        return Read-KeyOnly
    }

    Clear-ConsoleInputQueue
    if ($script:MouseDebug) {
        $keys = (@($HitMap.Keys) | Sort-Object | ForEach-Object { "$_=$($HitMap[$_])" }) -join ", "
        Write-MouseDebug "wait hitmap: $keys"
    }

    $prevLeftDown = $false
    while ($true) {
        try {
            [void][MorkynConsoleInput]::WaitInput(250)

            $kind = 0; $keyDown = 0; $vk = 0; $unicode = 0
            $mx = 0; $my = 0; $buttons = [uint32]0; $flags = [uint32]0
            $ok = [MorkynConsoleInput]::TryReadEvent(
                [ref]$kind, [ref]$keyDown, [ref]$vk, [ref]$unicode,
                [ref]$mx, [ref]$my, [ref]$buttons, [ref]$flags
            )
            if ($ok -lt 1) { continue }

            if ($kind -eq 1) {
                if ($keyDown -eq 0) { continue }
                $s = Convert-VkToChar -Vk $vk -Unicode $unicode
                if (-not $s) { continue }
                Write-MouseDebug "KEY vk=$vk uni=$unicode -> $s"
                Clear-ConsoleInputQueue
                return @{ Kind = "key"; Char = $s.ToUpperInvariant(); Y = -1 }
            }

            if ($kind -eq 2) {
                # Ignore wheel
                if (($flags -band 0x4) -ne 0 -or ($flags -band 0x8) -ne 0) { continue }

                $leftDown = ($buttons -band 0x1) -ne 0
                $y = [int]$my
                $x = [int]$mx
                $isMove = ($flags -band 0x1) -ne 0
                $isDouble = ($flags -band 0x2) -ne 0

                # Rising edge of left button = one click. Ignore moves/releases for firing.
                $rising = ($leftDown -and -not $prevLeftDown) -or ($isDouble -and $leftDown)
                $prevLeftDown = $leftDown
                if (-not $rising) {
                    if ($script:MouseDebug -and -not $isMove) {
                        Write-MouseDebug "mouse skip xy=($x,$y) btn=0x$('{0:X}' -f $buttons) flags=$flags left=$leftDown"
                    }
                    continue
                }

                $hit = Resolve-HitChar -HitMap $HitMap -Y $y
                Write-MouseDebug "CLICK xy=($x,$y) flags=$flags hit=$hit winTop=$([MorkynConsoleInput]::GetWindowTop())"
                if (-not $hit) { continue }

                Clear-ConsoleInputQueue
                return @{ Kind = "click"; Char = ([string]$hit).ToUpperInvariant(); Y = $y; X = $x }
            }
        } catch {
            if (-not $script:ConsoleInputWarned) {
                $script:ConsoleInputWarned = $true
                try {
                    Write-Host ""
                    Write-Host "  (mouse input failed; keyboard still works: $($_.Exception.Message))" -ForegroundColor DarkYellow
                } catch { }
            }
            Write-MouseDebug "exception $($_.Exception.Message)"
            Restore-ConsoleMouse
            return Read-KeyOnly
        }
    }
}

# --- Terminal UI (fixed-size panels, no scrollbars for click targets) ---------
$script:ConsoleGeomSaved = $false
$script:ConsoleGeomPrev = $null
$script:TuiReady = $false
$script:Box = $null

function Initialize-TuiStyle {
    if ($script:TuiReady) { return }
    try {
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
        $OutputEncoding = [System.Text.UTF8Encoding]::new()
    } catch { }
    try {
        [Console]::Title = "Morkyn"
        [Console]::CursorVisible = $false
    } catch { }
    # Prefer Unicode box drawing; fall back to ASCII if the host mangles it.
    $useUnicode = $true
    try {
        if ($env:MORKYN_ASCII_UI -match '^(1|true|yes|on)$') { $useUnicode = $false }
    } catch { }
    if ($useUnicode) {
        $script:Box = @{
            TL = [char]0x2554; TR = [char]0x2557; BL = [char]0x255A; BR = [char]0x255D
            H  = [char]0x2550; V  = [char]0x2551
            LT = [char]0x2560; RT = [char]0x2563; HL = [char]0x2500
        }
    } else {
        $script:Box = @{
            TL = '+'; TR = '+'; BL = '+'; BR = '+'
            H  = '='; V  = '|'
            LT = '+'; RT = '+'; HL = '-'
        }
    }
    $script:TuiReady = $true
}

function Save-ConsoleGeometry {
    if ($script:ConsoleGeomSaved) { return }
    try {
        $script:ConsoleGeomPrev = @{
            BufW = [Console]::BufferWidth
            BufH = [Console]::BufferHeight
            WinW = [Console]::WindowWidth
            WinH = [Console]::WindowHeight
            Title = [Console]::Title
        }
        $script:ConsoleGeomSaved = $true
    } catch {
        $script:ConsoleGeomPrev = $null
    }
}

function Restore-ConsoleGeometry {
    if (-not $script:ConsoleGeomSaved -or $null -eq $script:ConsoleGeomPrev) { return }
    try {
        $p = $script:ConsoleGeomPrev
        $bw = [int]$p.BufW; $bh = [int]$p.BufH
        $ww = [int]$p.WinW; $wh = [int]$p.WinH
        if ($bw -lt $ww) { $bw = $ww }
        if ($bh -lt $wh) { $bh = $wh }
        # Expand buffer first if needed, then window, then shrink buffer to prior if larger.
        if ([Console]::BufferWidth -lt $bw -or [Console]::BufferHeight -lt $bh) {
            [Console]::SetBufferSize([Math]::Max([Console]::BufferWidth, $bw), [Math]::Max([Console]::BufferHeight, $bh))
        }
        [Console]::SetWindowSize(
            [Math]::Min($ww, [Console]::LargestWindowWidth),
            [Math]::Min($wh, [Console]::LargestWindowHeight)
        )
        [Console]::SetBufferSize($bw, $bh)
        if ($p.Title) { [Console]::Title = [string]$p.Title }
        [Console]::CursorVisible = $true
    } catch { }
    $script:ConsoleGeomSaved = $false
}

function Set-LauncherConsoleSize {
    <#
      Resize window + lock buffer to the same size so the panel is not scrollable.
      Scrollable windows shift mouse Y vs marked rows (the click bug you hit).
    #>
    param(
        [int]$Width = 78,
        [int]$Height = 24,
        [string]$Title = "Morkyn"
    )
    Initialize-TuiStyle
    Save-ConsoleGeometry
    try {
        if ($Title) { [Console]::Title = $Title }
        $maxW = [Console]::LargestWindowWidth
        $maxH = [Console]::LargestWindowHeight
        if ($maxW -lt 40) { $maxW = 120 }
        if ($maxH -lt 15) { $maxH = 50 }
        $w = [Math]::Max(48, [Math]::Min($Width, $maxW))
        $h = [Math]::Max(16, [Math]::Min($Height, $maxH))

        # Grow buffer before growing window; shrink window before shrinking buffer.
        $curBW = [Console]::BufferWidth
        $curBH = [Console]::BufferHeight
        $curWW = [Console]::WindowWidth
        $curWH = [Console]::WindowHeight

        if ($w -gt $curBW -or $h -gt $curBH) {
            [Console]::SetBufferSize([Math]::Max($curBW, $w), [Math]::Max($curBH, $h))
        }
        if ($w -lt $curWW -or $h -lt $curWH) {
            [Console]::SetWindowSize(
                [Math]::Min($w, [Console]::BufferWidth),
                [Math]::Min($h, [Console]::BufferHeight)
            )
        } else {
            [Console]::SetWindowSize($w, $h)
        }
        # Buffer == window => no scrollbars, mouse Y matches drawn rows.
        [Console]::SetBufferSize($w, $h)
        try { [Console]::SetWindowPosition(0, 0) } catch { }
        try { [Console]::CursorVisible = $false } catch { }
        return @{ W = $w; H = $h }
    } catch {
        Write-MouseDebug "resize failed: $($_.Exception.Message)"
        return $null
    }
}

function Write-TuiHRule {
    param([int]$Width, [string]$Color = "DarkCyan", [switch]$Double)
    $b = $script:Box
    $ch = if ($Double) { $b.H } else { $b.HL }
    Write-Host ($b.LT + ($ch.ToString() * ($Width - 2)) + $b.RT) -ForegroundColor $Color
}

function Write-TuiTop {
    param([int]$Width, [string]$Color = "DarkCyan")
    $b = $script:Box
    Write-Host ($b.TL + ($b.H.ToString() * ($Width - 2)) + $b.TR) -ForegroundColor $Color
}

function Write-TuiBottom {
    param([int]$Width, [string]$Color = "DarkCyan")
    $b = $script:Box
    Write-Host ($b.BL + ($b.H.ToString() * ($Width - 2)) + $b.BR) -ForegroundColor $Color
}

function Write-TuiLine {
    param(
        [int]$Width,
        [string]$Text = "",
        [string]$Color = "Gray",
        [string]$Align = "Left"
    )
    $b = $script:Box
    $innerW = $Width - 4
    if ($innerW -lt 8) { $innerW = 8 }
    $t = [string]$Text
    if ($t.Length -gt $innerW) { $t = $t.Substring(0, [Math]::Max(1, $innerW - 1)) + "." }
    switch ($Align) {
        "Center" { $pad = $t.PadLeft([int](($innerW + $t.Length) / 2)).PadRight($innerW) }
        "Right"  { $pad = $t.PadLeft($innerW) }
        default  { $pad = $t.PadRight($innerW) }
    }
    Write-Host ($b.V + " ") -NoNewline -ForegroundColor DarkCyan
    Write-Host $pad -NoNewline -ForegroundColor $Color
    Write-Host (" " + $b.V) -ForegroundColor DarkCyan
}

function Show-Gatehouse {
    param($Prefs, $SavedModel, $Message = "")

    # Tall enough for the full board with no scrollbar (critical for click Y).
    $geom = Set-LauncherConsoleSize -Width 80 -Height 48 -Title "Morkyn - Advanced"
    $w = 76
    if ($geom -and $geom.W -gt 10) { $w = [Math]::Min(76, [int]$geom.W - 2) }

    $hits = @{}
    function Mark([string]$Key) {
        try {
            $y = Get-MarkRowY
            if ($y -ge 0) { $hits[$y] = $Key }
        } catch { }
    }

    $reach = switch ($Prefs.launch_mode) {
        "network" { "LAN / phone" }
        "vpn" { "VPN / overlay" }
        default { "this machine" }
    }
    $provider = [string]$Prefs.model_provider
    $draft = [string]$Prefs.draft_mode
    $gguf = [string]$Prefs.gguf_model_path
    if (-not $gguf -and $SavedModel -and $SavedModel.gguf_model_path) { $gguf = [string]$SavedModel.gguf_model_path }
    if ($gguf.Length -gt 36) { $ggufShort = "..." + $gguf.Substring($gguf.Length - 33) } else { $ggufShort = $(if ($gguf) { $gguf } else { "(none)" }) }

    $pipe = Lamp ([bool]$Prefs.narration_pipeline)
    $cons = Lamp ([bool]$Prefs.narration_consolidate)
    $fast = Lamp ([bool]$Prefs.fast_verification)
    $skip = Lamp ([bool]$Prefs.dsl_skip_verify)
    $think = Lamp ([bool]$Prefs.ollama_think)
    $flash = Lamp ([bool]$Prefs.llama_cpp_flash_attn)
    $browser = Lamp ([bool]$Prefs.open_browser)

    try { Clear-Host } catch { }

    function Write-BoxLine([string]$Text = "", [string]$Color = "Gray", [string]$HitKey = "") {
        if ($HitKey) { Mark $HitKey }
        Write-TuiLine -Width $w -Text $Text -Color $Color
    }
    function Write-Rule { Write-TuiHRule -Width $w -Color DarkCyan }
    function Write-Top  { Write-TuiTop -Width $w -Color DarkCyan }
    function Write-Bot  { Write-TuiBottom -Width $w -Color DarkCyan }
    function Write-Row([string]$Key, [string]$Label, [string]$Value, [string]$ValueColor = "White") {
        Mark $Key
        $b = $script:Box
        $left = ("[$Key] ").PadRight(5) + $Label.PadRight(20)
        $space = $w - 6 - $left.Length
        if ($space -lt 4) { $space = 4 }
        $val = [string]$Value
        if ($val.Length -gt $space) { $val = $val.Substring(0, [Math]::Max(1, $space - 1)) + "." }
        Write-Host ($b.V + "  ") -NoNewline -ForegroundColor DarkCyan
        Write-Host $left -NoNewline -ForegroundColor Cyan
        Write-Host $val.PadLeft($space) -NoNewline -ForegroundColor $ValueColor
        Write-Host ("  " + $b.V) -ForegroundColor DarkCyan
    }
    function Write-LampRow([string]$Key, [string]$Label, $LampInfo, [string]$Hint = "") {
        Mark $Key
        $b = $script:Box
        $left = ("[$Key] ").PadRight(5) + $Label.PadRight(20)
        $mid = $LampInfo.Text + $(if ($Hint) { "  " + $Hint } else { "" })
        $space = $w - 6 - $left.Length
        if ($space -lt 4) { $space = 4 }
        if ($mid.Length -gt $space) { $mid = $mid.Substring(0, $space) }
        $mid = $mid.PadRight($space)
        Write-Host ($b.V + "  ") -NoNewline -ForegroundColor DarkCyan
        Write-Host $left -NoNewline -ForegroundColor Cyan
        Write-Host $LampInfo.Text -NoNewline -ForegroundColor $LampInfo.Color
        $rest = $mid.Substring([Math]::Min($LampInfo.Text.Length, $mid.Length))
        Write-Host $rest -NoNewline -ForegroundColor DarkGray
        Write-Host ("  " + $b.V) -ForegroundColor DarkCyan
    }

    Write-Top
    Write-TuiLine -Width $w -Text "M O R K Y N   ·   G A T E H O U S E" -Color Yellow -Align Center
    Write-TuiLine -Width $w -Text "click a row  ·  or press its key  ·  window sized to fit" -Color DarkGray -Align Center
    Write-Rule
    Write-TuiLine -Width $w -Text "REACH" -Color DarkYellow
    Write-Row "A" "Reach" $reach "White"
    Write-Row "P" "App port" ([string]$Prefs.app_port)
    Write-Rule
    Write-TuiLine -Width $w -Text "MODEL" -Color DarkYellow
    Write-Row "B" "Provider" $provider
    Write-Row "M" "Ollama model" ([string]$Prefs.ollama_model)
    Write-Row "U" "Ollama URL" ([string]$Prefs.ollama_base_url)
    Write-Row "F" "GGUF path" $ggufShort "DarkGray"
    Write-Row "C" "Context tokens" ([string]$Prefs.llama_cpp_context)
    Write-Row "G" "GPU layers" ([string]$Prefs.llama_cpp_gpu_layers)
    Write-LampRow "H" "Flash attention" $flash
    Write-Row "L" "LLM logs" ([string]$Prefs.llm_log_mode)
    Write-LampRow "T" "Ollama think" $think "Qwen3: keep OFF"
    Write-Rule
    Write-TuiLine -Width $w -Text "STORY ENGINE" -Color DarkYellow
    Write-Row "D" "Draft mode" $draft
    Write-LampRow "N" "Narration pipeline" $pipe "para-by-para"
    Write-LampRow "K" "Pipeline consolidate" $cons
    Write-LampRow "V" "Fast verification" $fast
    Write-LampRow "S" "Skip DSL verifier" $skip
    Write-Row "R" "Soft response tok" ([string]$Prefs.soft_response_tokens)
    Write-Row "E" "Hard response tok" ([string]$Prefs.hard_response_tokens)
    Write-Rule
    Write-TuiLine -Width $w -Text "CLIENT" -Color DarkYellow
    Write-LampRow "O" "Open browser" $browser
    Write-Row "W" "LLM startup wait" ([string]$Prefs.llm_startup_timeout + "s")
    Write-Rule
    Write-TuiLine -Width $w -Text "ACTIONS" -Color DarkYellow
    Write-BoxLine "[1]  PLAY     launch with these settings" "Green" "1"
    Write-BoxLine "[0]  back     return to simple menu" "DarkGray" "0"
    Write-BoxLine "[?]  help     what each switch does" "DarkGray" "?"
    Write-BoxLine "[Z]  reset    restore defaults" "DarkGray" "Z"
    if ($Message) {
        Write-Rule
        Write-BoxLine $Message "Magenta"
    }
    Write-Bot
    Write-Host "  click or key > " -NoNewline -ForegroundColor DarkGray
    return $hits
}

function Show-Help {
    [void](Set-LauncherConsoleSize -Width 80 -Height 28 -Title "Morkyn - Help")
    try { Clear-Host } catch { }
    $w = 74
    Write-TuiTop -Width $w
    Write-TuiLine -Width $w -Text "GATEHOUSE FIELD NOTES" -Color Yellow -Align Center
    Write-TuiHRule -Width $w
    Write-TuiLine -Width $w -Text "Reach" -Color Cyan
    Write-TuiLine -Width $w -Text "  local  this PC only (127.0.0.1)" -Color Gray
    Write-TuiLine -Width $w -Text "  LAN    phone/tablet on same Wi-Fi" -Color Gray
    Write-TuiLine -Width $w -Text "  VPN    Tailscale / WireGuard / ZeroTier style" -Color Gray
    Write-TuiHRule -Width $w
    Write-TuiLine -Width $w -Text "Provider" -Color Cyan
    Write-TuiLine -Width $w -Text "  ollama / llama_cpp / openai (cloud-compatible API)" -Color Gray
    Write-TuiHRule -Width $w
    Write-TuiLine -Width $w -Text "Story engine" -Color Cyan
    Write-TuiLine -Width $w -Text "  dsl draft · narration pipeline · consolidate · verify" -Color Gray
    Write-TuiLine -Width $w -Text "Prefs: data\launcher_prefs.json  (applied on PLAY)" -Color DarkGray
    Write-TuiBottom -Width $w
    Write-Host ""
    Write-Host "  Press any key to return..." -ForegroundColor DarkGray
    [void][Console]::ReadKey($true)
}

function Get-ReachLabel {
    param($Prefs)
    switch ($Prefs.launch_mode) {
        "network" { return "LAN / phone" }
        "vpn" { return "VPN / overlay" }
        default { return "this machine only" }
    }
}

function Show-SimpleMenu {
    param($Prefs, $Message = "")

    # Compact home board — fixed size, no scrollbar.
    $geom = Set-LauncherConsoleSize -Width 72 -Height 24 -Title "Morkyn"
    $w = 64
    if ($geom -and $geom.W -gt 10) { $w = [Math]::Min(64, [int]$geom.W - 4) }

    $hits = @{}
    function Mark([string]$Key) {
        try {
            $y = Get-MarkRowY
            if ($y -ge 0) { $hits[$y] = $Key }
        } catch { }
    }

    $reach = Get-ReachLabel -Prefs $Prefs
    $pipeOn = [bool]$Prefs.narration_pipeline
    $pipe = if ($pipeOn) { "ON" } else { "OFF" }
    $pipeColor = if ($pipeOn) { "Green" } else { "DarkGray" }
    $prov = [string]$Prefs.model_provider
    $modelHint = if ($prov -eq "ollama") { [string]$Prefs.ollama_model }
        elseif ($prov -eq "openai") { [string]$Prefs.api_model }
        else { "GGUF / llama.cpp" }

    try { Clear-Host } catch { }
    $b = $script:Box

    Write-TuiTop -Width $w
    Write-TuiLine -Width $w -Text "M O R K Y N" -Color Yellow -Align Center
    Write-TuiLine -Width $w -Text "local-first browser RPG" -Color DarkGray -Align Center
    Write-TuiHRule -Width $w
    Write-TuiLine -Width $w -Text "STATUS  (click a row to change)" -Color DarkYellow

    function Write-StatusRow([string]$Key, [string]$Label, [string]$Value, [string]$ValueColor = "White", [string]$Hint = "") {
        Mark $Key
        $left = ("[$Key]  " + $Label).PadRight(14)
        $rest = $Value
        if ($Hint) { $rest = $Value + "  " + $Hint }
        $space = $w - 6 - $left.Length
        if ($space -lt 4) { $space = 4 }
        if ($rest.Length -gt $space) { $rest = $rest.Substring(0, $space - 1) + "." }
        Write-Host ($b.V + "  ") -NoNewline -ForegroundColor DarkCyan
        Write-Host $left -NoNewline -ForegroundColor Cyan
        Write-Host $rest.PadRight($space) -NoNewline -ForegroundColor $ValueColor
        Write-Host ("  " + $b.V) -ForegroundColor DarkCyan
    }

    Write-StatusRow "2" "Where" $reach "White" ""
    Write-StatusRow "3" "Engine" "$prov  ($modelHint)" "White" ""
    Write-StatusRow "4" "Pipeline" $pipe $pipeColor ""
    Write-TuiLine -Width $w -Text (("Port").PadRight(12) + [string]$Prefs.app_port) -Color DarkGray
    Write-TuiHRule -Width $w
    Write-TuiLine -Width $w -Text "ACTIONS" -Color DarkYellow

    function Write-Action([string]$Key, [string]$Text, [string]$Color) {
        Mark $Key
        Write-TuiLine -Width $w -Text ("[$Key]  " + $Text) -Color $Color
    }
    Write-Action "1" "Play                  start with current settings" "Green"
    Write-Action "2" "Cycle where           local / LAN / VPN" "Cyan"
    Write-Action "3" "Cycle engine          ollama / llama_cpp / cloud" "Cyan"
    Write-Action "4" "Toggle pipeline       narration quality pass" "Cyan"
    Write-Action "9" "Advanced settings...  full Gatehouse board" "DarkYellow"
    Write-Action "0" "Quit" "DarkGray"

    if ($Message) {
        Write-TuiHRule -Width $w
        Write-TuiLine -Width $w -Text $Message -Color Magenta
    }
    Write-TuiBottom -Width $w
    Write-Host "  click or key > " -NoNewline -ForegroundColor DarkGray
    return $hits
}

function Invoke-SimpleMenu {
    param($Prefs, $SavedModel)
    $msg = "click a row or press its number"
    try {
        while ($true) {
            $hits = Show-SimpleMenu -Prefs $Prefs -Message $msg
            $choice = Read-MenuChoice -HitMap $hits
            $c = [string]$choice.Char
            if ($c -eq "1") {
                Save-Prefs -Prefs $Prefs
                return "play"
            }
            if ($c -eq "0") {
                return "quit"
            }
            if ($c -eq "2") {
                $Prefs.launch_mode = Cycle-Value -Current $Prefs.launch_mode -Options @("local", "network", "vpn")
                Save-Prefs -Prefs $Prefs
                $msg = "where -> $(Get-ReachLabel -Prefs $Prefs)"
                continue
            }
            if ($c -eq "3") {
                $Prefs.model_provider = Cycle-Value -Current $Prefs.model_provider -Options @("ollama", "llama_cpp", "openai")
                Save-Prefs -Prefs $Prefs
                $msg = "engine -> $($Prefs.model_provider)"
                continue
            }
            if ($c -eq "4") {
                $Prefs.narration_pipeline = -not [bool]$Prefs.narration_pipeline
                Save-Prefs -Prefs $Prefs
                $msg = "pipeline -> $(if ($Prefs.narration_pipeline) { 'ON' } else { 'OFF' })"
                continue
            }
            if ($c -eq "9") {
                $adv = Invoke-GatehouseMenu -Prefs $Prefs -SavedModel $SavedModel -AllowBack
                if ($adv -eq "play") { return "play" }
                if ($adv -eq "quit") { return "quit" }
                $msg = "back from advanced"
                continue
            }
            $msg = "click Play / a setting row, or press 1-4, 9, 0"
        }
    } finally {
        Restore-ConsoleMouse
        try { [Console]::CursorVisible = $true } catch { }
    }
}

function Invoke-GatehouseMenu {
    param($Prefs, $SavedModel, [switch]$AllowBack)
    $msg = if ($AllowBack) { "advanced - click a row, or 0 to go back" } else { "advanced - click a row" }
    try {
    while ($true) {
        $hits = Show-Gatehouse -Prefs $Prefs -SavedModel $SavedModel -Message $msg
        $choice = Read-MenuChoice -HitMap $hits
        $c = [string]$choice.Char
        if ($c -eq "1") {
            Save-Prefs -Prefs $Prefs
            return "play"
        }
        if ($c -eq "0") {
            if ($AllowBack) { return "back" }
            return "quit"
        }
        if ($c -eq "?" ) { Show-Help; continue }
        if ($c -eq "Z") {
            $defaults = New-DefaultPrefs
            foreach ($key in @($defaults.Keys)) { $Prefs[$key] = $defaults[$key] }
            Save-Prefs -Prefs $Prefs
            $msg = "defaults restored"
            continue
        }
        switch ($c) {
            "A" {
                $Prefs.launch_mode = Cycle-Value -Current $Prefs.launch_mode -Options @("local", "network", "vpn")
                $msg = "reach -> $($Prefs.launch_mode)"
            }
            "P" {
                Write-Host ""
                $v = Read-HostSafe "  App port [$($Prefs.app_port)]"
                if ($v -match '^\d{2,5}$') { $Prefs.app_port = [int]$v; $msg = "port -> $v" }
                else { $msg = "port unchanged" }
            }
            "B" {
                $Prefs.model_provider = Cycle-Value -Current $Prefs.model_provider -Options @("ollama", "llama_cpp", "openai")
                $msg = "provider -> $($Prefs.model_provider)"
            }
            "M" {
                Write-Host ""
                $v = Read-HostSafe "  Ollama model [$($Prefs.ollama_model)]"
                if ($v) { $Prefs.ollama_model = $v.Trim(); $msg = "model -> $($Prefs.ollama_model)" }
            }
            "U" {
                Write-Host ""
                $v = Read-HostSafe "  Ollama base URL [$($Prefs.ollama_base_url)]"
                if ($v) { $Prefs.ollama_base_url = $v.Trim(); $msg = "ollama url set" }
            }
            "F" {
                Write-Host ""
                $v = Read-HostSafe "  GGUF path (blank clears)"
                $Prefs.gguf_model_path = if ($null -eq $v) { "" } else { $v.Trim() }
                $msg = if ($Prefs.gguf_model_path) { "gguf path set" } else { "gguf path cleared" }
            }
            "C" {
                Write-Host ""
                $v = Read-HostSafe "  Context tokens [$($Prefs.llama_cpp_context)]"
                if ($v -match '^\d+$') { $Prefs.llama_cpp_context = [int]$v; $msg = "context -> $v" }
            }
            "G" {
                Write-Host ""
                $v = Read-HostSafe "  GPU layers (-1 = all) [$($Prefs.llama_cpp_gpu_layers)]"
                if ($v -match '^-?\d+$') { $Prefs.llama_cpp_gpu_layers = [int]$v; $msg = "gpu layers -> $v" }
            }
            "H" { $Prefs.llama_cpp_flash_attn = -not [bool]$Prefs.llama_cpp_flash_attn; $msg = "flash attention toggled" }
            "L" {
                $Prefs.llm_log_mode = Cycle-Value -Current $Prefs.llm_log_mode -Options @("quiet", "console")
                $msg = "llm logs -> $($Prefs.llm_log_mode)"
            }
            "T" { $Prefs.ollama_think = -not [bool]$Prefs.ollama_think; $msg = "ollama think toggled" }
            "D" {
                $Prefs.draft_mode = Cycle-Value -Current $Prefs.draft_mode -Options @("dsl", "json")
                $msg = "draft mode -> $($Prefs.draft_mode)"
            }
            "N" { $Prefs.narration_pipeline = -not [bool]$Prefs.narration_pipeline; $msg = "narration pipeline toggled" }
            "K" { $Prefs.narration_consolidate = -not [bool]$Prefs.narration_consolidate; $msg = "consolidator toggled" }
            "V" { $Prefs.fast_verification = -not [bool]$Prefs.fast_verification; $msg = "fast verify toggled" }
            "S" { $Prefs.dsl_skip_verify = -not [bool]$Prefs.dsl_skip_verify; $msg = "skip DSL verifier toggled" }
            "R" {
                Write-Host ""
                $v = Read-HostSafe "  Soft response tokens [$($Prefs.soft_response_tokens)]"
                if ($v -match '^\d+$') { $Prefs.soft_response_tokens = [int]$v; $msg = "soft tokens -> $v" }
            }
            "E" {
                Write-Host ""
                $v = Read-HostSafe "  Hard response tokens [$($Prefs.hard_response_tokens)]"
                if ($v -match '^\d+$') { $Prefs.hard_response_tokens = [int]$v; $msg = "hard tokens -> $v" }
            }
            "O" { $Prefs.open_browser = -not [bool]$Prefs.open_browser; $msg = "open browser toggled" }
            "W" {
                Write-Host ""
                $v = Read-HostSafe "  LLM startup timeout seconds [$($Prefs.llm_startup_timeout)]"
                if ($v -match '^\d+$') { $Prefs.llm_startup_timeout = [int]$v; $msg = "startup wait -> ${v}s" }
            }
            default { $msg = "click a setting row, PLAY (or press 1 / Enter), or back (0)" }
        }
        Save-Prefs -Prefs $Prefs
    }
    } finally {
        Restore-ConsoleMouse
        try { [Console]::CursorVisible = $true } catch { }
    }
}

# --- main --------------------------------------------------------------------

$pythonCommand = Resolve-PythonCommand
& $pythonCommand.FilePath @($pythonCommand.BaseArgs) -c "import fastapi, uvicorn, pydantic" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Missing Python dependencies. Installing requirements..."
    & $pythonCommand.FilePath @($pythonCommand.BaseArgs) -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency install failed." }
    Write-Host ""
}

$savedModelConfig = Get-SavedModelConfig -PythonCommand $pythonCommand
$prefs = Load-Prefs

if ($savedModelConfig) {
    if (-not $prefs.gguf_model_path -and $savedModelConfig.gguf_model_path) {
        $prefs.gguf_model_path = [string]$savedModelConfig.gguf_model_path
    }
    if ($savedModelConfig.provider -and -not $env:AI_RPG_MODEL_PROVIDER) {
        # only seed provider from DB if prefs still default-ish
        if ($prefs.model_provider -eq "ollama" -and $savedModelConfig.provider -eq "llama_cpp") {
            # keep prefs unless user never saved launcher prefs
            if (-not (Test-Path -LiteralPath $PrefsPath) -and $savedModelConfig.provider) {
                $prefs.model_provider = [string]$savedModelConfig.provider
            }
        }
    }
    if ($savedModelConfig.ollama_model -and $prefs.ollama_model -eq "qwen3:8b" -and -not (Test-Path -LiteralPath $PrefsPath)) {
        $prefs.ollama_model = [string]$savedModelConfig.ollama_model
    }
    if ($savedModelConfig.ollama_base_url -and -not (Test-Path -LiteralPath $PrefsPath)) {
        $prefs.ollama_base_url = [string]$savedModelConfig.ollama_base_url
    }
}

if ($script:ArgMode) {
    $prefs.launch_mode = $script:ArgMode
}
if ($script:ArgPort -gt 0) {
    $prefs.app_port = $script:ArgPort
}

if ($script:PreviewOnly) {
    # Default preview = simple menu; use "preview advanced" for full board
    $wantAdvanced = $false
    foreach ($a in $args) {
        if ([string]$a -match '^(?i)(advanced|gatehouse)$') { $wantAdvanced = $true }
    }
    if ($wantAdvanced) {
        [void](Show-Gatehouse -Prefs $prefs -SavedModel $savedModelConfig -Message "advanced preview - not starting servers")
    } else {
        [void](Show-SimpleMenu -Prefs $prefs -Message "simple preview - click rows or press numbers")
    }
    Write-Host ""
    Write-Host "  (preview complete)" -ForegroundColor DarkGray
    exit 0
}

if (-not $script:SkipMenu) {
    try {
        $decision = Invoke-SimpleMenu -Prefs $prefs -SavedModel $savedModelConfig
    } catch {
        # Last-resort only. Normal path never throws from input (Read-MenuChoice falls back).
        Restore-ConsoleMouse
        Write-Host "Menu error; falling back to typed prompts." -ForegroundColor Yellow
        Write-Host ("  " + $_.Exception.Message) -ForegroundColor DarkYellow
        Write-Host "1=Play  2=local  3=LAN  4=VPN  0=Quit"
        try {
            $ans = Read-Host "Choice"
        } catch {
            $ans = "0"
        }
        switch ($ans) {
            "1" { $decision = "play" }
            "2" { $prefs.launch_mode = "local"; Save-Prefs -Prefs $prefs; $decision = "play" }
            "3" { $prefs.launch_mode = "network"; Save-Prefs -Prefs $prefs; $decision = "play" }
            "4" { $prefs.launch_mode = "vpn"; Save-Prefs -Prefs $prefs; $decision = "play" }
            default { $decision = "quit" }
        }
    } finally {
        Restore-ConsoleMouse
        Restore-ConsoleGeometry
        try { [Console]::CursorVisible = $true } catch { }
    }
    if ($decision -ne "play") {
        Write-Host "Launcher closed."
        exit 0
    }
    $prefs = Load-Prefs
} else {
    Save-Prefs -Prefs $prefs
}

Apply-PrefsToEnvironment -Prefs $prefs

# --- resolve runtime from prefs/env (same spirit as old launcher) ------------

$modelPath = if ($env:AI_RPG_GGUF_MODEL) { $env:AI_RPG_GGUF_MODEL } elseif ($prefs.gguf_model_path) { [string]$prefs.gguf_model_path } else { "" }
$llmHost = if ($env:AI_RPG_LLM_HOST) { $env:AI_RPG_LLM_HOST } else { "127.0.0.1" }
$llmPort = if ($env:AI_RPG_LLM_PORT) { [int]$env:AI_RPG_LLM_PORT } else { 8080 }
$ctxTokens = [int]$prefs.llama_cpp_context
$gpuLayers = [int]$prefs.llama_cpp_gpu_layers
$flashAttention = if ($prefs.llama_cpp_flash_attn) { "True" } else { "False" }
$llmStartupTimeout = [int]$prefs.llm_startup_timeout
$llmLogMode = [string]$prefs.llm_log_mode
$baseUrl = "http://$($llmHost):$($llmPort)"
$appPort = [int]$prefs.app_port
$launchMode = [string]$prefs.launch_mode
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

Clear-Host
Write-Host ""
Write-Host "  Mørkyn is opening the gate..." -ForegroundColor Yellow
Write-Host "  Reach: $(if ($vpnMode) { 'VPN / virtual network' } elseif ($appHost -eq '0.0.0.0') { 'local network / phone' } else { 'this machine only' })" -ForegroundColor Gray
Write-Host "  Provider: $($prefs.model_provider)  |  pipeline: $(if ($prefs.narration_pipeline) { 'ON' } else { 'OFF' })  |  draft: $($prefs.draft_mode)" -ForegroundColor Gray
if ($appHost -eq "0.0.0.0") {
    Write-Host "  Local PC URL: $localAppUrl" -ForegroundColor Cyan
    if ($vpnMode) {
        if ($vpnAddress) {
            Write-Host "  VPN URL: $appUrl ($($vpnCandidates[0].InterfaceAlias))" -ForegroundColor Cyan
        } else {
            Write-Host "  No VPN IPv4 detected. Set AI_RPG_PUBLIC_URL if needed." -ForegroundColor DarkYellow
        }
    } elseif ($lanAddress) {
        Write-Host "  Phone/tablet URL: $appUrl ($($lanCandidates[0].InterfaceAlias))" -ForegroundColor Cyan
    }
} else {
    Write-Host "  App URL: $appUrl" -ForegroundColor Cyan
}
Write-Host "  Close this terminal to stop the app and managed LLM server." -ForegroundColor DarkGray
Write-Host ""

$env:LLAMA_CPP_BASE_URL = $baseUrl
$env:OLLAMA_CONTEXT_TOKENS = "$ctxTokens"
if ($prefs.model_provider -eq "ollama") {
    $env:OLLAMA_BASE_URL = [string]$prefs.ollama_base_url
    $env:OLLAMA_MODEL = [string]$prefs.ollama_model
}

$managedProcesses = @()
$llmProcess = $null
$appProcess = $null

try {
    $useManagedLlama = ($prefs.model_provider -eq "llama_cpp")
    if ($prefs.model_provider -eq "openai") {
        Write-Host "Provider is OpenAI-compatible cloud/agent API."
        Write-Host "Base: $([string]$prefs.api_base_url)  model: $([string]$prefs.api_model)"
        Write-Host "Set XAI_API_KEY / OPENAI_API_KEY / AI_RPG_API_KEY (or key in LLM Settings)."
        Write-Host "Agent bridge: POST http://127.0.0.1:$appPort/api/agent/turn"
    }
    if ($useManagedLlama) {
        if (-not $modelPath) {
            Write-Host "No GGUF model path configured for llama_cpp."
            Write-Host "Set path in Gatehouse [F] or LLM Settings; Ollama can still be used if you switch provider."
        } elseif (-not (Test-Path -LiteralPath $modelPath)) {
            Write-Host "Model file not found: $modelPath"
        } elseif (Test-PortOpen -HostName $llmHost -Port $llmPort) {
            Write-Host "LLM server already appears to be running at $baseUrl."
            Wait-LlmServerReady -BaseUrl $baseUrl -TimeoutSeconds $llmStartupTimeout
        } else {
            $gpuSupport = "True"
            try {
                $gpuSupport = & $pythonCommand.FilePath @($pythonCommand.BaseArgs) -c "from llama_cpp import llama_cpp as lc; print(lc.llama_supports_gpu_offload())"
                $gpuSupport = ($gpuSupport | Select-Object -Last 1).Trim()
            } catch { $gpuSupport = "False" }
            if ($gpuSupport -ne "True" -and $gpuLayers -ne 0) {
                Write-Host "Installed llama-cpp-python does not report GPU offload support. Starting CPU-only."
                $gpuLayers = 0
            }
            Write-Host "Starting managed llama.cpp server..."
            Write-Host "Model: $modelPath"
            Write-Host "Context: $ctxTokens tokens / GPU layers: $gpuLayers"
            $llmStdoutPath = ""
            $llmStderrPath = ""
            if ($llmLogMode -ne "console") {
                $logDir = Join-Path $env:TEMP "ai-rpg-logs"
                New-Item -ItemType Directory -Force $logDir | Out-Null
                $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
                $llmStdoutPath = Join-Path $logDir "llama-$stamp.out.log"
                $llmStderrPath = Join-Path $logDir "llama-$stamp.err.log"
                Write-Host "llama.cpp logs quiet -> $llmStdoutPath"
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
    } else {
        Write-Host "Provider is Ollama - not starting managed llama.cpp."
        Write-Host "Expecting Ollama at $([string]$prefs.ollama_base_url) model $([string]$prefs.ollama_model)"
        if (Test-HttpReady -Url "$($prefs.ollama_base_url.TrimEnd('/'))/api/tags" -TimeoutMilliseconds 2000) {
            Write-Host "Ollama responded to /api/tags."
        } else {
            Write-Host "Warning: Ollama did not respond yet. Start it before playing if generation is empty." -ForegroundColor DarkYellow
        }
    }

    Write-Host ""
    Write-Host "Starting FastAPI app server..."
    $appArgs = @("-m", "uvicorn", "app.main:app", "--host", $appHost, "--port", "$appPort")
    $appProcess = Start-PythonProcess -PythonCommand $pythonCommand -Arguments $appArgs
    $managedProcesses += $appProcess

    if ($prefs.open_browser -and -not $env:AI_RPG_NO_BROWSER) {
        Start-Process $browserUrl | Out-Null
    }

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
