#!/bin/sh
# Mørkyn's launcher for an installed build (.deb, .rpm, AUR, install.sh).
# The build itself is read-only, so data/, runtime/ and versions/ live in the
# player's home; every install format shares it. @APP_DIR@ is set when packaged.
export MORKYN_HOME="${MORKYN_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/morkyn}"
mkdir -p "$MORKYN_HOME/data"
exec "@APP_DIR@/Morkyn" "$@"
