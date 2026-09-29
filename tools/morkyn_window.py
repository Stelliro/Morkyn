"""Open Morkyn in its own window.

The game is still a normal website. Any browser can open http://127.0.0.1:8000/
and use the same pages. This window is only another way in: no tabs, no
address bar, and it does not replace LibreWolf or Firefox.

Start the API first, then run: python tools/morkyn_window.py
"""

from __future__ import annotations

import sys
import urllib.request


URL = "http://127.0.0.1:8000/"


def server_up() -> bool:
    try:
        with urllib.request.urlopen(URL + "api/model-config", timeout=2) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def main() -> int:
    if not server_up():
        print("Morkyn's API is not running. Start it, then open this window again.")
        print("A normal browser can use the same address:", URL)
        return 1
    try:
        import webview
        from webview.platforms.edgechromium import EdgeChrome
    except ImportError:
        print("The window needs pywebview: python -m pip install pywebview")
        print("Until then, open", URL, "in any browser.")
        return 1

    # The system web view turns off Ctrl+V unless debug tools are on.
    # Keep paste, copy, cut, and undo. Leave the dev tools off.
    def enable_paste(sender) -> None:
        try:
            settings = sender.CoreWebView2.Settings
            settings.AreBrowserAcceleratorKeysEnabled = True
            settings.AreDefaultContextMenusEnabled = True
            settings.AreDevToolsEnabled = False
        except Exception:
            pass

    original_ready = EdgeChrome.on_webview_ready
    original_nav = EdgeChrome.on_navigation_completed

    def on_webview_ready(self, sender, args):
        original_ready(self, sender, args)
        enable_paste(sender)

    def on_navigation_completed(self, sender, args):
        original_nav(self, sender, args)
        enable_paste(sender)

    EdgeChrome.on_webview_ready = on_webview_ready
    EdgeChrome.on_navigation_completed = on_navigation_completed

    window = webview.create_window(
        "Morkyn",
        URL,
        width=1280,
        height=800,
        min_size=(960, 640),
        text_select=True,
    )

    def show(win) -> None:
        try:
            win.maximize()
        except Exception:
            pass

    webview.start(show, window)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
