#!/bin/sh
# Mørkyn's launcher for an installed build (.deb, .rpm, AUR, install.sh).
# The build itself is read-only, so data/, runtime/ and versions/ live in the
# player's home; every install format shares it. @APP_DIR@ is set when packaged.
export MORKYN_HOME="${MORKYN_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/morkyn}"
mkdir -p "$MORKYN_HOME/data"

# Opened from the menu (no terminal): run inside one, so closing the terminal
# closes the whole game; closing the window alone left the server running
# (Stell, 2026-10-23: "we just need a terminal we can close"). The menu entry's
# Terminal=true is up to each desktop, so the script does it.
# MORKYN_NO_TERMINAL=1 skips this; with no terminal found it runs as before.
if [ ! -t 0 ] && [ -z "$MORKYN_IN_TERMINAL" ] && [ -z "$MORKYN_NO_TERMINAL" ]; then
  export MORKYN_IN_TERMINAL=1
  for term in x-terminal-emulator cosmic-term gnome-terminal konsole xfce4-terminal kitty alacritty foot xterm; do
    command -v "$term" >/dev/null 2>&1 || continue
    case "$term" in
      gnome-terminal) exec "$term" -- "$0" "$@" ;;
      xfce4-terminal) exec "$term" -x "$0" "$@" ;;
      kitty|foot) exec "$term" "$0" "$@" ;;
      *) exec "$term" -e "$0" "$@" ;;
    esac
  done
fi
exec "@APP_DIR@/Morkyn" "$@"
