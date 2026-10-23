#!/usr/bin/env bash
# Build Mørkyn's packaged folder on Linux or macOS and archive it.
#
#   bash packaging/build.sh [--console] [--python /path/to/python]
#
# Needs: the repo's requirements installed (on Linux/macOS use the CPU wheel
# index for llama-cpp-python: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu),
# plus pyinstaller sse-starlette starlette-context pydantic-settings.
# On macOS pywebview gives the native window; on Linux the build opens the
# game in the browser unless PyGObject/WebKit2 are installed.
# Result: dist/Morkyn/ (run ./Morkyn) or dist/Morkyn.app on macOS, and a tar.gz / zip.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

python_bin="${MORKYN_PYTHON:-}"
console=0
while [ $# -gt 0 ]; do
  case "$1" in
    --console) console=1 ;;
    --python) shift; python_bin="$1" ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
if [ -z "$python_bin" ]; then
  if [ -x ".venv/bin/python" ]; then python_bin=".venv/bin/python"; else python_bin="python3"; fi
fi
version="$(sed -n 's/^APP_VERSION = "V\{0,1\}\([^"]*\)"/\1/p' app/main.py | head -1)"
echo "Building Morkyn $version with $python_bin"

"$python_bin" -m pip install --quiet pyinstaller sse-starlette starlette-context pydantic-settings
if [ "$console" = "1" ]; then export MORKYN_BUILD_CONSOLE=1; else unset MORKYN_BUILD_CONSOLE || true; fi

# PyInstaller deletes its output folder whole. The player's own folders beside
# the exe (data, runtime, versions) wait in dist/.keep and go back afterwards,
# also when the build fails (build.ps1 does the same; a Linux rebuild wiped a
# played copy's data/ and its 4.6 GB runtime/ on 2026-10-23).
keep="dist/.keep"
restore_kept() {
  [ -d "$keep" ] || return 0
  local place name
  for place in "$keep"/*; do
    [ -d "$place" ] || continue
    dest="dist/$(basename "$place" | tr '+' '/')"
    mkdir -p "$dest"
    for name in data runtime versions; do
      [ -e "$place/$name" ] || continue
      rm -rf "${dest:?}/$name"
      mv "$place/$name" "$dest/$name"
    done
  done
  rm -rf "$keep"
}
restore_kept  # a run that was killed before it could put them back
for place in Morkyn Morkyn.app/Contents/MacOS; do
  for name in data runtime versions; do
    [ -e "dist/$place/$name" ] || continue
    mkdir -p "$keep/$(echo "$place" | tr '/' '+')"
    mv "dist/$place/$name" "$keep/$(echo "$place" | tr '/' '+')/$name"
  done
done
trap restore_kept EXIT
"$python_bin" -m PyInstaller packaging/morkyn.spec --noconfirm --distpath dist --workpath packaging/build/work
restore_kept
trap - EXIT

out="dist/Morkyn"
if [ "$(uname -s)" = "Darwin" ] && [ -d "dist/Morkyn.app" ]; then
  out="dist/Morkyn.app/Contents/MacOS"
fi
for folder in static content config Media; do
  rm -rf "$out/$folder"
  cp -R "$folder" "$out/$folder"
done
for file in README.md LICENSE.md PRIVACY_POLICY.md CHANGELOG.md; do cp -f "$file" "$out/$file"; done
cp -f packaging/README-package.md "$out/README-package.md"
mkdir -p "$out/data"
if [ "$(uname -s)" != "Darwin" ]; then
  # The tarball's own installer (./install.sh) and the pieces it puts in place.
  rm -rf "$out/linux"
  mkdir -p "$out/linux"
  cp -f packaging/linux/morkyn.sh packaging/linux/morkyn.desktop "$out/linux/"
  "$python_bin" packaging/linux/make_icon.py "$out/linux/morkyn.png"
  cp -f packaging/linux/install.sh "$out/install.sh"
  chmod 755 "$out/install.sh"
fi

# A rebuild keeps the player's data/, runtime/ and versions/ beside the exe;
# the archive takes none of them (data/ goes in empty).
case "$(uname -s)" in
  Darwin)
    archive="dist/Morkyn-${version}-macos.zip"
    mac="Morkyn.app/Contents/MacOS"
    rm -f "$archive"; (cd dist && zip -qr "../$archive" "Morkyn.app" \
      -x "$mac/data/?*" "$mac/runtime/*" "$mac/versions/*") ;;
  *)
    arch="$(uname -m)"
    archive="dist/Morkyn-${version}-linux-${arch}.tar.gz"
    rm -f "$archive"; tar -C dist -czf "$archive" \
      --exclude="Morkyn/data/?*" --exclude=Morkyn/runtime --exclude=Morkyn/versions Morkyn ;;
esac
echo "Done: $out"
echo "Archive: $archive"
