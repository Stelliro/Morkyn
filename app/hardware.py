"""What this machine can run a local model on: the GPUs, and the engine pack that fits.

Stell (2026-10-19): "we need hardware specific auto installs as well as an area
the user can select what they want and if they want to use a custom one."
The detection is engine-only and never raises; a miss means "cpu".
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

VENDOR_IDS = {"10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel", "106b": "apple"}


def _run(cmd: list[str], timeout: int = 8) -> str:
    try:
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=flags)
        return out.stdout or ""
    except Exception:
        return ""


def _vendor_of(name: str) -> str:
    low = str(name or "").lower()
    if "nvidia" in low or "geforce" in low or "quadro" in low or "rtx" in low or "tesla" in low:
        return "nvidia"
    if "amd" in low or "radeon" in low or "advanced micro" in low:
        return "amd"
    if "intel" in low or "arc" in low or "iris" in low or "uhd" in low:
        return "intel"
    if "apple" in low:
        return "apple"
    return "other"


def gpus() -> list[dict[str, str]]:
    """[{vendor, name}] of the display adapters, best effort, no duplicates."""
    found: list[dict[str, str]] = []
    if sys.platform == "win32":
        text = _run(["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"])
        for line in text.splitlines():
            if line.strip():
                found.append({"vendor": _vendor_of(line), "name": line.strip()})
    elif sys.platform == "darwin":
        machine = platform.machine().lower()
        if machine in {"arm64", "aarch64"}:
            found.append({"vendor": "apple", "name": f"Apple Silicon ({machine})"})
        else:
            text = _run(["system_profiler", "SPDisplaysDataType"], timeout=20)
            for m in re.finditer(r"Chipset Model:\s*(.+)", text):
                found.append({"vendor": _vendor_of(m.group(1)), "name": m.group(1).strip()})
    else:
        drm = Path("/sys/class/drm")
        if drm.is_dir():
            for card in sorted(drm.glob("card[0-9]*")):
                if "-" in card.name:
                    continue
                vendor_file = card / "device" / "vendor"
                try:
                    vid = vendor_file.read_text().strip().lower().replace("0x", "")
                except Exception:
                    continue
                vendor = VENDOR_IDS.get(vid, "other")
                found.append({"vendor": vendor, "name": f"{vendor} GPU ({card.name})"})
        if not found and shutil.which("lspci"):
            for line in _run(["lspci"]).splitlines():
                if re.search(r"VGA|3D|Display", line):
                    name = line.split(":", 2)[-1].strip()
                    found.append({"vendor": _vendor_of(name), "name": name})
    if not any(g["vendor"] == "nvidia" for g in found) and shutil.which("nvidia-smi"):
        text = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        for line in text.splitlines():
            if line.strip():
                found.append({"vendor": "nvidia", "name": line.strip()})
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for g in found:
        key = g["name"].lower()
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out


def recommended_pack(adapters: list[dict[str, str]] | None = None) -> tuple[str, str]:
    """(pack id, why) for this machine: cuda for NVIDIA, metal on Apple Silicon, vulkan for AMD/Intel, else cpu."""
    adapters = gpus() if adapters is None else adapters
    vendors = [g["vendor"] for g in adapters]
    os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    if os_name == "macos":
        if "apple" in vendors or platform.machine().lower() in {"arm64", "aarch64"}:
            return "llama-cpp-metal", "Apple Silicon: the Metal build uses the GPU"
        return "llama-cpp-cpu", "Intel Mac: no GPU build; the CPU build"
    if "nvidia" in vendors:
        return "llama-cpp-cuda", "NVIDIA GPU: the CUDA build uses it"
    if "amd" in vendors or "intel" in vendors:
        return "llama-cpp-vulkan", "AMD or Intel GPU: the Vulkan build uses it"
    return "llama-cpp-cpu", "No GPU found: the CPU build"


def summary() -> dict[str, Any]:
    adapters = gpus()
    pack, why = recommended_pack(adapters)
    return {
        "os": {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux"),
        "arch": platform.machine().lower(),
        "gpus": adapters,
        "recommended": pack,
        "why": why,
    }
