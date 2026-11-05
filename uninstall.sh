#!/usr/bin/env bash
# KG Chat uninstaller (Linux). Removes shortcuts, autostart, the virtual environment
# and the project folder (including this script). Your data is kept unless you agree to delete it.
#
# Usage: bash uninstall.sh

set -uo pipefail

ask() {
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "${answer,,}" == y* ]]
}

# Everything runs inside one function so bash has read the whole script before the folder is deleted
main() {
    local root data_dir desktop_dir
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    data_dir="$HOME/KG_Chat_Data"
    desktop_dir="$(xdg-user-dir DESKTOP 2> /dev/null || echo "$HOME/Desktop")"

    if [[ ! -f "$root/src/main.py" || ! -d "$root/launchers" || "$root" == "/" || "$root" == "$HOME" ]]; then
        echo "ERROR: $root does not look like the KG Chat project folder, nothing was removed." >&2
        return 1
    fi

    echo "This removes KG Chat: shortcuts, autostart entry and the project folder:"
    echo "  $root"
    ask "Continue?" || { echo "Cancelled."; return 0; }

    echo "==> Stopping KG Chat"
    pkill -f "$root/src/main.py" 2> /dev/null && sleep 1

    echo "==> Removing shortcuts and autostart"
    rm -f -- "$HOME/.local/share/applications/kg-chat.desktop" \
        "$desktop_dir/kg-chat.desktop" \
        "$HOME/.config/autostart/kg_chat.desktop" \
        "$HOME/.config/autostart/kg-chat.desktop"
    command -v update-desktop-database > /dev/null && update-desktop-database "$HOME/.local/share/applications" 2> /dev/null
    command -v kbuildsycoca6 > /dev/null && kbuildsycoca6 > /dev/null 2>&1

    if [[ -d "$data_dir" ]] && ask "Also delete your data (accounts, chat logs, settings) in $data_dir?"; then
        rm -rf -- "$data_dir"
        echo "==> Data deleted"
    fi

    cd "$HOME" || return 1
    if ask "Delete the project folder $root (including the virtual environment)?"; then
        rm -rf -- "$root"
        echo "==> Project folder deleted"
    else
        echo "==> Project folder kept"
    fi

    echo "Done. System packages (mpv, ffmpeg, ...) were left installed."
}

main "$@"
exit $?
