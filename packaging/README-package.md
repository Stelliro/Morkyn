# Mørkyn, packaged

This folder is Mørkyn ready to run: no Python, no pip.

- **Windows:** double-click `Morkyn.exe`. The game opens in its own window; any browser on this
  PC can also open the address it shows (and phones on your network when *Where* says so).
- **macOS:** open `Morkyn.app`.
- **Linux:** run `./Morkyn`. It opens the game in your browser (the native window needs
  PyGObject and WebKit2GTK, which most distributions ship as `python3-gi gir1.2-webkit2-4.1`).

Options: `Morkyn.exe --browser` (system browser instead of the window), `--console` (no window,
run in the terminal), `lan` / `vpn` / a port number (reach and port for this start).

Everything you make lives in `data/` beside the executable: saves, settings, logs, portraits and
downloaded voices. Back that folder up, or move it to a new build, and your games come with it.

A local model (a `.gguf` file) is **not** in this package. Put yours anywhere and point the
Model settings at it, or use a cloud API from the same screen. The first start with a local
model takes a while to load it.

Updates: download the next build and copy your `data/` folder across. The in-game updater only
works from a git checkout.
