# Interactive console mouse diagnostic for Morkyn launcher.
# Run in a real console (Windows Terminal or conhost), NOT a redirected pipe:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\debug_console_mouse.ps1
# Logs: data\mouse_debug.log
# Keys: Q quit | C clear log display | click rows

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$logPath = Join-Path (Get-Location) "data\mouse_debug.log"
New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null

Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
public static class Mdbg {
    public const int STD_INPUT_HANDLE = -10;
    public const int STD_OUTPUT_HANDLE = -11;
    public const uint GENERIC_READ = 0x80000000;
    public const uint GENERIC_WRITE = 0x40000000;
    public const uint FILE_SHARE_READ = 0x1;
    public const uint FILE_SHARE_WRITE = 0x2;
    public const uint OPEN_EXISTING = 3;
    public const uint ENABLE_PROCESSED_INPUT = 0x0001;
    public const uint ENABLE_LINE_INPUT = 0x0002;
    public const uint ENABLE_ECHO_INPUT = 0x0004;
    public const uint ENABLE_WINDOW_INPUT = 0x0008;
    public const uint ENABLE_MOUSE_INPUT = 0x0010;
    public const uint ENABLE_QUICK_EDIT_MODE = 0x0040;
    public const uint ENABLE_EXTENDED_FLAGS = 0x0080;
    public const uint ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200;
    public const ushort KEY_EVENT = 1;
    public const ushort MOUSE_EVENT = 2;

    [StructLayout(LayoutKind.Sequential)] public struct COORD { public short X; public short Y; }
    [StructLayout(LayoutKind.Sequential)]
    public struct SMALL_RECT { public short Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct CONSOLE_SCREEN_BUFFER_INFO {
        public COORD dwSize; public COORD dwCursorPosition; public ushort wAttributes;
        public SMALL_RECT srWindow; public COORD dwMaximumWindowSize;
    }
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct KEY_EVENT_RECORD {
        public int bKeyDown; public ushort wRepeatCount; public ushort wVirtualKeyCode;
        public ushort wVirtualScanCode; public ushort UnicodeChar; public uint dwControlKeyState;
    }
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct MOUSE_EVENT_RECORD {
        public COORD dwMousePosition; public uint dwButtonState; public uint dwControlKeyState; public uint dwEventFlags;
    }
    [StructLayout(LayoutKind.Explicit, Size = 20)]
    public struct INPUT_RECORD {
        [FieldOffset(0)] public ushort EventType;
        [FieldOffset(4)] public KEY_EVENT_RECORD KeyEvent;
        [FieldOffset(4)] public MOUSE_EVENT_RECORD MouseEvent;
    }

    [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Auto)]
    public static extern IntPtr CreateFile(string name, uint acc, uint share, IntPtr sec, uint disp, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetConsoleMode(IntPtr h, out uint mode);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleMode(IntPtr h, uint mode);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool ReadConsoleInput(IntPtr h, [Out] INPUT_RECORD[] buf, uint len, out uint read);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool FlushConsoleInputBuffer(IntPtr h);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetConsoleScreenBufferInfo(IntPtr h, out CONSOLE_SCREEN_BUFFER_INFO info);
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("kernel32.dll", SetLastError=true)] public static extern uint WaitForSingleObject(IntPtr h, uint ms);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool CloseHandle(IntPtr h);

    public static IntPtr OpenConIn() {
        IntPtr h = CreateFile("CONIN$", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
            IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
        if (h == IntPtr.Zero || h == new IntPtr(-1)) h = GetStdHandle(STD_INPUT_HANDLE);
        return h;
    }
    public static IntPtr OpenConOut() {
        IntPtr h = CreateFile("CONOUT$", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
            IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
        if (h == IntPtr.Zero || h == new IntPtr(-1)) h = GetStdHandle(STD_OUTPUT_HANDLE);
        return h;
    }
    public static string ModeBits(uint m) {
        return string.Format("0x{0:X4} proc={1} line={2} echo={3} win={4} mouse={5} qedit={6} ext={7} vtin={8}",
            m, (m&1)!=0,(m&2)!=0,(m&4)!=0,(m&8)!=0,(m&0x10)!=0,(m&0x40)!=0,(m&0x80)!=0,(m&0x200)!=0);
    }
    public static bool ApplyMouse(IntPtr hin, out uint prev) {
        prev = 0;
        if (!GetConsoleMode(hin, out prev)) return false;
        SetConsoleMode(hin, ENABLE_EXTENDED_FLAGS); // required before clearing quick-edit
        uint mode = ENABLE_EXTENDED_FLAGS | ENABLE_MOUSE_INPUT | ENABLE_WINDOW_INPUT | ENABLE_PROCESSED_INPUT;
        // explicitly no LINE, ECHO, QUICK_EDIT, VT_INPUT
        if (!SetConsoleMode(hin, mode)) return false;
        FlushConsoleInputBuffer(hin);
        return true;
    }
    public static int CursorY(IntPtr hout) {
        CONSOLE_SCREEN_BUFFER_INFO i;
        if (!GetConsoleScreenBufferInfo(hout, out i)) return -1;
        return i.dwCursorPosition.Y;
    }
    public static string WindowInfo(IntPtr hout) {
        CONSOLE_SCREEN_BUFFER_INFO i;
        if (!GetConsoleScreenBufferInfo(hout, out i)) return "no-info";
        return string.Format("buf={0}x{1} cursor=({2},{3}) winTop={4} winBottom={5} winLeft={6}",
            i.dwSize.X, i.dwSize.Y, i.dwCursorPosition.X, i.dwCursorPosition.Y,
            i.srWindow.Top, i.srWindow.Bottom, i.srWindow.Left);
    }
}
"@

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $msg
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    return $line
}

$hin = [Mdbg]::OpenConIn()
$hout = [Mdbg]::OpenConOut()
$hwnd = [Mdbg]::GetConsoleWindow()
$prev = [uint32]0
if (-not [Mdbg]::ApplyMouse($hin, [ref]$prev)) {
    Write-Host "FAILED to enable mouse mode. Is this a real console?" -ForegroundColor Red
    Write-Host "hwnd=$hwnd err=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    exit 1
}
$modeNow = [uint32]0
[void][Mdbg]::GetConsoleMode($hin, [ref]$modeNow)

Clear-Host
$hits = @{}
function Mark([string]$key) {
    $y = [Mdbg]::CursorY($hout)
    $psY = -1
    try { $psY = [int][Console]::CursorTop } catch {}
    if ($y -ge 0) { $hits[$y] = $key }
    # also record PS cursor if different
    if ($psY -ge 0 -and $psY -ne $y) { $hits[$psY] = $key }
    return @{ Win32Y = $y; PsY = $psY; Key = $key }
}

Write-Host "MORKYN MOUSE DEBUG" -ForegroundColor Yellow
Write-Host "log: $logPath" -ForegroundColor DarkGray
Write-Host ([Mdbg]::WindowInfo($hout)) -ForegroundColor DarkGray
Write-Host ("mode " + [Mdbg]::ModeBits($modeNow)) -ForegroundColor DarkGray
Write-Host ("hwnd=$hwnd  IR size=$([Runtime.InteropServices.Marshal]::SizeOf([type][Mdbg+INPUT_RECORD]))") -ForegroundColor DarkGray
Write-Host "Click a row below. Press Q to quit." -ForegroundColor Cyan
Write-Host ""

$marks = @()
foreach ($pair in @(
    @("A", "Row A  Reach"),
    @("P", "Row P  Port"),
    @("B", "Row B  Provider"),
    @("N", "Row N  Pipeline"),
    @("1", "Row 1  PLAY"),
    @("0", "Row 0  Back")
)) {
    $m = Mark $pair[0]
    $marks += $m
    Write-Host ("  [{0}]  {1}   (marked win32Y={2} psY={3})" -f $pair[0], $pair[1], $m.Win32Y, $m.PsY) -ForegroundColor Green
}

Write-Host ""
Write-Host "Hitmap keys: $((@($hits.Keys) | Sort-Object | ForEach-Object { "$_=$($hits[$_])" }) -join ', ')" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "Events:" -ForegroundColor Yellow

[void](Log "=== start hwnd=$hwnd mode=$([Mdbg]::ModeBits($modeNow)) $($([Mdbg]::WindowInfo($hout))) ===")
[void](Log ("hitmap " + ((@($hits.Keys) | Sort-Object | ForEach-Object { "$_=$($hits[$_])" }) -join ", ")))
foreach ($m in $marks) { [void](Log ("mark key=$($m.Key) win32Y=$($m.Win32Y) psY=$($m.PsY)")) }

$prevLeft = $false
$timeoutMs = 120000
$start = [Environment]::TickCount
while ((([Environment]::TickCount - $start) -band 0x7fffffff) -lt $timeoutMs) {
    if ([Mdbg]::WaitForSingleObject($hin, 200) -ne 0) { continue }
    $buf = New-Object 'Mdbg+INPUT_RECORD[]' 1
    $read = [uint32]0
    if (-not [Mdbg]::ReadConsoleInput($hin, $buf, 1, [ref]$read) -or $read -lt 1) { continue }
    $rec = $buf[0]
    if ($rec.EventType -eq [Mdbg]::KEY_EVENT) {
        if ($rec.KeyEvent.bKeyDown -eq 0) { continue }
        $ch = [char]$rec.KeyEvent.UnicodeChar
        $vk = $rec.KeyEvent.wVirtualKeyCode
        $msg = "KEY down vk=$vk ch='$ch'"
        Write-Host (Log $msg) -ForegroundColor White
        if ($ch -eq 'q' -or $ch -eq 'Q' -or $vk -eq 0x51) { break }
        continue
    }
    if ($rec.EventType -eq [Mdbg]::MOUSE_EVENT) {
        $x = [int]$rec.MouseEvent.dwMousePosition.X
        $y = [int]$rec.MouseEvent.dwMousePosition.Y
        $btn = [uint32]$rec.MouseEvent.dwButtonState
        $flags = [uint32]$rec.MouseEvent.dwEventFlags
        $left = ($btn -band 1) -ne 0
        $edge = ""
        if ($left -and -not $prevLeft) { $edge = "PRESS" }
        elseif (-not $left -and $prevLeft) { $edge = "RELEASE" }
        elseif ($left) { $edge = "HOLD" }
        else { $edge = "UP" }
        $prevLeft = $left
        $hit = $null
        if ($hits.ContainsKey($y)) { $hit = $hits[$y] }
        $winTop = 0
        try {
            $info = New-Object Mdbg+CONSOLE_SCREEN_BUFFER_INFO
            [void][Mdbg]::GetConsoleScreenBufferInfo($hout, [ref]$info)
            $winTop = [int]$info.srWindow.Top
        } catch {}
        $yAdj = $y - $winTop
        $hitAdj = $null
        if ($hits.ContainsKey($yAdj)) { $hitAdj = $hits[$yAdj] }
        $flagNames = @()
        if (($flags -band 1) -ne 0) { $flagNames += "MOVED" }
        if (($flags -band 2) -ne 0) { $flagNames += "DBL" }
        if (($flags -band 4) -ne 0) { $flagNames += "WHEEL" }
        if (($flags -band 8) -ne 0) { $flagNames += "HWHEEL" }
        if ($flagNames.Count -eq 0) { $flagNames += "0" }
        $msg = "MOUSE $edge xy=($x,$y) btn=0x{0:X} flags=$($flagNames -join '|') winTop=$winTop y-winTop=$yAdj hit@Y=$hit hit@Y-top=$hitAdj" -f $btn
        $color = if ($edge -eq "PRESS" -or $edge -eq "RELEASE") { "Yellow" } else { "DarkGray" }
        if ($hit -or $hitAdj) { $color = "Green" }
        Write-Host (Log $msg) -ForegroundColor $color
        continue
    }
    [void](Log "OTHER eventType=$($rec.EventType)")
}

[void][Mdbg]::SetConsoleMode($hin, $prev)
Write-Host ""
Write-Host "Done. Log saved to $logPath" -ForegroundColor Cyan
if ($hin -ne [Mdbg]::GetStdHandle(-10)) { [void][Mdbg]::CloseHandle($hin) }
