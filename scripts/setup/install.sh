#!/usr/bin/env bash
# KG Chat installer (Linux). Made for Arch / Manjaro; on other distros use --skip-system
# and install python (3.12+), mpv, ffmpeg, portaudio.
#
# Usage: bash install.sh [--skip-system]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$ROOT/.venv"
LOG_FILE="$ROOT/install_log.txt"
ICON_FILE="$ROOT/src/icons/app/crazy.svg"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_ENTRY="$APPLICATIONS_DIR/kg-chat.desktop"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=12
SYSTEM_PACKAGES=(python noto-fonts-emoji mpv ffmpeg portaudio xdg-utils xcb-util-cursor gst-plugins-base gst-plugins-good)

exec > >(tee "$LOG_FILE") 2>&1

info() { echo "==> $*"; }
warn() { echo "!!  $*" >&2; }
die() { echo "ERROR: $*" >&2; exit 1; }

SKIP_SYSTEM=0
[[ "${1:-}" == "--skip-system" ]] && SKIP_SYSTEM=1

info "Installation started at $(date)"
(( EUID != 0 )) || die "Run as a normal user, not root (sudo is requested only where needed)."
[[ -f "$ROOT/requirements.txt" ]] || die "requirements.txt not found in $ROOT"
[[ -f "$ROOT/src/main.py" ]] || die "src/main.py not found in $ROOT"

install_system_packages() {
    if (( SKIP_SYSTEM )); then
        info "Skipping system packages (--skip-system)"
        return
    fi
    if ! command -v pacman > /dev/null; then
        warn "pacman not found. Install manually: python (3.12+), mpv, ffmpeg, portaudio, an emoji font (Noto Color Emoji)."
        return
    fi
    info "Installing system packages: ${SYSTEM_PACKAGES[*]}"
    sudo pacman -S --needed --noconfirm "${SYSTEM_PACKAGES[@]}"
}

check_python() {
    command -v python3 > /dev/null || die "python3 not found"
    python3 -c "import sys; sys.exit(sys.version_info < ($MIN_PYTHON_MAJOR, $MIN_PYTHON_MINOR))" \
        || die "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR or newer is required (found $(python3 -V))"
    info "Using $(python3 -V)"
}

install_python_packages() {
    info "Creating virtual environment in $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip
    info "Installing Python packages from requirements.txt"
    "$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"
    info "Checking for PyQt6 and WebEngine upgrades"
    "$VENV/bin/python" -m pip install --upgrade PyQt6 PyQt6-WebEngine
    "$VENV/bin/python" -c "import PyQt6.QtWidgets, PyQt6.QtWebEngineWidgets" \
        || warn "PyQt6 / WebEngine could not be imported, see the messages above"
}

create_shortcuts() {
    chmod +x "$ROOT/scripts/launchers/launcher.sh" "$ROOT/scripts/setup/install.sh" "$ROOT/scripts/setup/uninstall.sh" 2> /dev/null || true
    mkdir -p "$APPLICATIONS_DIR"
    cat > "$DESKTOP_ENTRY" << DESKTOP
[Desktop Entry]
Type=Application
Name=KG Chat
Comment=Klavogonki chat client
Exec=bash "$ROOT/scripts/launchers/launcher.sh"
Icon=$ICON_FILE
Terminal=false
Categories=Network;Chat;InstantMessaging;
DESKTOP
    chmod +x "$DESKTOP_ENTRY"
    info "Application menu entry created: $DESKTOP_ENTRY"

    local desktop_dir
    desktop_dir="$(xdg-user-dir DESKTOP 2> /dev/null || echo "$HOME/Desktop")"
    if [[ -d "$desktop_dir" && ! -e "$desktop_dir/kg-chat.desktop" ]]; then
        cp "$DESKTOP_ENTRY" "$desktop_dir/kg-chat.desktop"
        chmod +x "$desktop_dir/kg-chat.desktop"
        info "Desktop shortcut created: $desktop_dir/kg-chat.desktop"
    fi

    command -v update-desktop-database > /dev/null && update-desktop-database "$APPLICATIONS_DIR" || true
    command -v kbuildsycoca6 > /dev/null && kbuildsycoca6 > /dev/null 2>&1 || true
}

check_emoji_font() {
    if ! fc-list 2> /dev/null | grep -qi emoji; then
        warn "No emoji font found: install it (Arch: sudo pacman -S noto-fonts-emoji) and run fc-cache -f"
    fi
}

install_system_packages
check_python
install_python_packages
create_shortcuts
check_emoji_font

info "Installation finished at $(date)"
echo
echo "Start KG Chat from the application menu or with: bash \"$ROOT/scripts/launchers/launcher.sh\""
echo "Note: the global show/hide hotkey does not work on Wayland (and needs root on X11)."
echo "Log file: $LOG_FILE"
