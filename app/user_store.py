"""Per-user settings and secrets, outside the game folder and outside every save.

Stell (2026-10-22): "the api key and settings dont save, we should be saving it
in a local encrypted file that only morkyn can read that we save in appdata or
somewhere else secure". The model settings lived in the game database, which is
per save and sits beside the executable, so a new game, another slot or a
rebuild lost them, and the key was stored there as plain text.

  * ``user_dir()``: %APPDATA%\\Morkyn on Windows, ~/Library/Application
    Support/Morkyn on macOS, $XDG_CONFIG_HOME/morkyn on Linux;
    ``MORKYN_USER_DIR`` overrides it (tests, portable use).
  * ``model_settings.json``: the model settings, no secrets in it.
  * ``secrets.bin``: named secrets (the API keys). On Windows the file is
    encrypted with DPAPI for the current Windows user (CryptProtectData, with
    Mørkyn's own entropy), so only that user's processes that know the
    entropy can read it. On macOS and Linux it is a file only the user may
    read (mode 600); there is no OS encryption call without extra packages,
    and ``protection()`` says which one is in use.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

_ENTROPY = b"Morkyn secrets v1"
_LOCK = threading.Lock()


def user_dir() -> Path:
    override = os.getenv("MORKYN_USER_DIR")
    if override:
        return Path(override)
    if "unittest" in sys.modules and not getattr(sys, "frozen", False):
        # A test that forgot to isolate never writes the player's real store:
        # test_model_limits once left a test key in %APPDATA%\Morkyn (2026-10-22).
        import tempfile

        return Path(tempfile.gettempdir()) / "morkyn-user-store-tests"
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Morkyn"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Morkyn"
    return Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "morkyn"


def _ensure_dir() -> Path:
    path = user_dir()
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


# --- settings ---------------------------------------------------------------

def settings_path(name: str = "model") -> Path:
    """``model_settings.json`` (the narrator's model) or ``speech_settings.json``."""
    return user_dir() / f"{name}_settings.json"


def load_settings(name: str = "model") -> dict[str, Any]:
    try:
        data = json.loads(settings_path(name).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings: dict[str, Any], name: str = "model") -> None:
    clean = {k: v for k, v in (settings or {}).items() if k != "api_key"}
    with _LOCK:
        _ensure_dir()
        target = settings_path(name)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(clean, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(target)


# --- secrets ----------------------------------------------------------------

def protection() -> str:
    """How secrets.bin is protected here: "dpapi" (Windows encryption) or "file-permissions"."""
    return "dpapi" if sys.platform == "win32" else "file-permissions"


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes) -> Blob:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    src, entropy, out = blob(data), blob(_ENTROPY), Blob()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = fn(ctypes.byref(src), "Morkyn", ctypes.byref(entropy), None, None, flags, ctypes.byref(out))
    else:
        ok = fn(ctypes.byref(src), None, ctypes.byref(entropy), None, None, flags, ctypes.byref(out))
    if not ok:
        raise OSError("Windows could not " + ("protect" if protect else "read") + " Mørkyn's secrets")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _secrets_path() -> Path:
    return user_dir() / "secrets.bin"


def _read_secrets() -> dict[str, str]:
    path = _secrets_path()
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    try:
        body = _dpapi(base64.b64decode(raw), protect=False) if protection() == "dpapi" else raw
        data = json.loads(body.decode("utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_secrets(secrets: dict[str, str]) -> None:
    body = json.dumps(secrets, ensure_ascii=True).encode("utf-8")
    raw = base64.b64encode(_dpapi(body, protect=True)) if protection() == "dpapi" else body
    target = _ensure_dir() / "secrets.bin"
    tmp = target.with_suffix(".bin.tmp")
    tmp.write_bytes(raw)
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    tmp.replace(target)


def get_secret(name: str) -> str:
    with _LOCK:
        return _read_secrets().get(str(name), "")


def set_secret(name: str, value: str) -> None:
    with _LOCK:
        secrets = _read_secrets()
        if value:
            secrets[str(name)] = str(value)
        else:
            secrets.pop(str(name), None)
        _write_secrets(secrets)
