#!/usr/bin/env sh
set -eu

APP_NAME="hpc-agent"
MIN_PYTHON="3.12"

INSTALL_ROOT="${HPC_AGENT_INSTALL_ROOT:-"$HOME/.local/share/hpc-agent"}"
VENV_DIR="${HPC_AGENT_VENV_DIR:-"$INSTALL_ROOT/.venv"}"
BIN_DIR="${HPC_AGENT_BIN_DIR:-"$HOME/.local/bin"}"
PYTHON_BIN="${HPC_AGENT_PYTHON:-python3}"
PACKAGE_SPEC="${HPC_AGENT_PACKAGE:-hpc-agent}"
WHEEL_SPEC="${HPC_AGENT_WHEEL:-}"
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
    for command_name in hpc-agent hpc-agent-check hpc-agent-init; do
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

if [ -n "$WHEEL_SPEC" ]; then
    log "Installing $APP_NAME from wheel: $WHEEL_SPEC"
    pip_install "$WHEEL_SPEC"
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
