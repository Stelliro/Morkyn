#!/usr/bin/env bash
# Morkyn bootstrapper (Linux / macOS).
#
# Drop this file into an empty folder and run it:
#
#     bash start.sh
#
# First run  : clones the repo into ./Morkyn, installs dependencies, starts.
# Later runs : checks for updates, asks before applying them, then starts.
# Offline    : skips the update check and starts what is already on disk.
#
# Options:
#   --full         also install llama-cpp-python (only needed for the built-in
#                  GGUF server; Ollama and cloud APIs do not need it)
#   --update       apply an available update without asking
#   --no-update    skip the update check entirely
#   --port N       listen on port N (default 8000)
#   --lan          bind 0.0.0.0 so other devices on your network can play
#   --no-browser   do not open a browser window
#   --help         show this text
#
# Environment overrides: MORKYN_REPO_URL, MORKYN_BRANCH, MORKYN_DIR, MORKYN_PYTHON

set -uo pipefail

REPO_URL="${MORKYN_REPO_URL:-https://github.com/Stelliro/Morkyn.git}"
BRANCH="${MORKYN_BRANCH:-main}"

say()  { printf '%s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '!! %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }
rule() { printf '%s\n' "------------------------------------------------------------"; }

usage() { sed -n '2,23p' "$0" | sed 's/^#\{1,\} \{0,1\}//'; exit 0; }

# --- options -----------------------------------------------------------------
WANT_FULL=0
UPDATE_MODE="ask"      # ask | always | never
APP_PORT="${AI_RPG_APP_PORT:-8000}"
APP_HOST="127.0.0.1"
OPEN_BROWSER=1

while [ $# -gt 0 ]; do
    case "$1" in
        --full)       WANT_FULL=1 ;;
        --update|-u)  UPDATE_MODE="always" ;;
        --no-update)  UPDATE_MODE="never" ;;
        --lan)        APP_HOST="0.0.0.0" ;;
        --no-browser) OPEN_BROWSER=0 ;;
        --port)       shift; APP_PORT="${1:-8000}" ;;
        --port=*)     APP_PORT="${1#*=}" ;;
        --help|-h)    usage ;;
        *)            warn "ignoring unknown option: $1" ;;
    esac
    shift
done

case "$APP_PORT" in
    ''|*[!0-9]*) die "--port needs a number, got '$APP_PORT'" ;;
esac

# --- where does the checkout live? -------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

if [ -f "$SCRIPT_DIR/app/main.py" ] && [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    # Already sitting inside a checkout.
    REPO_DIR="$SCRIPT_DIR"
else
    REPO_DIR="${MORKYN_DIR:-$SCRIPT_DIR/Morkyn}"
fi

rule
say " Morkyn launcher"
rule
info "folder : $REPO_DIR"

# --- git ---------------------------------------------------------------------
if ! command -v git >/dev/null 2>&1; then
    warn "git was not found on PATH, and it is needed to download Morkyn."
    say ""
    say "  Debian / Ubuntu : sudo apt install git"
    say "  Fedora          : sudo dnf install git"
    say "  Arch            : sudo pacman -S git"
    say "  macOS           : xcode-select --install"
    exit 1
fi

if [ ! -e "$REPO_DIR" ]; then
    say ""
    info "no copy found - downloading Morkyn (this happens once)"
    if ! git clone "$REPO_URL" "$REPO_DIR"; then
        die "download failed. Check your internet connection and try again."
    fi
    info "downloaded"
elif [ ! -d "$REPO_DIR/.git" ]; then
    warn "'$REPO_DIR' exists but is not a git checkout."
    warn "Move or delete it, then run this script again."
    exit 1
elif [ "$UPDATE_MODE" = "never" ]; then
    info "update check skipped (--no-update)"
else
    # --- update check --------------------------------------------------------
    say ""
    info "checking for updates..."
    if ! git -C "$REPO_DIR" fetch --tags --prune origin >/dev/null 2>&1; then
        warn "could not reach GitHub - starting the copy you already have."
    else
        REMOTE_REF="origin/$BRANCH"
        if ! git -C "$REPO_DIR" rev-parse --verify --quiet "$REMOTE_REF" >/dev/null; then
            REMOTE_REF="origin/master"
        fi

        COUNTS="$(git -C "$REPO_DIR" rev-list --left-right --count "HEAD...$REMOTE_REF" 2>/dev/null)"
        AHEAD="$(printf '%s' "$COUNTS" | awk '{print $1}')"
        BEHIND="$(printf '%s' "$COUNTS" | awk '{print $2}')"
        : "${AHEAD:=0}" "${BEHIND:=0}"

        if [ "$BEHIND" -eq 0 ]; then
            info "already up to date"
        elif [ -n "$(git -C "$REPO_DIR" status --porcelain 2>/dev/null)" ]; then
            warn "$BEHIND update(s) available, but you have local changes."
            warn "Commit or stash them to update. Starting your current copy."
        elif [ "$AHEAD" -gt 0 ]; then
            warn "$BEHIND update(s) available, but your copy has $AHEAD local commit(s)."
            warn "Merge by hand to update. Starting your current copy."
        else
            say ""
            say "  An update is available ($BEHIND new change(s))."
            git -C "$REPO_DIR" log --oneline --no-decorate "HEAD..$REMOTE_REF" 2>/dev/null | head -8 | sed 's/^/      /'
            say ""

            DO_UPDATE=0
            if [ "$UPDATE_MODE" = "always" ]; then
                DO_UPDATE=1
            elif [ -t 0 ]; then
                printf '  Update now? [Y/n] '
                read -r ANSWER
                case "$ANSWER" in
                    ""|y|Y|yes|YES) DO_UPDATE=1 ;;
                    *)              DO_UPDATE=0 ;;
                esac
            else
                info "not an interactive terminal - skipping (use --update to force)"
            fi

            if [ "$DO_UPDATE" -eq 1 ]; then
                if git -C "$REPO_DIR" merge --ff-only "$REMOTE_REF"; then
                    info "updated"
                else
                    warn "update failed - starting your current copy instead."
                fi
            else
                info "skipped - starting your current copy"
            fi
        fi
    fi
fi

cd "$REPO_DIR" || die "could not enter $REPO_DIR"

# --- python ------------------------------------------------------------------
PY=""
for candidate in "${MORKYN_PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    warn "Python 3.11 or newer was not found on PATH."
    say ""
    say "  Debian / Ubuntu : sudo apt install python3 python3-venv"
    say "  Fedora          : sudo dnf install python3"
    say "  macOS           : brew install python"
    exit 1
fi

# --- virtual environment -----------------------------------------------------
VENV="$REPO_DIR/.venv"

# Unix venvs put the interpreter in bin/, Windows ones (Git Bash, MSYS) in
# Scripts/. Check both so this script also works from a Git Bash prompt.
venv_python() {
    if [ -x "$VENV/bin/python" ]; then
        printf '%s' "$VENV/bin/python"
    elif [ -x "$VENV/Scripts/python.exe" ]; then
        printf '%s' "$VENV/Scripts/python.exe"
    fi
}

VPY="$(venv_python)"
if [ -z "$VPY" ]; then
    say ""
    info "creating a private Python environment in .venv"
    if ! "$PY" -m venv "$VENV"; then
        warn "could not create the virtual environment."
        warn "On Debian/Ubuntu this usually means: sudo apt install python3-venv"
        exit 1
    fi
    VPY="$(venv_python)"
    [ -n "$VPY" ] || die "the virtual environment was created but has no interpreter in it"
fi

# --- dependencies ------------------------------------------------------------
NEED_DEPS=0
"$VPY" -c 'import fastapi, uvicorn, pydantic' >/dev/null 2>&1 || NEED_DEPS=1
[ "$WANT_FULL" -eq 1 ] && NEED_DEPS=1

if [ "$NEED_DEPS" -eq 1 ]; then
    say ""
    info "installing dependencies (the first run takes a few minutes)"
    "$VPY" -m pip install --upgrade pip >/dev/null 2>&1

    REQ="requirements.txt"
    TRIMMED=""
    if [ "$WANT_FULL" -eq 0 ]; then
        # llama-cpp-python is only needed for the built-in GGUF server, and its
        # CUDA wheels are a large download that fails outright on machines with
        # no matching toolchain. Ollama and cloud APIs need none of it, so the
        # default install filters it out of the project's own pins rather than
        # keeping a second copy of the version numbers here. --full keeps it.
        TRIMMED="$(mktemp)"
        "$VPY" -c 'import io,sys; src=io.open("requirements.txt",encoding="utf-8"); io.open(sys.argv[1],"w",encoding="utf-8").writelines([l for l in src if "llama-cpp-python" not in l and "--extra-index-url" not in l])' "$TRIMMED" || die "could not prepare the dependency list"
        REQ="$TRIMMED"
    fi

    if ! "$VPY" -m pip install -r "$REQ"; then
        [ -n "$TRIMMED" ] && rm -f "$TRIMMED"
        warn "dependency install failed."
        exit 1
    fi
    [ -n "$TRIMMED" ] && rm -f "$TRIMMED"
fi

# --- run ---------------------------------------------------------------------
URL="http://127.0.0.1:$APP_PORT/"

say ""
rule
say " Morkyn is starting"
info "open $URL in your browser"
info "press Ctrl+C here to stop"
rule
say ""

if [ "$OPEN_BROWSER" -eq 1 ] && [ -z "${AI_RPG_NO_BROWSER:-}" ]; then
    OPENER=""
    if command -v xdg-open >/dev/null 2>&1; then
        OPENER="xdg-open"
    elif command -v open >/dev/null 2>&1; then
        OPENER="open"
    fi
    if [ -n "$OPENER" ]; then
        ( sleep 3; "$OPENER" "$URL" >/dev/null 2>&1 ) &
    fi
fi

exec "$VPY" -m uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT"
