#!/usr/bin/env bash
# Build Mørkyn's Linux packages from the packaged folder (dist/Morkyn, made by
# packaging/build.sh):
#
#   bash packaging/build_linux.sh [--rebuild] [tar] [deb] [rpm] [appimage] [aur]
#
# No format named builds them all. --rebuild (or no dist/Morkyn yet) runs
# packaging/build.sh first.
#
#   tar       dist/Morkyn-<v>-linux-<arch>.tar.gz   run ./Morkyn, or ./install.sh for this user
#   deb       dist/morkyn_<v>_<arch>.deb            Debian, Ubuntu, Mint, Pop!_OS
#   rpm       dist/morkyn-<v>-1.<arch>.rpm          Fedora, openSUSE, RHEL (needs rpmbuild:
#                                                   the `rpm` package on Debian/Ubuntu)
#   appimage  dist/Morkyn-<v>-<arch>.AppImage       any distro; appimagetool is fetched
#   aur       dist/aur/PKGBUILD + .SRCINFO          Arch: morkyn-bin, built from the
#                                                   release tarball of the same version
#
# Installed formats put the build in /opt/morkyn (the AppImage keeps it inside)
# and the player's data/, runtime/ and versions/ in ~/.local/share/morkyn
# (packaging/linux/morkyn.sh, AppRun). The player's folders beside dist/Morkyn's
# exe are never packed.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

rebuild=0
formats=()
for arg in "$@"; do
  case "$arg" in
    --rebuild) rebuild=1 ;;
    tar|deb|rpm|appimage|aur) formats+=("$arg") ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
[ ${#formats[@]} -gt 0 ] || formats=(tar deb rpm appimage aur)
wants() { local f; for f in "${formats[@]}"; do [ "$f" = "$1" ] && return 0; done; return 1; }

if [ "$rebuild" = "1" ] || [ ! -x dist/Morkyn/Morkyn ]; then
  bash packaging/build.sh
fi
if [ -x ".venv/bin/python" ]; then python_bin=".venv/bin/python"; else python_bin="python3"; fi

version="$(sed -n 's/^APP_VERSION = "V\{0,1\}\([^"]*\)"/\1/p' app/main.py | head -1)"
machine="$(uname -m)"
glibc="$(getconf GNU_LIBC_VERSION | cut -d' ' -f2)"
tarball="dist/Morkyn-${version}-linux-${machine}.tar.gz"
work="packaging/build/linux"
summary="A dark-fantasy RPG narrated by a local or cloud language model"
homepage="https://github.com/Stelliro/Morkyn"
maintainer="Stelliro <Stelliro@users.noreply.github.com>"
rm -rf "$work"
mkdir -p "$work"
built=()

# The build without the player's folders a run from dist/ leaves beside the exe,
# and without the tarball's own installer (install.sh, linux/).
copy_app() {
  mkdir -p "$1"
  local item
  for item in dist/Morkyn/* dist/Morkyn/.[!.]*; do
    [ -e "$item" ] || continue
    case "$(basename "$item")" in data|runtime|versions|install.sh|linux) continue ;; esac
    cp -R "$item" "$1/"
  done
}

# /opt/morkyn + /usr/bin/morkyn + the menu entry and icon, for deb and rpm.
stage_system() {
  local stage="$1"
  copy_app "$stage/opt/morkyn"
  mkdir -p "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
  sed "s|@APP_DIR@|/opt/morkyn|" packaging/linux/morkyn.sh > "$stage/usr/bin/morkyn"
  chmod 755 "$stage/usr/bin/morkyn"
  cp packaging/linux/morkyn.desktop "$stage/usr/share/applications/morkyn.desktop"
  "$python_bin" packaging/linux/make_icon.py "$stage/usr/share/icons/hicolor/256x256/apps/morkyn.png"
}

if wants tar || wants aur; then
  if [ "$rebuild" = "0" ] || [ ! -f "$tarball" ]; then
    rm -f "$tarball"
    tar -C dist -czf "$tarball" \
      --exclude="Morkyn/data/?*" --exclude=Morkyn/runtime --exclude=Morkyn/versions Morkyn
  fi
  built+=("$tarball")
fi

if wants deb; then
  deb_version="${version//-/\~}"
  arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
  stage="$work/deb"
  stage_system "$stage"
  mkdir -p "$stage/DEBIAN"
  cat > "$stage/DEBIAN/control" <<EOF
Package: morkyn
Version: $deb_version
Section: games
Priority: optional
Architecture: $arch
Depends: libc6 (>= $glibc), xdg-utils
Installed-Size: $(du -sk "$stage" | cut -f1)
Maintainer: $maintainer
Homepage: $homepage
Description: $summary
 Saves, settings and the downloaded engine packs are kept in
 ~/.local/share/morkyn, so updating or removing the package keeps them.
EOF
  out="dist/morkyn_${deb_version}_${arch}.deb"
  fakeroot dpkg-deb --build -Zxz "$stage" "$out" >/dev/null
  built+=("$out")
fi

if wants rpm; then
  if ! command -v rpmbuild >/dev/null; then
    echo "rpm: skipped, rpmbuild is not installed (Debian/Ubuntu: sudo apt install rpm)" >&2
  else
    rpm_version="${version%%-*}"
    rpm_release="1"
    case "$version" in *-*) rpm_release="0.${version#*-}"; rpm_release="${rpm_release//-/.}" ;; esac
    top="$(pwd)/$work/rpm"
    stage="$top/stage"
    stage_system "$stage"
    mkdir -p "$top/SPECS" "$top/RPMS"
    # A PyInstaller build breaks when stripped, and its bundled libraries are
    # not the system's: no strip, no debuginfo, no automatic requires.
    cat > "$top/SPECS/morkyn.spec" <<EOF
%global debug_package %{nil}
%global __os_install_post %{nil}
%global _build_id_links none
%define __strip /bin/true
Name: morkyn
Version: $rpm_version
Release: $rpm_release
Summary: $summary
License: Proprietary
URL: $homepage
AutoReqProv: no
Requires: glibc >= $glibc
Requires: xdg-utils

%description
Saves, settings and the downloaded engine packs are kept in
~/.local/share/morkyn, so updating or removing the package keeps them.

%install
cp -a "$stage/." "%{buildroot}/"

%files
/opt/morkyn
/usr/bin/morkyn
/usr/share/applications/morkyn.desktop
/usr/share/icons/hicolor/256x256/apps/morkyn.png
EOF
    rpmbuild --quiet -bb --define "_topdir $top" "$top/SPECS/morkyn.spec"
    for rpm_file in "$top"/RPMS/*/*.rpm; do
      cp -f "$rpm_file" dist/
      built+=("dist/$(basename "$rpm_file")")
    done
  fi
fi

if wants appimage; then
  tool="packaging/build/tools/appimagetool-${machine}.AppImage"
  if [ ! -x "$tool" ]; then
    mkdir -p "$(dirname "$tool")"
    curl -sSfL -o "$tool" "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-${machine}.AppImage"
    chmod 755 "$tool"
  fi
  appdir="$work/Morkyn.AppDir"
  copy_app "$appdir/usr/lib/morkyn"
  mkdir -p "$appdir/usr/share/applications" "$appdir/usr/share/icons/hicolor/256x256/apps"
  cp packaging/linux/AppRun "$appdir/AppRun"
  chmod 755 "$appdir/AppRun"
  cp packaging/linux/morkyn.desktop "$appdir/morkyn.desktop"
  cp packaging/linux/morkyn.desktop "$appdir/usr/share/applications/morkyn.desktop"
  "$python_bin" packaging/linux/make_icon.py "$appdir/morkyn.png"
  cp "$appdir/morkyn.png" "$appdir/usr/share/icons/hicolor/256x256/apps/morkyn.png"
  ln -sf morkyn.png "$appdir/.DirIcon"
  out="dist/Morkyn-${version}-${machine}.AppImage"
  rm -f "$out"
  # Extract-and-run: no FUSE needed on the build machine (CI runners lack it).
  APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$machine" "$tool" --no-appstream "$appdir" "$out" >/dev/null
  built+=("$out")
fi

if wants aur; then
  # morkyn-bin: the AUR builds from the release tarball, so the sums are this one's.
  aur_version="${version//-/_}"
  sum="$(sha256sum "$tarball" | cut -d' ' -f1)"
  mkdir -p dist/aur
  cp packaging/linux/morkyn.sh packaging/linux/morkyn.desktop dist/aur/
  "$python_bin" packaging/linux/make_icon.py dist/aur/morkyn.png
  sums=()
  for f in morkyn.sh morkyn.desktop morkyn.png; do sums+=("$(sha256sum "dist/aur/$f" | cut -d' ' -f1)"); done
  cat > dist/aur/PKGBUILD <<EOF
# Maintainer: $maintainer
pkgname=morkyn-bin
pkgver=$aur_version
pkgrel=1
pkgdesc="$summary"
arch=('x86_64')
url="$homepage"
license=('custom')
depends=('glibc' 'xdg-utils')
provides=('morkyn')
conflicts=('morkyn')
options=('!strip' '!debug')
source=("$homepage/releases/download/v$version/Morkyn-$version-linux-x86_64.tar.gz"
        'morkyn.sh' 'morkyn.desktop' 'morkyn.png')
sha256sums=('$sum'
            '${sums[0]}'
            '${sums[1]}'
            '${sums[2]}')

package() {
  install -d "\$pkgdir/opt/morkyn"
  cp -a "\$srcdir/Morkyn/." "\$pkgdir/opt/morkyn/"
  rm -rf "\$pkgdir/opt/morkyn/data" "\$pkgdir/opt/morkyn/install.sh" "\$pkgdir/opt/morkyn/linux"
  install -d "\$pkgdir/usr/bin"
  sed "s|@APP_DIR@|/opt/morkyn|" "\$srcdir/morkyn.sh" > "\$pkgdir/usr/bin/morkyn"
  chmod 755 "\$pkgdir/usr/bin/morkyn"
  install -Dm644 "\$srcdir/morkyn.desktop" "\$pkgdir/usr/share/applications/morkyn.desktop"
  install -Dm644 "\$srcdir/morkyn.png" "\$pkgdir/usr/share/icons/hicolor/256x256/apps/morkyn.png"
  install -Dm644 "\$srcdir/Morkyn/LICENSE.md" "\$pkgdir/usr/share/licenses/\$pkgname/LICENSE.md"
}
EOF
  cat > dist/aur/.SRCINFO <<EOF
pkgbase = morkyn-bin
	pkgdesc = $summary
	pkgver = $aur_version
	pkgrel = 1
	url = $homepage
	arch = x86_64
	license = custom
	depends = glibc
	depends = xdg-utils
	provides = morkyn
	conflicts = morkyn
	options = !strip
	options = !debug
	source = $homepage/releases/download/v$version/Morkyn-$version-linux-x86_64.tar.gz
	source = morkyn.sh
	source = morkyn.desktop
	source = morkyn.png
	sha256sums = $sum
	sha256sums = ${sums[0]}
	sha256sums = ${sums[1]}
	sha256sums = ${sums[2]}

pkgname = morkyn-bin
EOF
  built+=("dist/aur/PKGBUILD")
fi

echo "Built (glibc $glibc or newer):"
for f in "${built[@]}"; do echo "  $f"; done
