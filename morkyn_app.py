"""Mørkyn's own window: the launcher, the game, and its pop-out windows in one app.

    python morkyn_app.py                  start with the saved settings
    python morkyn_app.py lan 8088         reach / port for this start (saved, as before)
    python morkyn_app.py --browser        open the game in the system browser instead
    python morkyn_app.py --console        no window: run in this terminal, Ctrl+C stops

The game is still a website. While this runs, any browser on this PC can open
http://127.0.0.1:<port>/ (and phones on the LAN or VPN when Where says so); the
window is only the default way in. Settings live in the game's Settings dialog
and main menu. The window starts and restarts the server when they change.

This replaces the PowerShell Gatehouse (Morkyn.ps1), which still works, and is
the entry point a packaged .exe will build from.
"""
from __future__ import annotations

import base64
import io
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent  # data/ lives beside the exe, not in its temp unpack
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WEBVIEW_DIR = ROOT / "data" / "webview"
BG = "#0b0810"  # tokens.css --bg (dusk), so no white flash before the page paints

POPOUT_TITLES = {
    "player": "Player",
    "inventory": "Inventory",
    "bible": "World Bible",
    "search": "Search",
    "model": "Model",
    "npcs": "NPCs",
    "items": "Items",
    "places": "Places",
    "events": "Events",
    "talk": "Talk",
    "drafts": "Checks",
    "history": "History",
}


# The native title bar in the theme's colours (static/ui/frame.js sends the live
# ones; these are dusk, for the boot page and the moment before a page loads).
FRAME_DEFAULT = {"caption": "#08060b", "text": "#bfa0ee", "border": "#463a58"}
_FRAME_BY_WINDOW: dict[str, dict[str, str]] = {}


def _colorref(value: str) -> int | None:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        return None
    r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    return r | (g << 8) | (b << 16)  # COLORREF is 0x00BBGGRR


def paint_frame(win: Any, colors: dict[str, str] | None = None) -> None:
    """Windows 11: caption = the void, title = the thread, border = a dim thread line.

    Earlier Windows ignores the colour attributes and keeps its dark frame.
    """
    if os.name != "nt" or win is None:
        return
    chosen = {**FRAME_DEFAULT, **{k: v for k, v in (colors or {}).items() if _colorref(v) is not None}}
    _FRAME_BY_WINDOW[str(getattr(win, "uid", id(win)))] = chosen
    try:
        import ctypes

        hwnd = ctypes.c_void_p(int(win.native.Handle.ToInt64()))
        dwm = ctypes.windll.dwmapi
        attrs = (
            (20, 1),  # immersive dark mode: light caption-button glyphs
            (38, 1),  # no Mica backdrop under the caption
            (34, _colorref(chosen["border"])),
            (35, _colorref(chosen["caption"])),
            (36, _colorref(chosen["text"])),
        )
        for attr, value in attrs:
            number = ctypes.c_int(int(value))
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(number), ctypes.sizeof(number))
    except Exception:
        pass


def _keep_frame_painted() -> None:
    """pywebview resets the frame when the system switches light/dark; paint ours back on top."""
    try:
        from webview.platforms.winforms import BrowserView
    except Exception:
        return
    form_class = getattr(BrowserView, "BrowserForm", None)
    original = getattr(form_class, "update_title_bar_theme", None)
    if form_class is None or original is None:
        return

    def update_title_bar_theme(self: Any) -> None:
        original(self)
        win = getattr(self, "pywebview_window", None)
        paint_frame(win, _FRAME_BY_WINDOW.get(str(getattr(win, "uid", id(win)))))

    try:
        form_class.update_title_bar_theme = update_title_bar_theme
    except Exception:
        pass  # a .NET-derived class may refuse it; the frame then resets only on a system theme switch


def parse_args(argv: list[str]) -> dict[str, Any]:
    opts: dict[str, Any] = {"overrides": {}, "console": False, "window": None}
    for raw in argv:
        word = raw.strip().lower().lstrip("-")
        if word in {"console", "headless", "terminal"}:
            opts["console"] = True
        elif word == "browser":
            opts["window"] = "browser"
        elif word in {"app", "window"}:
            opts["window"] = "app"
        elif word in {"play", "preview"}:
            continue  # the Gatehouse's skip-the-menu word; there is no menu to skip now
        elif word in {"local", "machine"}:
            opts["overrides"]["launch_mode"] = "local"
        elif word in {"lan", "network", "web", "phone"}:
            opts["overrides"]["launch_mode"] = "lan"
        elif word in {"vpn", "tunnel", "tailscale", "wireguard", "zerotier"}:
            opts["overrides"]["launch_mode"] = "vpn"
        elif word.isdigit() and 2 <= len(word) <= 5:
            opts["overrides"]["app_port"] = int(word)
    return opts


def serve(host: str, port: str) -> int:
    """`--serve host port`: what a packaged build runs instead of `python -m uvicorn`."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=int(port))
    return 0


def prepare_assets() -> tuple[str, str | None]:
    """(logo data URI for the boot page, .ico path for the window). Built once from Media/."""
    WEBVIEW_DIR.mkdir(parents=True, exist_ok=True)
    thumb = WEBVIEW_DIR / "boot-logo.png"
    ico = WEBVIEW_DIR / "morkyn-mark.ico"
    source = ROOT / "Media" / "morkyn-logo.png"
    try:
        if source.is_file() and (not thumb.is_file() or thumb.stat().st_mtime < source.stat().st_mtime):
            from PIL import Image

            with Image.open(source) as image:
                small = image.convert("RGBA")
                small.thumbnail((192, 288))
                small.save(thumb, "PNG", optimize=True)
        if not ico.is_file():
            draw_mark().save(ico, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception:
        pass
    logo = ""
    if thumb.is_file():
        logo = "data:image/png;base64," + base64.b64encode(thumb.read_bytes()).decode("ascii")
    return logo, (str(ico) if ico.is_file() else None)


def draw_mark() -> Any:
    """The title-bar icon: the logo's Ø as one thread of light (ring + slash, no fill) with a faint halo.

    The key art itself turns to mud at 16 px, so the mark is drawn, in the
    thread colour, on transparency so it sits on the void caption.
    """
    from PIL import Image, ImageDraw, ImageFilter

    size = 256
    thread = (191, 160, 238, 255)  # tokens.css --thread (dusk)
    line = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(line)
    pen.ellipse((58, 34, 198, 222), outline=thread, width=26)
    pen.line((44, 236, 212, 20), fill=thread, width=24)
    halo = line.filter(ImageFilter.GaussianBlur(14))
    halo.putalpha(halo.getchannel("A").point(lambda a: a * 0.55))
    return Image.alpha_composite(halo, line)


def boot_html(logo: str) -> str:
    return (ROOT / "static" / "boot.html").read_text(encoding="utf-8").replace("__LOGO__", logo)


def open_folder(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - a local folder the user asked to see
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", str(path)])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# --- console mode ------------------------------------------------------------

def run_console(opts: dict[str, Any], open_browser: bool) -> int:
    from app.launcher import Supervisor

    sup = Supervisor(overrides=opts["overrides"])
    if hasattr(signal, "SIGTERM"):
        # `kill <pid>` would otherwise end this process without the finally
        # below, and on POSIX the servers would outlive it.
        def _terminate(_signum: int, _frame: Any) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, _terminate)
    try:
        if not sup.start():
            print("\n  Could not start:", sup.error)
            print("  Server log:", sup.server_log)
            return 1
        if open_browser:
            # Probing for a browser can block for seconds on a headless box.
            threading.Thread(target=webbrowser.open, args=(sup.url,), daemon=True).start()
        print(f"\n  Open {sup.url} in any browser. Ctrl+C stops Mørkyn.", flush=True)
        while sup.state not in {"failed", "stopped"}:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        sup.stop()
    return 0 if sup.state == "stopped" else 1


# --- window mode ---------------------------------------------------------------

class Shell:
    """Owns the windows. Supervisor callbacks arrive on its threads, so state moves are guarded."""

    def __init__(self, webview: Any, opts: dict[str, Any], window_mode: str) -> None:
        from app.launcher import Supervisor

        self.webview = webview
        self.window_mode = window_mode
        self.logo, self.icon = prepare_assets()
        self.main: Any = None
        self.popouts: dict[str, Any] = {}
        self.showing = "boot"  # boot | game
        self.browser_opened_for = ""
        self.quitting = False
        # The game window's frame colours; new pop-outs open in them before their page loads.
        self.frame_colors = dict(FRAME_DEFAULT)
        self._lock = threading.Lock()
        self.sup = Supervisor(on_change=self._on_change, overrides=opts["overrides"])
        self.api = ShellApi(self)

    # Supervisor -> windows
    def _on_change(self, sup: Any) -> None:
        if self.main is None or self.quitting:
            return
        with self._lock:
            if sup.state == "ready":
                if self.window_mode == "app" and self.showing != "game":
                    self.showing = "game"
                    self.main.load_url(sup.url + "/")
                elif self.window_mode == "browser" and self.browser_opened_for != sup.url:
                    self.browser_opened_for = sup.url
                    webbrowser.open(sup.url)
            elif sup.state in {"starting", "restarting", "failed"} and self.showing != "boot":
                self.showing = "boot"
                self._close_popouts()
                self.main.load_html(boot_html(self.logo))

    def status(self) -> dict[str, Any]:
        out = self.sup.status()
        out["window_mode"] = self.window_mode
        out["show_running"] = self.window_mode != "app" or self.showing == "boot"
        return out

    def open_popout(self, tab: str, title: str = "", width: int = 1100, height: int = 900) -> bool:
        key = str(tab or "player")
        win = self.popouts.get(key)
        if win is not None:
            try:
                win.restore()
                win.show()
                # Windows only raises a window the user did not click if it is on top for a moment.
                win.on_top = True
                win.on_top = False
                return True
            except Exception:
                self.popouts.pop(key, None)
        label = title or POPOUT_TITLES.get(key, key)
        url = f"{self.sup.url}/popout?tab={key}&native=1"
        win = self.webview.create_window(
            f"Mørkyn — {label}",
            url,
            width=max(560, int(width or 1100)),
            height=max(480, int(height or 900)),
            min_size=(480, 360),
            background_color=BG,
            text_select=True,
            js_api=self.api,  # its Close button calls close_popout
        )
        self.popouts[key] = win

        def closed() -> None:
            if self.popouts.get(key) is win:
                self.popouts.pop(key, None)
            if self.main is not None and self.showing == "game" and not self.quitting:
                try:
                    self.main.evaluate_js(f"window.__morkynNativePopoutClosed && window.__morkynNativePopoutClosed({key!r})")
                except Exception:
                    pass

        win.events.closed += closed
        win.events.shown += lambda: paint_frame(win, self.frame_colors)
        return True

    def set_frame_colors(self, frame_id: str, colors: dict[str, str]) -> bool:
        key = str(frame_id or "main")
        win = self.main if key == "main" else self.popouts.get(key)
        if win is None or not isinstance(colors, dict):
            return False
        if key == "main":
            self.frame_colors = {**FRAME_DEFAULT, **{k: v for k, v in colors.items() if _colorref(v) is not None}}
        paint_frame(win, colors)
        return True

    def _close_popouts(self) -> None:
        for key, win in list(self.popouts.items()):
            self.popouts.pop(key, None)
            try:
                win.destroy()
            except Exception:
                pass

    def quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        self._close_popouts()
        threading.Thread(target=self.sup.stop, daemon=True).start()
        try:
            self.main.destroy()
        except Exception:
            pass

    def run(self) -> int:
        self.main = self.webview.create_window(
            "Mørkyn",
            html=boot_html(self.logo),
            js_api=self.api,
            width=1280 if self.window_mode == "app" else 720,
            height=800 if self.window_mode == "app" else 620,
            min_size=(960, 640) if self.window_mode == "app" else (520, 420),
            background_color=BG,
            text_select=True,
        )

        def on_closed() -> None:
            self.quitting = True
            self._close_popouts()
            self.sup.stop()

        self.main.events.closed += on_closed
        self.main.events.shown += lambda: paint_frame(self.main, self.frame_colors)

        def started() -> None:
            if self.window_mode == "app":
                try:
                    self.main.maximize()
                except Exception:
                    pass
            self.sup.start_async()

        self.webview.start(
            started,
            private_mode=False,  # keep localStorage (theme, layout, tutorial flags) between launches
            storage_path=str(WEBVIEW_DIR / "profile"),
            icon=self.icon,
        )
        self.sup.stop()
        return 0


class ShellApi:
    """What pages in the window can call as window.pywebview.api.*. Keep internals private (_)."""

    def __init__(self, shell: Shell) -> None:
        self._shell = shell

    def status(self) -> dict[str, Any]:
        return self._shell.status()

    def is_app(self) -> bool:
        return True

    def open_popout(self, tab: str, title: str = "", width: int = 1100, height: int = 900) -> bool:
        return self._shell.open_popout(tab, title, width, height)

    def set_frame_colors(self, frame_id: str, colors: dict[str, str]) -> bool:
        return self._shell.set_frame_colors(frame_id, colors)

    def popouts(self) -> list[str]:
        return list(self._shell.popouts)

    def close_popout(self, tab: str) -> bool:
        win = self._shell.popouts.pop(str(tab), None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        return win is not None

    def restart(self) -> bool:
        return self._shell.sup.request_restart()

    def retry(self, prefs: dict[str, Any] | None = None) -> bool:
        from app.launcher_prefs import save_prefs

        if isinstance(prefs, dict) and prefs:
            save_prefs(prefs)
        if self._shell.sup.state in {"failed", "stopped", "idle"}:
            self._shell.sup.start_async()
        return True

    def open_logs(self) -> bool:
        from app.launcher import LOG_DIR

        open_folder(LOG_DIR)
        return True

    def open_in_browser(self) -> bool:
        if self._shell.sup.url:
            webbrowser.open(self._shell.sup.url)
        return True

    def open_game_here(self) -> bool:
        shell = self._shell
        if shell.sup.state == "ready":
            shell.window_mode = "app"
            shell.showing = "game"
            try:
                shell.main.resize(1280, 800)
            except Exception:
                pass
            shell.main.load_url(shell.sup.url + "/")
        return True

    def open_external(self, url: str) -> bool:
        if str(url).startswith(("http://", "https://")):
            webbrowser.open(str(url))
            return True
        return False

    def quit(self) -> bool:
        threading.Thread(target=self._shell.quit, daemon=True).start()
        return True


def _keep_paste_working(webview: Any) -> None:
    """The system web view turns off Ctrl+V and the context menu unless debug is on. Keep them; leave dev tools off."""
    try:
        from webview.platforms.edgechromium import EdgeChrome
    except Exception:
        return

    def enable(sender: Any) -> None:
        try:
            settings = sender.CoreWebView2.Settings
            settings.AreBrowserAcceleratorKeysEnabled = True
            settings.AreDefaultContextMenusEnabled = True
            settings.AreDevToolsEnabled = bool(os.getenv("MORKYN_DEVTOOLS"))
        except Exception:
            pass

    original_ready = EdgeChrome.on_webview_ready
    original_nav = EdgeChrome.on_navigation_completed

    def on_webview_ready(self: Any, sender: Any, args: Any) -> None:
        original_ready(self, sender, args)
        enable(sender)

    def on_navigation_completed(self: Any, sender: Any, args: Any) -> None:
        original_nav(self, sender, args)
        enable(sender)

    EdgeChrome.on_webview_ready = on_webview_ready
    EdgeChrome.on_navigation_completed = on_navigation_completed


def run_module(module: str, args: list[str]) -> int:
    """`--run-module name args`: what a packaged build runs instead of `python -m name`.

    The launcher starts the llama.cpp server and probes a model's limits this
    way (app.launcher.module_command); a checkout still uses the interpreter.
    """
    import runpy

    sys.argv = [module, *args]
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else (0 if code is None else 1)
    return 0


def run_code(code: str) -> int:
    """`--run-code "..."`: what a packaged build runs instead of `python -c`."""
    exec(compile(code, "<morkyn --run-code>", "exec"), {"__name__": "__main__"})
    return 0


def main(argv: list[str]) -> int:
    # A console build writes "Mørkyn" to a cp1252 console as "M�rkyn"; the
    # streams take UTF-8 with replacement instead of raising or mangling.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # The downloaded dependency packs (llama-cpp-python and the like) go on the
    # path before anything imports them; every process of the app runs this.
    try:
        from app.runtime_packs import activate

        activate()
    except Exception:
        pass
    if len(argv) >= 3 and argv[0] == "--serve":
        return serve(argv[1], argv[2])
    if len(argv) >= 2 and argv[0] == "--run-module":
        return run_module(argv[1], argv[2:])
    if len(argv) >= 2 and argv[0] == "--run-code":
        return run_code(argv[1])
    # The version the player chose runs instead of this build (app.versions):
    # a packaged build only, and never for the internal subcommands above.
    try:
        from app.versions import hand_over

        handed = hand_over(argv)
    except Exception:
        handed = None
    if handed is not None:
        return handed
    opts = parse_args(argv)
    from app.launcher_prefs import load_prefs

    window_mode = opts["window"] or load_prefs()["window_mode"]
    if opts["console"]:
        return run_console(opts, open_browser=window_mode != "none")
    try:
        import webview
    except ImportError:
        if sys.stdout is not None:
            print("  The Mørkyn window needs pywebview:  python -m pip install pywebview")
            print("  Running in this terminal and opening your browser instead.\n")
        return run_console(opts, open_browser=window_mode != "none")
    _keep_paste_working(webview)
    _keep_frame_painted()
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    debug_port = os.getenv("MORKYN_REMOTE_DEBUG_PORT", "").strip()
    if debug_port.isdigit():
        # For UI tests: Playwright attaches over CDP. Off unless asked for.
        webview.settings["REMOTE_DEBUGGING_PORT"] = int(debug_port)
    return Shell(webview, opts, window_mode).run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
