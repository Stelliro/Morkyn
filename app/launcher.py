"""Start, watch and restart Mørkyn's servers. The PowerShell Gatehouse, in Python.

`morkyn_app.py` drives this from its window (or from a terminal with
--console). It owns the two child processes the old launcher started:

  * the FastAPI app server (uvicorn), always;
  * a managed llama.cpp server, only when the engine is llama_cpp.

Settings come from data/launcher_prefs.json through app/launcher_prefs.py, the
same file the in-game Settings write. A setting that only takes effect at start
(reach, port, llama.cpp flags) is applied by restarting: the app server exits
on /api/launcher/restart after writing a flag file, and the watch thread here
sees the flag and starts everything again with the new prefs.

Nothing here imports app.main, so the window can open, and show what is
happening, before the heavy server modules load.
"""
from __future__ import annotations

import collections
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.launcher_prefs import (
    apply_env,
    explicit_pref_int,
    load_prefs,
    normalize_prefs,
    prefs_path,
    prefs_to_env,
    save_prefs,
)

from app.paths import ROOT  # the repo root, or the folder beside the packaged exe
LOG_DIR = ROOT / "data" / "logs"
RESTART_EXIT_CODE = 75
LLM_HOST = os.getenv("AI_RPG_LLM_HOST", "127.0.0.1")
LLM_PORT = int(os.getenv("AI_RPG_LLM_PORT", "8080") or 8080)
APP_READY_TIMEOUT = 180


# --- addresses ---------------------------------------------------------------

_VIRTUAL_HINTS = ("vpn", "proton", "wireguard", "tailscale", "zerotier", "vethernet", "virtual", "vmware",
                  "virtualbox", "hyper-v", "bluetooth", "loopback", "wsl")
_VPN_HINTS = ("vpn", "proton", "wireguard", "tailscale", "zerotier", "openvpn", "tun", "tap", "hamachi", "radmin")


def _usable_ipv4(address: str) -> bool:
    return bool(address) and not address.startswith(("127.", "169.254.")) and address != "0.0.0.0"


def _lan_score(address: str, alias: str) -> int:
    alias = alias.lower()
    score = 100
    if any(word in alias for word in ("wi-fi", "wifi", "wireless", "ethernet", "wlan", "eth")):
        score -= 35
    if address.startswith("192.168."):
        score -= 30
    elif address.startswith("172.") and 16 <= int(address.split(".")[1]) <= 31:
        score -= 20
    elif address.startswith("10."):
        score -= 10
    if any(word in alias for word in _VIRTUAL_HINTS):
        score += 80
    return score


def ipv4_interfaces() -> list[dict[str, Any]]:
    """Every usable IPv4 address with its adapter name, best LAN candidate first."""
    found: list[tuple[str, str]] = []
    try:
        import psutil  # optional; gives adapter names

        for alias, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and _usable_ipv4(addr.address):
                    found.append((addr.address, alias))
    except Exception:
        found = []
    if not found:
        # No adapter names without psutil: the address the default route uses,
        # plus whatever the host name resolves to.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("10.255.255.255", 1))
                found.append((probe.getsockname()[0], "default route"))
        except OSError:
            pass
        try:
            for address in socket.gethostbyname_ex(socket.gethostname())[2]:
                if _usable_ipv4(address) and all(address != seen for seen, _ in found):
                    found.append((address, "host name"))
        except OSError:
            pass
    rows = [{"address": a, "alias": n, "score": _lan_score(a, n)} for a, n in found if _usable_ipv4(a)]
    return sorted(rows, key=lambda row: (row["score"], row["alias"], row["address"]))


def vpn_interfaces(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out = []
    for row in rows if rows is not None else ipv4_interfaces():
        alias = row["alias"].lower()
        if not any(word in alias for word in _VPN_HINTS):
            continue
        score = 100
        if any(word in alias for word in ("tailscale", "zerotier", "wireguard")):
            score -= 40
        else:
            score -= 30
        first, second = (int(part) for part in row["address"].split(".")[:2])
        if first == 100 and 64 <= second <= 127:
            score -= 20
        elif first == 10:
            score -= 10
        out.append({**row, "vpn_score": score})
    return sorted(out, key=lambda row: (row["vpn_score"], row["alias"], row["address"]))


def runtime_plan(prefs: dict[str, Any]) -> dict[str, Any]:
    """Bind address and the URLs to show for these prefs."""
    p = normalize_prefs(prefs)
    port = p["app_port"]
    mode = p["launch_mode"]
    host = os.getenv("AI_RPG_APP_HOST") or ("0.0.0.0" if mode in {"lan", "vpn"} else "127.0.0.1")
    local_url = f"http://127.0.0.1:{port}"
    plan: dict[str, Any] = {
        "reach": mode,
        "host": host,
        "port": port,
        "local_url": local_url,
        "lan_url": "",
        "lan_adapter": "",
        "vpn_url": "",
        "vpn_adapter": "",
        "public_url": os.getenv("AI_RPG_PUBLIC_URL", ""),
    }
    if host == "0.0.0.0":
        rows = ipv4_interfaces()
        if rows:
            plan["lan_url"] = f"http://{rows[0]['address']}:{port}"
            plan["lan_adapter"] = rows[0]["alias"]
        if mode == "vpn":
            vpn = vpn_interfaces(rows)
            if vpn:
                plan["vpn_url"] = f"http://{vpn[0]['address']}:{port}"
                plan["vpn_adapter"] = vpn[0]["alias"]
    elif host not in {"127.0.0.1", "localhost"}:
        plan["local_url"] = f"http://{host}:{port}"
    return plan


# --- small checks --------------------------------------------------------------

def port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def saved_model_config() -> dict[str, str]:
    """model_config from world.db, read without importing the app (the Gatehouse did the same)."""
    db_path = Path(os.getenv("AI_RPG_DB") or (ROOT / "data" / "world.db"))
    if not db_path.is_file():
        return {}
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'model_config'").fetchone()
        raw = json.loads(row[0]) if row else {}
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        "provider": str(raw.get("provider") or ""),
        "gguf_model_path": str(raw.get("gguf_model_path") or ""),
        "mle_model": str(raw.get("mle_model") or raw.get("ollama_model") or ""),
    }


def seed_prefs_from_saved_model() -> dict[str, Any]:
    """First launch only: carry the model the world.db already remembers into the prefs."""
    prefs = load_prefs()
    saved = saved_model_config()
    if not saved:
        return prefs
    updates: dict[str, Any] = {}
    if not prefs["gguf_model_path"] and saved.get("gguf_model_path"):
        updates["gguf_model_path"] = saved["gguf_model_path"]
    if not prefs_path().is_file():
        if saved.get("provider") and not os.getenv("AI_RPG_MODEL_PROVIDER"):
            updates["model_provider"] = saved["provider"]
        if saved.get("mle_model") and prefs["mle_model"] == "qwen3:8b":
            updates["mle_model"] = saved["mle_model"]
    return save_prefs(updates) if updates else prefs


# --- child processes -------------------------------------------------------------

class _KillOnClose:
    """A Windows job object: children die with the launcher, even if it crashes."""

    def __init__(self) -> None:
        self.handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.OpenProcess.restype = wintypes.HANDLE
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return

            class _Basic(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _Io(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class _Extended(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _Basic),
                    ("IoInfo", _Io),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = _Extended()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                self.handle = job
                self._kernel32 = kernel32
        except Exception:
            self.handle = None

    def add(self, proc: subprocess.Popen) -> None:
        if not self.handle:
            return
        try:
            access = 0x0001 | 0x0100  # PROCESS_TERMINATE | PROCESS_SET_QUOTA
            handle = self._kernel32.OpenProcess(access, False, proc.pid)
            if handle:
                self._kernel32.AssignProcessToJobObject(self.handle, handle)
                self._kernel32.CloseHandle(handle)
        except Exception:
            pass


def _no_window_flags() -> int:
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


# Resolved in the parent, before any fork: the child runs between fork and exec
# with only the forking thread, and a library load there (an import of _ctypes,
# CDLL) can find the loader mid-update by another thread. With the Qt window's
# threads running, the server died at start with exit 127, "Inconsistency
# detected by ld.so: dl-open.c ... r_state == RT_CONSISTENT" (2026-10-23).
_PRCTL: Any = None


def _prctl() -> Any:
    global _PRCTL
    if _PRCTL is None:
        import ctypes

        _PRCTL = ctypes.CDLL(None).prctl
    return _PRCTL


def _die_with_parent(prctl: Any) -> Callable[[], None]:
    """Linux's version of the job object: the child gets SIGTERM when the launcher dies."""

    def preexec() -> None:
        try:
            prctl(1, 15)  # PR_SET_PDEATHSIG, SIGTERM
        except Exception:
            pass

    return preexec


def _child_options() -> dict[str, Any]:
    opts: dict[str, Any] = {"creationflags": _no_window_flags()}
    if sys.platform.startswith("linux"):
        try:
            opts["preexec_fn"] = _die_with_parent(_prctl())
        except Exception:
            pass
    return opts


# PR_SET_PDEATHSIG fires when the *thread* that forked the child exits, not the
# process. The window starts the server from the short-lived morkyn-start
# thread, so on Linux the server got SIGTERM about a second after it was ready
# and the window showed "127.0.0.1 refused to connect" (Stell, 2026-10-23, the
# first Linux window). Every child is forked from this one thread, which lives
# as long as the launcher.
_SPAWNER: Any = None
_SPAWNER_LOCK = threading.Lock()


def _spawn(args: list[str], **kwargs: Any) -> subprocess.Popen:
    """subprocess.Popen with _child_options(), forked from the launcher's long-lived spawner thread on Linux."""
    kwargs.update(_child_options())
    if not sys.platform.startswith("linux"):
        return subprocess.Popen(args, **kwargs)
    global _SPAWNER
    with _SPAWNER_LOCK:
        if _SPAWNER is None:
            from concurrent.futures import ThreadPoolExecutor

            _SPAWNER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morkyn-spawner")
    return _SPAWNER.submit(subprocess.Popen, args, **kwargs).result()


def server_command(host: str, port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        # A packaged build has no `-m uvicorn`; the exe serves when asked to.
        return [sys.executable, "--serve", host, str(port)]
    return [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)]


def module_command(module: str, *args: str) -> list[str]:
    """``python -m module args``, or the packaged exe running that module (morkyn_app --run-module)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-module", module, *args]
    return [sys.executable, "-m", module, *args]


def snippet_command(code: str) -> list[str]:
    """``python -c code``, or the packaged exe running it (morkyn_app --run-code)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-code", code]
    return [sys.executable, "-c", code]


class Supervisor:
    """States: idle -> starting -> ready | failed; ready -> restarting -> starting ..."""

    def __init__(self, on_change: Callable[["Supervisor"], None] | None = None,
                 overrides: dict[str, Any] | None = None) -> None:
        self.on_change = on_change
        # CLI words (local / lan / vpn / a port) win over the saved prefs once,
        # and are saved, the way the Gatehouse treated them.
        self.overrides = dict(overrides or {})
        self.state = "idle"
        self.error = ""
        self.plan: dict[str, Any] = {}
        self.prefs: dict[str, Any] = {}
        self.attached = False
        self.lines: collections.deque[str] = collections.deque(maxlen=400)
        self._lock = threading.RLock()
        self._app: subprocess.Popen | None = None
        self._llm: subprocess.Popen | None = None
        self._job = _KillOnClose()
        self._stopping = False
        self._generation = 0
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.restart_flag = LOG_DIR / "restart.request"
        self.launcher_log = LOG_DIR / "launcher.log"
        self.server_log = LOG_DIR / "server.log"
        try:
            self.launcher_log.write_text("", encoding="utf-8")
        except OSError:
            pass

    # -- reporting --
    def log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        for line in str(text).splitlines() or [""]:
            self.lines.append(f"{stamp}  {line}")
            try:
                with self.launcher_log.open("a", encoding="utf-8") as fh:
                    fh.write(f"{stamp}  {line}\n")
            except OSError:
                pass
            if sys.stdout is not None:
                try:
                    print(f"  {line}", flush=True)
                except Exception:
                    pass
        self._changed()

    def _set(self, state: str, error: str = "") -> None:
        self.state = state
        self.error = error
        self._changed()

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change(self)
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "error": self.error,
            "attached": self.attached,
            "plan": dict(self.plan),
            "prefs": dict(self.prefs),
            "lines": list(self.lines)[-120:],
            "server_log_tail": self.server_log_tail(40) if self.state == "failed" else [],
            "log_dir": str(LOG_DIR),
        }

    def server_log_tail(self, count: int = 40) -> list[str]:
        try:
            text = self.server_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return text.splitlines()[-count:]

    @property
    def url(self) -> str:
        return str(self.plan.get("local_url") or "")

    # -- lifecycle --
    def start_async(self) -> None:
        threading.Thread(target=self.start, name="morkyn-start", daemon=True).start()

    def start(self) -> bool:
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._stopping = False
            self.attached = False
            self._set("starting")
            try:
                ok = self._start_locked()
            except Exception as exc:  # anything unexpected still lands on the boot screen
                self.log(f"Start failed: {exc}")
                self._stop_children()
                self._set("failed", str(exc))
                return False
        if ok and not self.attached:
            threading.Thread(target=self._watch, args=(generation,), name="morkyn-watch", daemon=True).start()
        return ok

    def _start_locked(self) -> bool:
        prefs = seed_prefs_from_saved_model()
        if self.overrides:
            prefs = save_prefs(self.overrides)
            self.overrides = {}
        self.prefs = prefs
        self.plan = plan = runtime_plan(prefs)
        reach_label = {"local": "this machine only", "lan": "local network / phone", "vpn": "VPN / overlay"}[plan["reach"]]
        self.log("Mørkyn is opening the gate…")
        self.log(f"Reach: {reach_label}   port {plan['port']}")
        self.log(f"Engine: {prefs['model_provider']}   pipeline: {'on' if prefs['narration_pipeline'] else 'off'}"
                 f"   draft: {prefs['draft_mode']}")
        if plan["host"] == "0.0.0.0":
            self.log(f"This PC: {plan['local_url']}")
            if plan["reach"] == "vpn":
                self.log(f"VPN: {plan['vpn_url']} ({plan['vpn_adapter']})" if plan["vpn_url"]
                         else "No VPN adapter found. Set AI_RPG_PUBLIC_URL if your overlay network uses another name.")
            elif plan["lan_url"]:
                self.log(f"Phone / tablet: {plan['lan_url']} ({plan['lan_adapter']})")
        else:
            self.log(f"Address: {plan['local_url']}")

        env = dict(os.environ)
        apply_env(prefs_to_env(prefs), env)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["LLAMA_CPP_BASE_URL"] = f"http://{LLM_HOST}:{LLM_PORT}"
        env["AI_RPG_SUPERVISED"] = "1"
        env["AI_RPG_RESTART_FLAG"] = str(self.restart_flag)
        env["AI_RPG_LAUNCHER_PLAN"] = json.dumps(plan, ensure_ascii=True)
        env["AI_RPG_LAUNCHER_LOG"] = str(self.launcher_log)
        try:
            self.restart_flag.unlink()
        except OSError:
            pass

        port = int(plan["port"])
        if port_open("127.0.0.1", port):
            if http_ok(f"{plan['local_url']}/api/model-config"):
                # A Mørkyn server someone started by hand. Use it, but say that
                # settings needing a restart cannot be applied from here.
                self.attached = True
                self.log(f"A Mørkyn server is already running on port {port}; using it.")
                self.log("Settings that need a restart will not apply until that server is restarted.")
                self._set("ready")
                return True
            raise RuntimeError(f"Port {port} is already used by another program. Pick another port below and retry.")

        if prefs["model_provider"] == "llama_cpp":
            self._start_llama(prefs, env)
        elif prefs["model_provider"] == "openai":
            self.log(f"Cloud / agent API: {prefs['api_base_url']}  model {prefs['api_model']}")
            self.log("The key comes from XAI_API_KEY / OPENAI_API_KEY / AI_RPG_API_KEY or LLM details in Settings.")
        else:
            self.log(f"MLE loads {prefs['mle_model']} in-process on the first model call.")

        self.log("Starting the game server…")
        self._rotate_server_log()
        log_fh = self.server_log.open("ab")
        try:
            self._app = _spawn(
                server_command(plan["host"], port),
                cwd=str(ROOT),
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        finally:
            log_fh.close()
        self._job.add(self._app)
        deadline = time.monotonic() + APP_READY_TIMEOUT
        ready_url = f"{plan['local_url']}/api/launcher/status"
        while time.monotonic() < deadline:
            if self._app.poll() is not None:
                tail = "\n".join(self.server_log_tail(12))
                raise RuntimeError(f"The game server stopped while starting (exit {self._app.returncode}).\n{tail}")
            if http_ok(ready_url, timeout=1.0):
                self.log("Game server is ready.")
                self._set("ready")
                return True
            time.sleep(0.4)
        raise RuntimeError(f"The game server did not answer within {APP_READY_TIMEOUT} seconds. See {self.server_log}.")

    def _rotate_server_log(self) -> None:
        try:
            if self.server_log.is_file() and self.server_log.stat().st_size:
                self.server_log.replace(self.server_log.with_suffix(".prev.log"))
        except OSError:
            pass

    def _start_llama(self, prefs: dict[str, Any], env: dict[str, str]) -> None:
        model_path = prefs["gguf_model_path"]
        base_url = env["LLAMA_CPP_BASE_URL"]
        if not model_path:
            self.log("No GGUF file is set for llama.cpp. Set one in Settings, or switch the engine to MLE.")
            return
        if not Path(model_path).is_file():
            self.log(f"GGUF file not found: {model_path}")
            return
        timeout = int(prefs["llm_startup_timeout"])
        if port_open(LLM_HOST, LLM_PORT):
            self.log(f"A llama.cpp server already answers at {base_url}.")
            self._wait_llama(base_url, None, timeout)
            return
        context = explicit_pref_int(prefs["llama_cpp_context"]) or self._auto_context(model_path)
        gpu_layers = int(prefs["llama_cpp_gpu_layers"])
        if gpu_layers != 0 and not self._llama_has_gpu():
            self.log("This llama-cpp-python build reports no GPU offload. Starting on the CPU.")
            gpu_layers = 0
        self.log(f"Starting llama.cpp: {Path(model_path).name}")
        self.log(f"Context {context} tokens, GPU layers {gpu_layers}")
        if prefs["llm_log_mode"] == "console":
            out_path = self.server_log.with_name("llama.log")
        else:
            temp = Path(tempfile.gettempdir()) / "ai-rpg-logs"
            temp.mkdir(parents=True, exist_ok=True)
            out_path = temp / f"llama-{time.strftime('%Y%m%d-%H%M%S')}.log"
        self.log(f"llama.cpp log: {out_path}")
        args = [
            *module_command("llama_cpp.server"),
            "--model", model_path,
            "--model_alias", "ai-rpg-local",
            "--host", LLM_HOST,
            "--port", str(LLM_PORT),
            "--n_ctx", str(context),
            "--n_gpu_layers", str(gpu_layers),
            "--flash_attn", "True" if prefs["llama_cpp_flash_attn"] else "False",
            "--verbose", "False",
        ]
        with out_path.open("ab") as fh:
            self._llm = _spawn(args, cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL)
        self._job.add(self._llm)
        self._wait_llama(base_url, self._llm, timeout)

    def _wait_llama(self, base_url: str, proc: subprocess.Popen | None, timeout: int) -> None:
        self.log(f"Waiting for llama.cpp at {base_url} …")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                raise RuntimeError("The llama.cpp server stopped before it was ready. Check its log, the GGUF path, "
                                   "or lower the GPU layers in Settings.")
            if http_ok(f"{base_url}/v1/models"):
                self.log("llama.cpp is ready.")
                return
            time.sleep(1)
        raise RuntimeError(f"llama.cpp did not answer within {timeout} seconds. Raise the startup wait in Settings.")

    def _auto_context(self, model_path: str) -> int:
        try:
            out = subprocess.run(module_command("app.model_limits", "--context", model_path), cwd=str(ROOT),
                                 capture_output=True, text=True, timeout=60, creationflags=_no_window_flags())
            number = int((out.stdout or "").strip().splitlines()[-1])
            if number > 0:
                return number
        except Exception:
            pass
        return 32768

    def _llama_has_gpu(self) -> bool:
        try:
            out = subprocess.run(
                snippet_command("from llama_cpp import llama_cpp as lc; print(lc.llama_supports_gpu_offload())"),
                cwd=str(ROOT), capture_output=True, text=True, timeout=60, creationflags=_no_window_flags())
            return (out.stdout or "").strip().splitlines()[-1:] == ["True"]
        except Exception:
            return False

    def _watch(self, generation: int) -> None:
        while True:
            time.sleep(0.5)
            if self._stopping or generation != self._generation:
                return
            app, llm = self._app, self._llm
            app_code = app.poll() if app else None
            llm_code = llm.poll() if llm else None
            if app_code is None and llm_code is None:
                continue
            with self._lock:
                if self._stopping or generation != self._generation:
                    return
                wanted = app_code == RESTART_EXIT_CODE or self.restart_flag.exists()
                if wanted:
                    self.log("Restarting with the new settings…")
                    self._set("restarting")
                    self._stop_children()
                else:
                    which = "game server" if app_code is not None else "llama.cpp server"
                    code = app_code if app_code is not None else llm_code
                    self.log(f"The {which} stopped (exit {code}).")
                    self._stop_children()
                    self._set("failed", f"The {which} stopped unexpectedly (exit {code}).")
                    return
            self.start()
            return

    def request_restart(self) -> bool:
        """Ask the server to restart itself; kill it if it does not answer."""
        if self.attached:
            return False
        app = self._app
        if app is None or app.poll() is not None:
            self.start_async()
            return True
        try:
            self.restart_flag.write_text("window", encoding="utf-8")
        except OSError:
            pass
        try:
            req = urllib.request.Request(f"{self.url}/api/launcher/restart", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=3).close()
        except Exception:
            pass

        def ensure_exit() -> None:
            try:
                app.wait(timeout=12)
            except subprocess.TimeoutExpired:
                app.kill()

        threading.Thread(target=ensure_exit, daemon=True).start()
        return True

    def _stop_children(self) -> None:
        for proc in (self._app, self._llm):
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=8)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._app = None
        self._llm = None

    def stop(self) -> None:
        self._stopping = True
        with self._lock:
            self._stop_children()
            self._set("stopped")
