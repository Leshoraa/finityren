#!/usr/bin/env bash
sleep 3
SPEED=3.0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/infinite_desktop_core.py" "auto" "auto" "$SPEED"