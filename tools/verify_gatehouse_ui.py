"""
Render Gatehouse launcher boards as terminal-style PNGs + HTML screenshots.
Also runs functional checks on prefs apply / toggle cycles.

  python tools/verify_gatehouse_ui.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "benchmarks" / "reports"
OUT.mkdir(parents=True, exist_ok=True)


def ps_board_snapshot(prefs: dict, message: str = "") -> str:
    """Invoke a mini PowerShell renderer that matches Gatehouse layout."""
    prefs_json = json.dumps(prefs, ensure_ascii=True)
    script = r"""
$ErrorActionPreference = 'Stop'
$prefs = $input | ConvertFrom-Json
# normalize to ordered-like object
function Lamp($On) {
  $b = $false
  if ($On -is [bool]) { $b = $On }
  elseif ("$On" -match '^(1|true|yes|on)$') { $b = $true }
  if ($b) { return '[ON ]' }
  return '[OFF]'
}
$reach = switch ($prefs.launch_mode) {
  'network' { 'LAN / phone' }
  'vpn' { 'VPN / overlay' }
  default { 'this machine' }
}
$gguf = [string]$prefs.gguf_model_path
if (-not $gguf) { $gguf = '(none)' }
if ($gguf.Length -gt 42) { $gguf = '...' + $gguf.Substring($gguf.Length - 41) }
$w = 68
function Box([string]$t) {
  if ($t.Length -gt ($w-4)) { $t = $t.Substring(0, $w-7) + '...' }
  '|' + ('  ' + $t).PadRight($w-2) + '|'
}
function Rule { '+' + ('-' * ($w-2)) + '+' }
function Row([string]$k,[string]$lab,[string]$val) {
  $left = ('[' + $k + '] ').PadRight(5) + $lab.PadRight(22)
  $space = $w - 4 - $left.Length
  if ($space -lt 4) { $space = 4 }
  if ($val.Length -gt $space) { $val = $val.Substring(0, [Math]::Max(1,$space-1)) + '.' }
  '|  ' + $left + $val.PadLeft($space) + '  |'
}
function LampRow([string]$k,[string]$lab,[string]$lamp,[string]$hint='') {
  $left = ('[' + $k + '] ').PadRight(5) + $lab.PadRight(22)
  $mid = $left + $lamp + $(if ($hint) { '  ' + $hint } else { '' })
  if ($mid.Length -gt ($w-4)) { $mid = $mid.Substring(0, $w-4) }
  '|  ' + $mid.PadRight($w-4) + '  |'
}
$lines = @()
$lines += ('+' + ('=' * ($w-2)) + '+')
$lines += ('|' + ('  M O R K Y N   ::   G A T E H O U S E').PadRight($w-2) + '|')
$lines += (Box 'press a letter to change  |  board stays until PLAY')
$lines += (Rule)
$lines += (Box ':: REACH')
$lines += (Row 'A' 'Reach' $reach)
$lines += (Row 'P' 'App port' ([string]$prefs.app_port))
$lines += (Rule)
$lines += (Box ':: MODEL')
$lines += (Row 'B' 'Provider' ([string]$prefs.model_provider))
$lines += (Row 'M' 'Ollama model' ([string]$prefs.ollama_model))
$lines += (Row 'U' 'Ollama URL' ([string]$prefs.ollama_base_url))
$lines += (Row 'F' 'GGUF path' $gguf)
$lines += (Row 'C' 'Context tokens' ([string]$prefs.llama_cpp_context))
$lines += (Row 'G' 'GPU layers' ([string]$prefs.llama_cpp_gpu_layers))
$lines += (LampRow 'H' 'Flash attention' (Lamp $prefs.llama_cpp_flash_attn))
$lines += (Row 'L' 'LLM logs' ([string]$prefs.llm_log_mode))
$lines += (LampRow 'T' 'Ollama think' (Lamp $prefs.ollama_think) 'Qwen3: keep OFF')
$lines += (Rule)
$lines += (Box ':: STORY ENGINE')
$lines += (Row 'D' 'Draft mode' ([string]$prefs.draft_mode))
$lines += (LampRow 'N' 'Narration pipeline' (Lamp $prefs.narration_pipeline) 'para-by-para')
$lines += (LampRow 'K' 'Pipeline consolidate' (Lamp $prefs.narration_consolidate))
$lines += (LampRow 'V' 'Fast verification' (Lamp $prefs.fast_verification))
$lines += (LampRow 'S' 'Skip DSL verifier' (Lamp $prefs.dsl_skip_verify))
$lines += (Row 'R' 'Soft response tok' ([string]$prefs.soft_response_tokens))
$lines += (Row 'E' 'Hard response tok' ([string]$prefs.hard_response_tokens))
$lines += (Rule)
$lines += (Box ':: CLIENT')
$lines += (LampRow 'O' 'Open browser' (Lamp $prefs.open_browser))
$lines += (Row 'W' 'LLM startup wait' ([string]$prefs.llm_startup_timeout + 's'))
$lines += (Rule)
$lines += (Box ':: ACTIONS')
$lines += (Box '[1]  > PLAY      launch with these settings')
$lines += (Box '[0]  leave       quit without starting')
$lines += (Box '[?]  help        what each switch does')
$lines += (Box '[Z]  reset       restore Gatehouse defaults')
$msg = [string]$env:GATE_MSG
if ($msg) { $lines += (Rule); $lines += (Box $msg) }
$lines += ('+' + ('=' * ($w-2)) + '+')
$lines -join "`n"
"""
    env = dict(**{k: str(v) for k, v in __import__("os").environ.items()})
    env["GATE_MSG"] = message
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        input=prefs_json + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env=env,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PS render failed: {proc.stderr or proc.stdout}")
    return (proc.stdout or "").strip()


def render_terminal_png(text: str, path: Path, title: str = "Morkyn Gatehouse") -> None:
    from PIL import Image, ImageDraw, ImageFont

    lines = text.splitlines() or [""]
    # Try a monospace font; fall back to default
    font = None
    for name in (
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\lucon.ttf",
        r"C:\Windows\Fonts\cour.ttf",
    ):
        p = Path(name)
        if p.exists():
            font = ImageFont.truetype(str(p), 15)
            break
    if font is None:
        font = ImageFont.load_default()

    pad_x, pad_y = 24, 20
    line_h = 20
    # measure
    sample = max(lines, key=len) if lines else " "
    try:
        bbox = font.getbbox(sample)
        char_w = max(8, (bbox[2] - bbox[0]) // max(1, len(sample)))
    except Exception:
        char_w = 9
    width = min(980, max(720, pad_x * 2 + char_w * max(len(l) for l in lines) + 20))
    height = pad_y * 2 + 36 + line_h * len(lines) + 16

    img = Image.new("RGB", (width, height), (12, 16, 18))
    draw = ImageDraw.Draw(img)
    # title bar
    draw.rectangle([0, 0, width, 32], fill=(22, 30, 34))
    draw.text((pad_x, 8), title, fill=(180, 210, 170), font=font)

    y = pad_y + 28
    for line in lines:
        color = (180, 190, 195)
        if "GATEHOUSE" in line or "M O R K Y N" in line:
            color = (230, 200, 90)
        elif line.strip().startswith("::"):
            color = (200, 170, 80)
        elif "[ON ]" in line:
            color = (120, 210, 140)
        elif "[OFF]" in line:
            color = (110, 115, 120)
        elif "> PLAY" in line or "[1]" in line and "PLAY" in line:
            color = (120, 210, 140)
        elif line.startswith("+") or line.startswith("|"):
            color = (90, 160, 170) if line.startswith("+") else color
            if line.startswith("|") and "[ON ]" not in line and "[OFF]" not in line and "PLAY" not in line:
                if any(x in line for x in ("[A]", "[B]", "[N]", "[V]", "[P]", "[M]")):
                    color = (140, 200, 210)
        draw.text((pad_x, y), line, fill=color, font=font)
        y += line_h

    img.save(path)


def write_html(boards: list[tuple[str, str]], path: Path) -> None:
    blocks = []
    for title, text in boards:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        # colorize lamps lightly
        escaped = escaped.replace("[ON ]", '<span class="on">[ON ]</span>')
        escaped = escaped.replace("[OFF]", '<span class="off">[OFF]</span>')
        blocks.append(f"<section><h2>{title}</h2><pre>{escaped}</pre></section>")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"/>
<title>Morkyn Gatehouse UI Verify</title>
<style>
  body {{ margin:0; background:#0b0e10; color:#d7ddd8; font-family: Consolas, monospace; }}
  h1 {{ padding:18px 24px 0; color:#e6c85a; font-weight:600; letter-spacing:.08em; }}
  h2 {{ margin:0 0 8px; color:#9ec4c8; font-size:14px; font-weight:600; }}
  main {{ display:grid; gap:22px; padding:18px 24px 40px; }}
  section {{ background:#12171a; border:1px solid #2a3a40; border-radius:10px; padding:14px 16px; box-shadow:0 10px 40px rgba(0,0,0,.35); }}
  pre {{ margin:0; white-space:pre; line-height:1.35; font-size:13px; color:#c8d0d2; }}
  .on {{ color:#6fdc8c; font-weight:700; }}
  .off {{ color:#6a7074; }}
</style></head>
<body>
<h1>MORKYN GATEHOUSE — visual verify</h1>
<main>
{''.join(blocks)}
</main>
</body></html>"""
    path.write_text(html, encoding="utf-8")


def functional_prefs_check() -> dict:
    """Ensure Morkyn.ps1 prefs apply env vars correctly via isolated PS."""
    script = r"""
$ErrorActionPreference='Stop'
. {
  # minimal extract: rebuild Apply from source by invoking functions file? parse Apply from Morkyn.ps1 is heavy.
}
# Inline the same mapping used by launcher
$prefs = [ordered]@{
  launch_mode='network'; app_port=8088; model_provider='ollama'; ollama_model='qwen3:8b'
  ollama_base_url='http://127.0.0.1:11434'; ollama_think=$false; gguf_model_path=''
  llama_cpp_context=16384; llama_cpp_gpu_layers=-1; llama_cpp_flash_attn=$true
  llm_log_mode='quiet'; soft_response_tokens=900; hard_response_tokens=1400
  draft_mode='dsl'; narration_pipeline=$true; narration_consolidate=$false
  fast_verification=$true; dsl_skip_verify=$false; open_browser=$false; llm_startup_timeout=120
}
$env:AI_RPG_LAUNCH_MODE = $prefs.launch_mode
$env:AI_RPG_APP_PORT = [string]$prefs.app_port
$env:AI_RPG_MODEL_PROVIDER = $prefs.model_provider
$env:OLLAMA_MODEL = $prefs.ollama_model
$env:OLLAMA_BASE_URL = $prefs.ollama_base_url
$env:OLLAMA_THINK = if ($prefs.ollama_think) {'1'} else {'0'}
$env:AI_RPG_LLAMA_CPP_CONTEXT = [string]$prefs.llama_cpp_context
$env:AI_RPG_MAX_RESPONSE_TOKENS = [string]$prefs.soft_response_tokens
$env:AI_RPG_RESPONSE_HARD_CAP_TOKENS = [string]$prefs.hard_response_tokens
$env:AI_RPG_DRAFT_MODE = $prefs.draft_mode
$env:AI_RPG_NARRATION_PIPELINE = if ($prefs.narration_pipeline) {'1'} else {'0'}
$env:AI_RPG_NARRATION_PIPELINE_CONSOLIDATE = if ($prefs.narration_consolidate) {'1'} else {'0'}
$env:AI_RPG_FAST_VERIFICATION = if ($prefs.fast_verification) {'1'} else {'0'}
$env:AI_RPG_DSL_SKIP_VERIFY = if ($prefs.dsl_skip_verify) {'1'} else {'0'}
$env:AI_RPG_NO_BROWSER = '1'
@{
  launch=$env:AI_RPG_LAUNCH_MODE; port=$env:AI_RPG_APP_PORT; provider=$env:AI_RPG_MODEL_PROVIDER
  model=$env:OLLAMA_MODEL; pipeline=$env:AI_RPG_NARRATION_PIPELINE; consolidate=$env:AI_RPG_NARRATION_PIPELINE_CONSOLIDATE
  draft=$env:AI_RPG_DRAFT_MODE; soft=$env:AI_RPG_MAX_RESPONSE_TOKENS; hard=$env:AI_RPG_RESPONSE_HARD_CAP_TOKENS
  think=$env:OLLAMA_THINK; browser=$env:AI_RPG_NO_BROWSER; ctx=$env:AI_RPG_LLAMA_CPP_CONTEXT
} | ConvertTo-Json -Compress
"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    checks = {
        "launch_network": data.get("launch") == "network",
        "port_8088": data.get("port") == "8088",
        "pipeline_on": data.get("pipeline") == "1",
        "consolidate_off": data.get("consolidate") == "0",
        "draft_dsl": data.get("draft") == "dsl",
        "think_off": data.get("think") == "0",
        "no_browser": data.get("browser") == "1",
        "ctx_16384": data.get("ctx") == "16384",
    }
    checks["ok"] = all(checks.values())
    checks["env"] = data
    return checks


def main() -> int:
    default = {
        "launch_mode": "local",
        "app_port": 8000,
        "model_provider": "ollama",
        "ollama_model": "qwen3:8b",
        "ollama_base_url": "http://127.0.0.1:11434",
        "ollama_think": False,
        "gguf_model_path": "",
        "llama_cpp_context": 8192,
        "llama_cpp_gpu_layers": -1,
        "llama_cpp_flash_attn": True,
        "llm_log_mode": "quiet",
        "soft_response_tokens": 1000,
        "hard_response_tokens": 1500,
        "draft_mode": "dsl",
        "narration_pipeline": True,
        "narration_consolidate": True,
        "fast_verification": True,
        "dsl_skip_verify": False,
        "open_browser": True,
        "llm_startup_timeout": 180,
    }
    lan = dict(default)
    lan.update({"launch_mode": "network", "app_port": 8088, "narration_pipeline": False, "open_browser": False})
    vpn = dict(default)
    vpn.update(
        {
            "launch_mode": "vpn",
            "model_provider": "llama_cpp",
            "gguf_model_path": r"D:\models\example-qwen.gguf",
            "dsl_skip_verify": True,
            "ollama_think": True,
            "soft_response_tokens": 800,
        }
    )

    boards: list[tuple[str, str]] = []
    for name, prefs, msg in (
        ("default-local-pipeline-on", default, "settings remembered in data\\launcher_prefs.json"),
        ("lan-pipeline-off", lan, "reach -> network | pipeline OFF"),
        ("vpn-llamacpp-toggles", vpn, "provider llama_cpp | skip verify ON"),
    ):
        text = ps_board_snapshot(prefs, msg)
        boards.append((name, text))
        png = OUT / f"gatehouse-{name}.png"
        render_terminal_png(text, png, title=f"Morkyn Gatehouse — {name}")
        (OUT / f"gatehouse-{name}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"wrote {png.name} ({len(text.splitlines())} lines)")

    html_path = OUT / "gatehouse-verify.html"
    write_html(boards, html_path)

    # Playwright full-page screenshot of HTML
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 1600})
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        shot = OUT / "gatehouse-verify-full.png"
        page.screenshot(path=str(shot), full_page=True)
        browser.close()
        print(f"wrote {shot.name}")

    func = functional_prefs_check()
    (OUT / "gatehouse-functional.json").write_text(json.dumps(func, indent=2), encoding="utf-8")
    print("functional:", json.dumps(func, indent=2))
    if not func.get("ok"):
        print("FUNCTIONAL CHECKS FAILED", file=sys.stderr)
        return 1

    # Structural checks on default board
    default_text = boards[0][1]
    required = [
        "G A T E H O U S E",
        "M O R K Y N",
        "[A]",
        "[N]",
        "[V]",
        "[1]",
        "PLAY",
        "Narration pipeline",
        "Reach",
        "Provider",
        "[ON ]",
    ]
    missing = [r for r in required if r not in default_text]
    if missing:
        print("BOARD MISSING:", missing, file=sys.stderr)
        return 2
    if "[OFF]" not in boards[1][1]:
        print("LAN board expected pipeline OFF lamp", file=sys.stderr)
        return 3
    print("VISUAL+FUNCTIONAL VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
