"""No console windows for the tools Mørkyn runs (Windows).

Mørkyn's window starts the game server without a console (pythonw +
CREATE_NO_WINDOW), so every console program the server runs - nvidia-smi on
each model call through app/gpu_gate.py, git, pip, powershell - got a console
of its own: with Windows Terminal as the default terminal, a terminal window
flashed open per call, many per turn with the narration pipeline on. Under the
old terminal launcher the children shared its console and nothing showed.

install() makes CREATE_NO_WINDOW the default for every subprocess started from
this process, unless the caller asked for a console (CREATE_NEW_CONSOLE) or
detached it (DETACHED_PROCESS). A gate, not a per-call fix: a spawn added later
cannot bring the flashing back. Windows that are meant to be seen (the Forge
launcher's Start-Process -WindowStyle Normal) open their own window and are
unaffected. Imported from app/__init__.py, so it covers the server, the
launcher, and tools that import the app.
"""
from __future__ import annotations

import os
import subprocess

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_CONSOLE = 0x00000010
_CONSOLE_CHOICES = CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_CONSOLE


def quiet_flags(creationflags: int) -> int:
    """creationflags with CREATE_NO_WINDOW added unless a console choice was already made."""
    flags = int(creationflags or 0)
    if flags & _CONSOLE_CHOICES:
        return flags
    return flags | CREATE_NO_WINDOW


def install() -> bool:
    """Patch subprocess.Popen once. Returns True when the guard is active."""
    if os.name != "nt":
        return False
    popen = subprocess.Popen
    if getattr(popen, "_morkyn_quiet", False):
        return True
    original_init = popen.__init__

    def __init__(self, *args, **kwargs):
        # creationflags is the 14th positional parameter; nobody passes it that way, but keep it intact if so.
        if len(args) < 14:
            kwargs["creationflags"] = quiet_flags(kwargs.get("creationflags", 0))
        original_init(self, *args, **kwargs)

    popen.__init__ = __init__
    popen._morkyn_quiet = True
    return True
