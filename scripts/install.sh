#!/usr/bin/env sh
set -eu

APP_NAME="hpc-agent"
MIN_PYTHON="3.12"
DEFAULT_REPO_BASE="https://artifacts-cn-beijing.volces.com/repository/agents"
DEFAULT_NAMESPACE="ai-llm"
DEFAULT_MODEL="hpc-agent"
DEFAULT_VERSION="stable"
DEFAULT_LATEST_FILENAME="latest.json"

INSTALL_ROOT="${HPC_AGENT_INSTALL_ROOT:-"$HOME/.local/share/hpc-agent"}"
VENV_DIR="${HPC_AGENT_VENV_DIR:-"$INSTALL_ROOT/.venv"}"
BIN_DIR="${HPC_AGENT_BIN_DIR:-"$HOME/.local/bin"}"
PYTHON_BIN="${HPC_AGENT_PYTHON:-python3}"
PACKAGE_SPEC="${HPC_AGENT_PACKAGE:-hpc-agent}"
WHEEL_SPEC="${HPC_AGENT_WHEEL:-}"
WHEEL_URL="${HPC_AGENT_WHEEL_URL:-}"
USE_PACKAGE="${HPC_AGENT_USE_PACKAGE:-0}"
LATEST_URL="${HPC_AGENT_LATEST_URL:-}"
REPO_BASE="${HPC_AGENT_REPO_BASE:-"$DEFAULT_REPO_BASE"}"
REPO_USERNAME="${HPC_AGENT_REPO_USERNAME:-${VOLC_USERNAME:-}}"
REPO_TOKEN="${HPC_AGENT_REPO_TOKEN:-${VOLC_TOKEN:-}}"
REPO_NAMESPACE="${HPC_AGENT_NAMESPACE:-"$DEFAULT_NAMESPACE"}"
REPO_MODEL="${HPC_AGENT_MODEL:-"$DEFAULT_MODEL"}"
REPO_VERSION="${HPC_AGENT_VERSION:-"$DEFAULT_VERSION"}"
WHEEL_FILENAME="${HPC_AGENT_WHEEL_FILENAME:-}"
DOWNLOAD_DIR="${HPC_AGENT_DOWNLOAD_DIR:-"${TMPDIR:-/tmp}/hpc-agent-install"}"
PIP_INDEX_URL="${HPC_AGENT_PIP_INDEX_URL:-}"
PIP_EXTRA_INDEX_URL="${HPC_AGENT_PIP_EXTRA_INDEX_URL:-}"
SKIP_CHECK="${HPC_AGENT_SKIP_CHECK:-0}"
FORCE_REINSTALL="${HPC_AGENT_FORCE_REINSTALL:-0}"
PIP_NO_DEPS="${HPC_AGENT_PIP_NO_DEPS:-0}"

log() {
    printf '%s\n' "==> $*"
}

fail() {
    printf '%s\n' "ERROR: $*" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

download_file() {
    url="$1"
    output="$2"

    command_exists curl || fail "Cannot find curl. Install curl first, or set HPC_AGENT_WHEEL to a local wheel file."
    mkdir -p "$(dirname "$output")"

    if [ -n "$REPO_USERNAME" ] || [ -n "$REPO_TOKEN" ]; then
        [ -n "$REPO_USERNAME" ] || fail "HPC_AGENT_REPO_TOKEN is set but HPC_AGENT_REPO_USERNAME is empty."
        [ -n "$REPO_TOKEN" ] || fail "HPC_AGENT_REPO_USERNAME is set but HPC_AGENT_REPO_TOKEN is empty."
        curl -fL -u "$REPO_USERNAME:$REPO_TOKEN" "$url" -o "$output"
    else
        curl -fL "$url" -o "$output"
    fi
}

default_wheel_url() {
    repo_base="${REPO_BASE%/}"
    printf '%s\n' "$repo_base/models/$REPO_NAMESPACE/$REPO_MODEL/$REPO_VERSION/$WHEEL_FILENAME"
}

default_latest_url() {
    repo_base="${REPO_BASE%/}"
    printf '%s\n' "$repo_base/models/$REPO_NAMESPACE/$REPO_MODEL/$REPO_VERSION/$DEFAULT_LATEST_FILENAME"
}

repo_file_url() {
    repo_path="$1"
    repo_path="${repo_path#/}"
    repo_base="${REPO_BASE%/}"
    printf '%s\n' "$repo_base/models/$REPO_NAMESPACE/$REPO_MODEL/$repo_path"
}

filename_from_url_or_path() {
    value="$1"
    value="${value%%\?*}"
    value="${value%%#*}"
    value="${value%/}"
    value="${value##*/}"
    [ -n "$value" ] || value="hpc-agent-wheel.whl"
    printf '%s\n' "$value"
}

parse_latest_json() {
    latest_file="$1"
    "$PYTHON_BIN" - "$latest_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    latest = json.load(fh)

wheel = latest.get("files", {}).get("wheel", {})
path = wheel.get("path")
sha256 = wheel.get("sha256", "")

if not path:
    raise SystemExit("latest.json does not contain files.wheel.path")

print(path)
print(sha256)
PY
}

load_latest_wheel_metadata() {
    if [ -z "$LATEST_URL" ]; then
        LATEST_URL="$(default_latest_url)"
    fi

    latest_file="$DOWNLOAD_DIR/$DEFAULT_LATEST_FILENAME"
    log "Downloading $APP_NAME latest metadata: $LATEST_URL"
    download_file "$LATEST_URL" "$latest_file"

    metadata="$(parse_latest_json "$latest_file")"
    WHEEL_PATH="$(printf '%s\n' "$metadata" | sed -n '1p')"
    WHEEL_SHA256="$(printf '%s\n' "$metadata" | sed -n '2p')"

    case "$WHEEL_PATH" in
        http://*|https://*|file://*)
            WHEEL_URL="$WHEEL_PATH"
            ;;
        *)
            WHEEL_URL="$(repo_file_url "$WHEEL_PATH")"
            ;;
    esac

    if [ -z "$WHEEL_FILENAME" ]; then
        WHEEL_FILENAME="$(filename_from_url_or_path "$WHEEL_PATH")"
    fi
}

verify_sha256_if_available() {
    target="$1"
    expected="$2"

    if [ -z "$expected" ] || [ "$expected" = "REPLACE_WITH_WHEEL_SHA256" ]; then
        return
    fi
    command_exists sha256sum || return

    actual="$(sha256sum "$target" | awk '{print $1}')"
    [ "$actual" = "$expected" ] || fail "Downloaded wheel sha256 mismatch. Expected $expected, got $actual."
}

resolve_install_target() {
    if [ "$USE_PACKAGE" = "1" ]; then
        INSTALL_TARGET=""
        return
    fi

    if [ -n "$WHEEL_SPEC" ]; then
        INSTALL_TARGET="$WHEEL_SPEC"
        return
    fi

    if [ -z "$WHEEL_URL" ]; then
        if [ -n "$WHEEL_FILENAME" ]; then
            WHEEL_URL="$(default_wheel_url)"
        else
            load_latest_wheel_metadata
        fi
    fi

    if [ -z "$WHEEL_FILENAME" ]; then
        WHEEL_FILENAME="$(filename_from_url_or_path "$WHEEL_URL")"
    fi

    downloaded_wheel="$DOWNLOAD_DIR/$WHEEL_FILENAME"
    log "Downloading $APP_NAME wheel: $WHEEL_URL"
    download_file "$WHEEL_URL" "$downloaded_wheel"
    verify_sha256_if_available "$downloaded_wheel" "${WHEEL_SHA256:-}"
    INSTALL_TARGET="$downloaded_wheel"
}

check_python() {
    command_exists "$PYTHON_BIN" || fail "Cannot find $PYTHON_BIN. Install Python $MIN_PYTHON+ first."
    "$PYTHON_BIN" - "$MIN_PYTHON" <<'PY'
import sys

required = tuple(int(part) for part in sys.argv[1].split("."))
current = sys.version_info[:2]
if current < required:
    raise SystemExit(
        f"Python {required[0]}.{required[1]}+ is required, got {sys.version.split()[0]}"
    )
PY
}

pip_install() {
    install_target="$1"
    set -- "$VENV_DIR/bin/python" -m pip install --upgrade
    if [ "$FORCE_REINSTALL" = "1" ]; then
        set -- "$@" --force-reinstall
    fi
    if [ "$PIP_NO_DEPS" = "1" ]; then
        set -- "$@" --no-deps
    fi
    if [ -n "$PIP_INDEX_URL" ]; then
        set -- "$@" --index-url "$PIP_INDEX_URL"
    fi
    if [ -n "$PIP_EXTRA_INDEX_URL" ]; then
        set -- "$@" --extra-index-url "$PIP_EXTRA_INDEX_URL"
    fi
    set -- "$@" "$install_target"
    "$@"
}

create_links() {
    mkdir -p "$BIN_DIR"
    for command_name in hpc-agent hpc-agent-check hpc-agent-init hpc-agent-mcp hpc-agent-mcp-client; do
        if [ -x "$VENV_DIR/bin/$command_name" ]; then
            ln -sfn "$VENV_DIR/bin/$command_name" "$BIN_DIR/$command_name"
        fi
    done
}

run_agent_command() {
    HPC_AGENT_INSTALL_ROOT= \
    HPC_AGENT_RESOURCE_ROOT="${HPC_AGENT_RESOURCE_ROOT:-"$VENV_DIR/share/hpc-agent"}" \
    "$@"
}

print_path_hint() {
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            printf '\n%s\n' "NOTE: $BIN_DIR is not in PATH."
            printf '%s\n' "Add this to your shell profile if needed:"
            printf '%s\n' "  export PATH=\"$BIN_DIR:\$PATH\""
            ;;
    esac
}

log "Checking Python"
check_python

log "Creating virtual environment: $VENV_DIR"
mkdir -p "$INSTALL_ROOT"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

log "Upgrading pip"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

INSTALL_TARGET=""
resolve_install_target
if [ -n "$INSTALL_TARGET" ]; then
    log "Installing $APP_NAME from wheel: $INSTALL_TARGET"
    pip_install "$INSTALL_TARGET"
else
    log "Installing $APP_NAME package: $PACKAGE_SPEC"
    pip_install "$PACKAGE_SPEC"
fi

log "Creating command links in $BIN_DIR"
create_links

log "Initializing user configuration"
run_agent_command "$VENV_DIR/bin/hpc-agent-init"

if [ "$SKIP_CHECK" = "1" ]; then
    log "Skipping hpc-agent-check because HPC_AGENT_SKIP_CHECK=1"
else
    log "Running installed package check"
    run_agent_command "$VENV_DIR/bin/hpc-agent-check"
fi

print_path_hint

printf '\n%s\n' "HPC Agent installation complete."
printf '%s\n' "Commands:"
printf '%s\n' "  $BIN_DIR/hpc-agent"
printf '%s\n' "  $BIN_DIR/hpc-agent-check"
printf '%s\n' "  $BIN_DIR/hpc-agent-init"
