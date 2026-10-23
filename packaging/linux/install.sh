#!/usr/bin/env bash
# Install Mørkyn from the .tar.gz for this user only (no root):
#
#   ./install.sh               install or update, from the extracted folder
#   ./install.sh --uninstall   remove the program (your saves are kept)
#
# The program goes to ~/.local/opt/morkyn, the `morkyn` command to ~/.local/bin,
# and a menu entry and icon to ~/.local/share. Saves, settings and engine packs
# live in ~/.local/share/morkyn, shared with the .deb, .rpm and AppImage.
# Running ./Morkyn from the folder without installing still works: then data/
# stays beside it.
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
app_dir="$HOME/.local/opt/morkyn"
bin="$HOME/.local/bin/morkyn"
desktop="$data_home/applications/morkyn.desktop"
icon="$data_home/icons/hicolor/256x256/apps/morkyn.png"
home="$data_home/morkyn"

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$app_dir"
  rm -f "$bin" "$desktop" "$icon"
  command -v update-desktop-database >/dev/null && update-desktop-database "$data_home/applications" || true
  echo "Removed Mørkyn. Your saves and settings are still in $home (delete it to remove them)."
  exit 0
fi

[ -x "$src/Morkyn" ] || { echo "Run this from the extracted Morkyn folder." >&2; exit 1; }

rm -rf "$app_dir"
mkdir -p "$app_dir" "$(dirname "$bin")" "$(dirname "$desktop")" "$(dirname "$icon")" "$home/data"
for item in "$src"/* "$src"/.[!.]*; do
  [ -e "$item" ] || continue
  case "$(basename "$item")" in data|runtime|versions) continue ;; esac
  cp -R "$item" "$app_dir/"
done

# Games played from the folder before installing come along, once.
if [ -d "$src/data" ] && [ -z "$(ls -A "$home/data" 2>/dev/null)" ] && [ -n "$(ls -A "$src/data" 2>/dev/null)" ]; then
  cp -R "$src/data/." "$home/data/"
  echo "Copied the saves in $src/data to $home/data."
fi

sed "s|@APP_DIR@|$app_dir|" "$src/linux/morkyn.sh" > "$bin"
chmod 755 "$bin"
# The full path, as the desktop session may not have ~/.local/bin on its PATH.
sed "s|^Exec=morkyn|Exec=$bin|" "$src/linux/morkyn.desktop" > "$desktop"
cp -f "$src/linux/morkyn.png" "$icon"
command -v update-desktop-database >/dev/null && update-desktop-database "$data_home/applications" || true

echo "Installed Mørkyn. Start it from your app menu or with: morkyn"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "(~/.local/bin is not on your PATH; the menu entry still works.)" ;; esac
