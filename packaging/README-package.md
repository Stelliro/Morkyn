# Mørkyn, packaged

This folder is Mørkyn ready to run: no Python, no pip.

- **Windows:** double-click `Morkyn.exe`. The game opens in its own window; any browser on this
  PC can also open the address it shows (and phones on your network when *Where* says so).
- **macOS:** open `Morkyn.app`.
- **Linux:** run `./Morkyn`. It opens the game in your browser (the native window needs
  PyGObject and WebKit2GTK, which most distributions ship as `python3-gi gir1.2-webkit2-4.1`).
  Run `./install.sh` to install it for your user with a menu entry (`./install.sh --uninstall`
  removes it). The installed game, like the `.deb`, `.rpm` and `.AppImage`, keeps your saves
  and engine packs in `~/.local/share/morkyn` instead of beside the program.

Options: `Morkyn.exe --browser` (system browser instead of the window), `--console` (no window,
run in the terminal), `lan` / `vpn` / a port number (reach and port for this start).

Everything you make lives in `data/` beside the executable: saves, settings, logs, portraits and
downloaded voices. Back that folder up, or move it to a new build, and your games come with it.

**The local engine** (llama.cpp) is not in this package either: the first start looks at your
GPU and downloads the engine pack that fits it (NVIDIA: CUDA; Apple Silicon: Metal; AMD or
Intel: Vulkan; otherwise CPU) into `runtime/` beside the program. Settings → Updates (the
"Versions & engine" panel) shows what was picked; there you can choose another pack, point at a
build of your own, or run without a local engine and use a cloud API. A model (a `.gguf` file)
is not included: put yours anywhere and point the Model settings at it.

**Versions:** the same panel lists every release. Install any one, newer or older, and choose
it; it starts next time. Every version shares your `data/` folder and the engine packs.
