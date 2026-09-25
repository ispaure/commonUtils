#!/bin/bash
set -u
set -o pipefail

PROJECT_ROOT="${1:-}"
CONFIG_FILE="${2:-}"
PAUSE_ON_EXIT="${3:-false}"

case "${PAUSE_ON_EXIT,,}" in
    true|1|yes|on) PAUSE_ON_EXIT=true ;;
    false|0|no|off|"") PAUSE_ON_EXIT=false ;;
    *) echo "ERROR: pause_on_exit must be true or false (received: $PAUSE_ON_EXIT)." >&2; exit 1 ;;
esac
UV_INSTALL_DIR_DEFAULT="${HOME:-}/.local/bin"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"

# Include the user-local binary directory where uv is installed.
if [[ -n "$UV_INSTALL_DIR_DEFAULT" ]]; then
    export PATH="$UV_INSTALL_DIR_DEFAULT:$PATH"
fi

pause_if_requested() {
    if [[ "$PAUSE_ON_EXIT" == true && -t 0 ]]; then
        echo
        read -r -p "Press Enter to close..." _ || true
    fi
}

fail() {
    local message="$1"
    local code="${2:-1}"
    echo "ERROR: $message" >&2
    pause_if_requested
    exit "$code"
}

warn() {
    echo "WARNING: $*" >&2
}

info() {
    echo "$*"
}

require_command() {
    local command_name="$1"
    command -v "$command_name" >/dev/null 2>&1 || fail "Required command '$command_name' was not found."
}

read_launch_value() {
    local key="$1"
    local output_variable="$2"
    local value
    local status

    value="$(awk -v wanted="$key" '
        function trim(s) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
            return s
        }
        {
            sub(/\r$/, "")
        }
        /^[[:space:]]*[#;]/ { next }
        /^[[:space:]]*\[Launch\][[:space:]]*$/ {
            in_launch = 1
            next
        }
        /^[[:space:]]*\[/ {
            in_launch = 0
        }
        in_launch {
            line = $0
            pos = index(line, "=")
            if (!pos) {
                next
            }
            found_key = trim(substr(line, 1, pos - 1))
            if (found_key == wanted) {
                matches++
                found_value = trim(substr(line, pos + 1))
                if ((found_value ~ /^".*"$/) || (found_value ~ /^\047.*\047$/)) {
                    found_value = substr(found_value, 2, length(found_value) - 2)
                }
                value = found_value
            }
        }
        END {
            if (matches > 1) {
                exit 2
            }
            if (matches == 1) {
                print value
            }
        }
    ' "$CONFIG_FILE")"
    status=$?

    case $status in
        0) printf -v "$output_variable" '%s' "$value" ;;
        2) fail "Duplicate '$key' entries were found in [Launch] in $CONFIG_FILE." ;;
        *) fail "Failed to read '$key' from $CONFIG_FILE." ;;
    esac
}

resolve_from_project_root() {
    local value="$1"
    printf '%s\n' "$PROJECT_ROOT/$value"
}

check_regular_readable_file() {
    local path="$1"
    local label="$2"
    [[ -f "$path" ]] || fail "$label is missing: $path"
    [[ -r "$path" ]] || fail "$label exists but is not readable: $path"
}

validate_macos() {
    local os_name
    local machine
    local translated="0"
    local product_version=""
    local major_version=""

    require_command uname
    os_name="$(uname -s 2>/dev/null)" || fail "Could not determine the operating system with uname."
    [[ "$os_name" == "Darwin" ]] || fail "This launcher is for macOS only. Detected operating system: $os_name"

    machine="$(uname -m 2>/dev/null)" || fail "Could not determine the Mac architecture with uname."
    case "$machine" in
        arm64)
            info "Detected macOS on Apple Silicon (arm64)."
            ;;
        x86_64)
            # Apple Silicon processes running under Rosetta report x86_64.
            if command -v sysctl >/dev/null 2>&1; then
                translated="$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')"
            fi
            if [[ "$translated" == "1" ]]; then
                warn "This launcher is running under Rosetta 2 on Apple Silicon. uv and Python may resolve x86_64 builds. For a native arm64 environment, run the launcher from a native Apple Silicon Terminal/session."
            else
                info "Detected macOS on Intel (x86_64)."
            fi
            ;;
        *)
            fail "Unsupported macOS architecture reported by uname: $machine. This launcher expects arm64 (Apple Silicon) or x86_64 (Intel)."
            ;;
    esac

    if command -v sw_vers >/dev/null 2>&1; then
        product_version="$(sw_vers -productVersion 2>/dev/null || true)"
        major_version="${product_version%%.*}"
        if [[ "$major_version" =~ ^[0-9]+$ ]] && (( major_version < 13 )); then
            warn "Detected macOS $product_version. Current uv support targets macOS 13 or newer. macOS 12 may work only with additional compatibility requirements; older versions are not supported by this launcher."
        fi
    fi
}

install_uv() {
    local install_dir="$UV_INSTALL_DIR_DEFAULT"
    local installer=""

    [[ -n "${HOME:-}" ]] || fail "HOME is not set, so uv cannot be installed for the current user."
    [[ -n "$install_dir" ]] || fail "Could not determine the uv installation directory."

    if ! mkdir -p "$install_dir" 2>/dev/null; then
        fail "Could not create the uv installation directory: $install_dir"
    fi
    [[ -w "$install_dir" ]] || fail "uv installation directory is not writable: $install_dir"

    require_command mktemp
    installer="$(mktemp "${TMPDIR:-/tmp}/uv-installer.XXXXXX")" || fail "Could not create a temporary file for the uv installer."
    info "uv was not found. Downloading the official uv installer..."
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fL --retry 3 --connect-timeout 15 --max-time 120 -o "$installer" "$UV_INSTALL_URL"; then
            rm -f -- "$installer"
            fail "Failed to download the uv installer from $UV_INSTALL_URL. Check the network connection, proxy/firewall settings, and TLS certificates."
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget --timeout=15 --tries=3 -O "$installer" "$UV_INSTALL_URL"; then
            rm -f -- "$installer"
            fail "Failed to download the uv installer from $UV_INSTALL_URL. Check the network connection, proxy/firewall settings, and TLS certificates."
        fi
    else
        rm -f -- "$installer"
        fail "uv is not installed and neither curl nor wget is available to download it."
    fi

    [[ -s "$installer" ]] || {
        rm -f -- "$installer"
        fail "The downloaded uv installer is empty."
    }

    info "Installing uv for the current user into: $install_dir"
    if ! env UV_INSTALL_DIR="$install_dir" UV_NO_MODIFY_PATH=1 sh "$installer"; then
        rm -f -- "$installer"
        fail "The uv installer returned an error. uv was not installed successfully."
    fi
    rm -f -- "$installer"

    export PATH="$install_dir:$PATH"
    hash -r 2>/dev/null || true

    command -v uv >/dev/null 2>&1 || fail "uv installation completed, but 'uv' still cannot be found. Expected it under: $install_dir"
}

validate_uv() {
    local uv_path
    uv_path="$(command -v uv 2>/dev/null || true)"
    [[ -n "$uv_path" ]] || return 1
    if ! uv --version >/dev/null 2>&1; then
        fail "uv was found at '$uv_path' but could not run successfully. The binary may be damaged or built for the wrong architecture."
    fi
    info "Using $(uv --version) at: $uv_path"
}

ensure_python() {
    local python_request
    python_request="$(tr -d '\r' < "$SOURCE_DIR/.python-version" | awk 'NF && $1 !~ /^#/ { print; exit }')"
    [[ -n "$python_request" ]] || fail ".python-version does not contain a Python version request: $SOURCE_DIR/.python-version"

    info "Requested Python: $python_request"

    # Check without downloading first so installation failures can be reported separately.
    if uv python find --no-python-downloads >/dev/null 2>&1; then
        info "A compatible Python installation is already available."
        return 0
    fi

    info "Compatible Python was not found locally. Installing it with uv..."
    if ! uv python install; then
        fail "Python installation failed for the request in .python-version ('$python_request'). Check network access, uv output above, available disk space, the macOS/CPU architecture, and whether this Python build exists for the current platform."
    fi

    if ! uv python find --no-python-downloads >/dev/null 2>&1; then
        fail "uv reported that Python installation completed, but a compatible Python still cannot be resolved for '$python_request'."
    fi

    info "Python installation/resolution succeeded."
}

[[ -n "$PROJECT_ROOT" ]] || fail "Project root argument is missing. This shared launcher must be called by a project launcher."
[[ -n "$CONFIG_FILE" ]] || fail "Launch config argument is missing. This shared launcher must be called by a project launcher."
[[ -d "$PROJECT_ROOT" ]] || fail "Project root directory does not exist: $PROJECT_ROOT"
[[ -r "$PROJECT_ROOT" ]] || fail "Project root directory is not readable: $PROJECT_ROOT"
[[ -x "$PROJECT_ROOT" ]] || fail "Project root directory cannot be traversed by the current user: $PROJECT_ROOT"
check_regular_readable_file "$CONFIG_FILE" "Launch config"

validate_macos
require_command awk
require_command sh
require_command tr

SOURCE_DIR_VALUE=""
LAUNCH_FILE_VALUE=""
ENSURE_USER_DIR=""
read_launch_value source_dir SOURCE_DIR_VALUE
read_launch_value launch_file LAUNCH_FILE_VALUE
read_launch_value ensure_user_dir ENSURE_USER_DIR

[[ -n "$SOURCE_DIR_VALUE" ]] || fail "source_dir is missing or empty in [Launch] in $CONFIG_FILE."
[[ -n "$LAUNCH_FILE_VALUE" ]] || fail "launch_file is missing or empty in [Launch] in $CONFIG_FILE."
[[ "$SOURCE_DIR_VALUE" != /* ]] || fail "source_dir must be relative to the project launcher directory: $SOURCE_DIR_VALUE"
[[ "$LAUNCH_FILE_VALUE" != /* ]] || fail "launch_file must be relative to source_dir: $LAUNCH_FILE_VALUE"
[[ "$LAUNCH_FILE_VALUE" != *.py ]] || fail "launch_file must omit the .py extension. Use '${LAUNCH_FILE_VALUE%.py}' instead."

case "/$SOURCE_DIR_VALUE/" in
    */../*) fail "source_dir may not contain '..': $SOURCE_DIR_VALUE" ;;
esac
case "/$LAUNCH_FILE_VALUE/" in
    */../*) fail "launch_file may not contain '..': $LAUNCH_FILE_VALUE" ;;
esac

SOURCE_DIR="$(resolve_from_project_root "$SOURCE_DIR_VALUE")"
VENV_DIR="$PROJECT_ROOT/.venv"
LAUNCH_PATH="$SOURCE_DIR/$LAUNCH_FILE_VALUE.py"

[[ -d "$SOURCE_DIR" ]] || fail "Configured source_dir does not exist: $SOURCE_DIR"
[[ -r "$SOURCE_DIR" ]] || fail "Configured source_dir is not readable: $SOURCE_DIR"
[[ -x "$SOURCE_DIR" ]] || fail "Configured source_dir cannot be traversed by the current user: $SOURCE_DIR"

if [[ -e "$VENV_DIR" && ! -d "$VENV_DIR" ]]; then
    fail "The virtual-environment path exists but is not a directory: $VENV_DIR"
fi
if [[ ! -e "$VENV_DIR" && ! -w "$PROJECT_ROOT" ]]; then
    fail "The project root is not writable, so .venv cannot be created there: $PROJECT_ROOT"
fi

if [[ -n "$ENSURE_USER_DIR" ]]; then
    [[ -n "${HOME:-}" ]] || fail "ensure_user_dir is configured, but HOME is not set."
    [[ "$ENSURE_USER_DIR" != /* ]] || fail "ensure_user_dir must be relative to the current user's home directory: $ENSURE_USER_DIR"
    case "/$ENSURE_USER_DIR/" in
        */../*) fail "ensure_user_dir may not contain '..': $ENSURE_USER_DIR" ;;
    esac
    ENSURE_USER_PATH="$HOME/$ENSURE_USER_DIR"
    if [[ ! -d "$ENSURE_USER_PATH" ]]; then
        info "Creating user directory: $ENSURE_USER_PATH"
        mkdir -p "$ENSURE_USER_PATH" || fail "Could not create configured user directory: $ENSURE_USER_PATH"
    fi
fi

check_regular_readable_file "$SOURCE_DIR/.python-version" ".python-version"
check_regular_readable_file "$SOURCE_DIR/pyproject.toml" "pyproject.toml"
check_regular_readable_file "$LAUNCH_PATH" "Python launch file"

[[ -s "$SOURCE_DIR/.python-version" ]] || fail ".python-version is empty: $SOURCE_DIR/.python-version"
[[ -s "$SOURCE_DIR/pyproject.toml" ]] || fail "pyproject.toml is empty: $SOURCE_DIR/pyproject.toml"

# A missing uv.lock is a valid first-run state. If it already exists, it must
# be a readable, non-empty regular file; existing lockfiles are never silently
# replaced or regenerated by the launcher.
if [[ -e "$SOURCE_DIR/uv.lock" ]]; then
    check_regular_readable_file "$SOURCE_DIR/uv.lock" "uv.lock"
    [[ -s "$SOURCE_DIR/uv.lock" ]] || fail "uv.lock exists but is empty: $SOURCE_DIR/uv.lock"
fi

if ! command -v uv >/dev/null 2>&1; then
    install_uv
fi
validate_uv

export UV_PROJECT_ENVIRONMENT="$VENV_DIR"
cd "$SOURCE_DIR" || fail "Could not change to source_dir: $SOURCE_DIR"

ensure_python

if [[ ! -e "$SOURCE_DIR/uv.lock" ]]; then
    info "uv.lock was not found. Generating the initial lockfile..."
    if ! uv lock --no-python-downloads; then
        fail "Failed to generate uv.lock. Check pyproject.toml, dependency/version compatibility, network access, and uv's error output above."
    fi
    [[ -f "$SOURCE_DIR/uv.lock" ]] || fail "uv lock completed without creating the expected file: $SOURCE_DIR/uv.lock"
    [[ -r "$SOURCE_DIR/uv.lock" ]] || fail "uv lock created uv.lock, but it is not readable: $SOURCE_DIR/uv.lock"
    [[ -s "$SOURCE_DIR/uv.lock" ]] || fail "uv lock created uv.lock, but the file is empty: $SOURCE_DIR/uv.lock"
    info "Created initial lockfile: $SOURCE_DIR/uv.lock"
fi

info "Synchronizing the project environment from uv.lock..."
if ! uv sync --locked --no-python-downloads; then
    fail "uv sync failed. pyproject.toml and uv.lock may be out of sync, a dependency may not support this macOS/Python/CPU architecture, the network may be unavailable, or the existing .venv may be invalid. See uv's error output above."
fi

[[ -d "$VENV_DIR" ]] || fail "uv sync completed without creating the expected virtual environment: $VENV_DIR"

info "Launching: $LAUNCH_FILE_VALUE.py"
uv run --locked --no-sync --no-python-downloads python "$LAUNCH_PATH"
status=$?

echo
if [[ $status -eq 0 ]]; then
    echo "Process has ended."
else
    echo "ERROR: Python launch file exited with code $status: $LAUNCH_PATH" >&2
fi

pause_if_requested
exit "$status"
