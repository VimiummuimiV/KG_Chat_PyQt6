#!/usr/bin/env bash
# KG Chat launcher (Linux): starts the app in the background

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3 || true)"

if [[ -z "$PYTHON" ]]; then
    echo "Python not found. Run install.sh first." >&2
    exit 1
fi

LOG_DIR="$HOME/KG_Chat_Data"
mkdir -p "$LOG_DIR"

cd "$ROOT" || exit 1
nohup "$PYTHON" "$ROOT/src/main.py" > "$LOG_DIR/launcher.log" 2>&1 &

echo "KG Chat started in background (log: $LOG_DIR/launcher.log)"
echo "To exit: right-click the tray icon -> Exit"
