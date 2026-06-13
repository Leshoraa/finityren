sleep 3

MOUSE_SPEED=0.2
TRACKPAD_SPEED=5.0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$SCRIPT_DIR/infinite_desktop_core.py" "auto" "auto" "$MOUSE_SPEED" "$TRACKPAD_SPEED"