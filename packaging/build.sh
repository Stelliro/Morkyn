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
"$python_bin" -m PyInstaller packaging/morkyn.spec --noconfirm --distpath dist --workpath packaging/build/work

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

case "$(uname -s)" in
  Darwin)
    archive="dist/Morkyn-${version}-macos.zip"
    rm -f "$archive"; (cd dist && zip -qr "../$archive" "Morkyn.app") ;;
  *)
    arch="$(uname -m)"
    archive="dist/Morkyn-${version}-linux-${arch}.tar.gz"
    rm -f "$archive"; tar -C dist -czf "$archive" Morkyn ;;
esac
echo "Done: $out"
echo "Archive: $archive"
