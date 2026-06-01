#!/usr/bin/env bash
sleep 3
SPEED=1.6

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KBD_DEV=$(python3 -c "
import glob, os
ignore_words = ['mouse', 'optical', 'system control', 'consumer control']
real_keyboard = None
for dev in sorted(glob.glob('/dev/input/event*')):
    try:
        with open('/sys/class/input/'+os.path.basename(dev)+'/device/name') as f:
            name = f.read().strip().lower()
        if any(word in name for word in ignore_words):
            continue
        if 'keyboard' in name or 'kbd' in name or 'gaming keyboard' in name:
            with open('/sys/class/input/'+os.path.basename(dev)+'/device/capabilities/ev') as f:
                caps = int(f.read().strip(), 16)
            if caps & 0x1:
                real_keyboard = dev
                break
    except:
        continue
if not real_keyboard:
    for dev in sorted(glob.glob('/dev/input/event*')):
        try:
            with open('/sys/class/input/'+os.path.basename(dev)+'/device/name') as f:
                name = f.read().strip().lower()
            if 'optical mouse keyboard' in name:
                continue
            if 'keyboard' in name or 'kbd' in name:
                with open('/sys/class/input/'+os.path.basename(dev)+'/device/capabilities/ev') as f:
                    caps = int(f.read().strip(), 16)
                if caps & 0x1:
                    real_keyboard = dev
                    break
        except:
            continue
print(real_keyboard if real_keyboard else '')
")

MOUSE_DEV=$(python3 -c "
import glob, os
touchpad = None
mouse = None
for dev in sorted(glob.glob('/dev/input/event*')):
    try:
        with open('/sys/class/input/'+os.path.basename(dev)+'/device/name') as f:
            name = f.read().strip().lower()
        
        # Simpan jika itu Touchpad
        if 'touchpad' in name:
            touchpad = dev
        # Simpan jika itu Mouse (tapi jangan timpa mouse yang sudah ada)
        elif 'mouse' in name and 'keyboard' not in name and not mouse:
            mouse = dev
    except:
        continue

# WAJIB prioritaskan Touchpad jika tersedia, abaikan Mouse virtual ASUS!
if touchpad:
    print(touchpad)
elif mouse:
    print(mouse)
else:
    print('')
")

if [ -z "$KBD_DEV" ]; then
    echo "❌ Error: Could not detect keyboard" >&2
    exit 1
fi

if [ -z "$MOUSE_DEV" ]; then
    echo "❌ Error: Could not detect pointer/touchpad" >&2
    exit 1
fi

echo "Detected: keyboard=$KBD_DEV pointer=$MOUSE_DEV"
exec python3 "$SCRIPT_DIR/infinite_desktop_core.py" "$KBD_DEV" "$MOUSE_DEV" "$SPEED"