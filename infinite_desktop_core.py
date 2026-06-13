import sys
import struct
import threading
import time
import subprocess
import json
import math
import glob
import os
import socket

kbd_dev = sys.argv[1]
mouse_dev = sys.argv[2]
mouse_speed = float(sys.argv[3])
trackpad_speed = float(sys.argv[4]) if len(sys.argv) > 4 else mouse_speed
EVENT_SIZE = struct.calcsize('llHHi')

EV_KEY = 1
EV_REL = 2
EV_ABS = 3
REL_X = 0
REL_Y = 1
ABS_X = 0
ABS_Y = 1

KEY_LEFTMETA = 125
KEY_RIGHTMETA = 126
KEY_LEFTALT = 56
KEY_RIGHTALT = 100
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_UP = 103
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_DOWN = 108
KEY_SPACE = 57
KEY_F = 33
BTN_LEFT = 272
BTN_TOUCH = 330

STATE_FILE = "/tmp/infinite-desktop-state"
PROTECTED_APPS = ['brave-browser', 'chromium', 'chromium-browser', 'google-chrome',
                  'firefox', 'firefoxdeveloperedition', 'librewolf', 'vivaldi',
                  'opera', 'microsoft-edge']
GAP = 10
PSEUDO_SCALE_W = 0.994
PSEUDO_SCALE_H = 0.966
BOTTOM_MARGIN = 6

lock = threading.Lock()
cache_lock = threading.Lock()
wakeup_event = threading.Event()
refresh_event = threading.Event()

super_pressed = False
alt_pressed = False
ctrl_pressed = False
btn_left = False
acc_x = 0.0
acc_y = 0.0
last_nav_time = 0
NAV_COOLDOWN = 0.2

window_positions = {}
last_workspace_id = None
auto_floated_windows = set()

cached_workspace_id = 1
cached_clients = []
cached_monitors = []
panning = False
is_animating = False
dragged_window_addr = None

def read_inverted():
    try:
        with open(STATE_FILE) as f:
            return f.read().strip() == 'inverse'
    except:
        return False

def get_monitor_center():
    with cache_lock:
        monitors = cached_monitors
    if monitors:
        for m in monitors:
            if m.get('focused', False):
                scale = m.get('scale', 1.0)
                cx = m['x'] + (m['width'] / scale) / 2.0
                cy = m['y'] + (m['height'] / scale) / 2.0
                return cx, cy
        m = monitors[0]
        scale = m.get('scale', 1.0)
        cx = m['x'] + (m['width'] / scale) / 2.0
        cy = m['y'] + (m['height'] / scale) / 2.0
        return cx, cy
    return 960.0, 600.0

def get_floating_windows(workspace_id):
    with cache_lock:
        return [w for w in cached_clients if w.get('floating') and w.get('workspace', {}).get('id') == workspace_id]

def is_protected_app(window):
    if not window:
        return False
    return any(app in window.get('class', '').lower() for app in PROTECTED_APPS)

def pan_to_window(floating_windows, target_addr, center_x, center_y):
    target_window = next((w for w in floating_windows if w['address'] == target_addr), None)
    if not target_window:
        return
    with cache_lock:
        monitors = cached_monitors
    mon = None
    if monitors:
        mon = next((m for m in monitors if m.get('focused', False)), monitors[0])
    if mon:
        scale = mon.get('scale', 1.0)
        monitor_bottom_y = mon['y'] + (mon['height'] / scale)
    else:
        monitor_bottom_y = center_y * 2.0
        
    target_center_x = target_window['at'][0] + target_window['size'][0] / 2.0
    target_center_y = target_window['at'][1] + target_window['size'][1] / 2.0

    dx = int(round(center_x - target_center_x))
    dy = int(round(center_y - target_center_y))
    
    if dx == 0 and dy == 0:
        if not is_protected_app(target_window):
            subprocess.Popen(['hyprctl', 'dispatch', 'focuswindow', f'address:{target_addr}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    batch_cmds = []
    for w in floating_windows:
        batch_cmds.append(f"dispatch movewindowpixel {dx} {dy},address:{w['address']}")
        if w['address'] in window_positions:
            window_positions[w['address']]['target_x'] += dx
            window_positions[w['address']]['target_y'] += dy
            window_positions[w['address']]['sx'] += dx
            window_positions[w['address']]['sy'] += dy
    subprocess.Popen(['hyprctl', '--batch', ';'.join(batch_cmds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not is_protected_app(target_window):
        subprocess.Popen(['hyprctl', 'dispatch', 'focuswindow', f'address:{target_addr}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def change_focus(direction):
    global last_nav_time
    current_time = time.time()
    if current_time - last_nav_time < NAV_COOLDOWN:
        return
    last_nav_time = current_time

    # FIX: Paksa update cache ke Hyprland real-time sebelum pindah pakai panah keyboard
    # Ini yang mencegah layout mental/jump karena pakai koordinat lama
    update_cache()

    try:
        with cache_lock:
            workspace_id = cached_workspace_id
        floating_windows = get_floating_windows(workspace_id)
        if len(floating_windows) <= 1:
            return
        center_x, center_y = get_monitor_center()
        current_window = None
        min_dist_center = float('inf')
        for w in floating_windows:
            wx = w['at'][0] + w['size'][0] / 2.0
            wy = w['at'][1] + w['size'][1] / 2.0
            d = math.hypot(wx - center_x, wy - center_y)
            if d < min_dist_center:
                min_dist_center = d
                current_window = w
        if not current_window:
            return
        fx = current_window['at'][0] + current_window['size'][0] / 2.0
        fy = current_window['at'][1] + current_window['size'][1] / 2.0
        best_window = None
        best_score = float('inf')
        for w in floating_windows:
            if w['address'] == current_window['address']:
                continue
            wx = w['at'][0] + w['size'][0] / 2.0
            wy = w['at'][1] + w['size'][1] / 2.0
            dx = wx - fx
            dy = wy - fy
            dist = math.hypot(dx, dy)
            valid = False
            if direction == 'up' and dy < -10 and abs(dy) > abs(dx) * 0.5:
                valid = True
                score = dist + abs(dx) * 2.5
            elif direction == 'down' and dy > 10 and abs(dy) > abs(dx) * 0.5:
                valid = True
                score = dist + abs(dx) * 2.5
            elif direction == 'left' and dx < -10 and abs(dx) > abs(dy) * 0.5:
                valid = True
                score = dist + abs(dy) * 2.5
            elif direction == 'right' and dx > 10 and abs(dx) > abs(dy) * 0.5:
                valid = True
                score = dist + abs(dy) * 2.5
            if valid and score < best_score:
                best_score = score
                best_window = w
        if not best_window:
            for w in floating_windows:
                if w['address'] == current_window['address']:
                    continue
                wx = w['at'][0] + w['size'][0] / 2.0
                wy = w['at'][1] + w['size'][1] / 2.0
                dx = wx - fx
                dy = wy - fy
                dist = math.hypot(dx, dy)
                valid = False
                if direction == 'up' and dy < -10:
                    valid = True
                    score = dist + abs(dx) * 1.5
                elif direction == 'down' and dy > 10:
                    valid = True
                    score = dist + abs(dx) * 1.5
                elif direction == 'left' and dx < -10:
                    valid = True
                    score = dist + abs(dy) * 1.5
                elif direction == 'right' and dx > 10:
                    valid = True
                    score = dist + abs(dy) * 1.5
                if valid and score < best_score:
                    best_score = score
                    best_window = w
        if best_window:
            pan_to_window(floating_windows, best_window['address'], center_x, center_y)
    except:
        pass

def kbd_reader(dev_path):
    global super_pressed, alt_pressed, ctrl_pressed
    try:
        fd = open(dev_path, 'rb')
    except:
        return
    while True:
        try:
            data = fd.read(EVENT_SIZE)
            if not data or len(data) < EVENT_SIZE:
                break
            _, _, etype, code, value = struct.unpack('llHHi', data)
            if etype != EV_KEY or value == 2:
                continue
            with lock:
                if code in (KEY_LEFTMETA, KEY_RIGHTMETA):
                    super_pressed = (value == 1)
                    wakeup_event.set()
                elif code in (KEY_LEFTALT, KEY_RIGHTALT):
                    alt_pressed = (value == 1)
                    wakeup_event.set()
                elif code in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
                    ctrl_pressed = (value == 1)
                    wakeup_event.set()
                if super_pressed and alt_pressed and not ctrl_pressed:
                    if value == 1:
                        if code == KEY_UP:
                            threading.Thread(target=change_focus, args=('up',), daemon=True).start()
                        elif code == KEY_DOWN:
                            threading.Thread(target=change_focus, args=('down',), daemon=True).start()
                        elif code == KEY_LEFT:
                            threading.Thread(target=change_focus, args=('left',), daemon=True).start()
                        elif code == KEY_RIGHT:
                            threading.Thread(target=change_focus, args=('right',), daemon=True).start()
                        elif code in (KEY_SPACE, KEY_F):
                            def pseudo_fullscreen():
                                try:
                                    r = subprocess.run(
                                        ['hyprctl', 'activewindow', '-j'],
                                        capture_output=True,
                                        text=True,
                                        timeout=0.2
                                    )
                                    win = json.loads(r.stdout)
                                    if not win:
                                        return
                                    addr = win['address']
                                    with cache_lock:
                                        monitors = cached_monitors
                                    mon = next(
                                        (m for m in monitors if m.get('focused', False)),
                                        monitors[0]
                                    )
                                    scale = mon.get('scale', 1)
                                    w = int((mon['width'] / scale) * PSEUDO_SCALE_W)
                                    h = int((mon['height'] / scale) * PSEUDO_SCALE_H)
                                    cmds = []
                                    if not win.get('floating', False):
                                        cmds.append(f"dispatch togglefloating address:{addr}")
                                    def do_resize():
                                        if cmds:
                                            subprocess.run(
                                                ['hyprctl', '--batch', ';'.join(cmds)],
                                                stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL
                                            )
                                            time.sleep(0.1)
                                        subprocess.run(
                                            ['hyprctl', '--batch',
                                             f"dispatch resizewindowpixel exact {w} {h},address:{addr};dispatch centerwindow"],
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL
                                        )
                                    threading.Thread(target=do_resize, daemon=True).start()
                                except:
                                    pass
                            threading.Thread(target=pseudo_fullscreen, daemon=True).start()
        except:
            break

def mouse_reader(dev_path):
    global acc_x, acc_y, btn_left
    last_abs_x = None
    last_abs_y = None
    try:
        fd = open(dev_path, 'rb')
    except:
        return
    while True:
        try:
            data = fd.read(EVENT_SIZE)
            if not data or len(data) < EVENT_SIZE:
                break
            _, _, etype, code, value = struct.unpack('llHHi', data)
            with lock:
                if etype == EV_KEY:
                    if code in (BTN_LEFT, BTN_TOUCH):
                        btn_left = (value == 1)
                        wakeup_event.set()
                        if not btn_left:
                            last_abs_x = None
                            last_abs_y = None
                elif etype == EV_REL:
                    if super_pressed and alt_pressed and btn_left:
                        sign = -1 if read_inverted() else 1
                        if code == REL_X:
                            acc_x += value * mouse_speed * sign
                        elif code == REL_Y:
                            acc_y += value * mouse_speed * sign
                        wakeup_event.set()
                    elif btn_left:
                        refresh_event.set()
                elif etype == EV_ABS:
                    if super_pressed and alt_pressed and btn_left:
                        sign = -1 if read_inverted() else 1
                        if code == ABS_X:
                            if last_abs_x is not None:
                                diff = value - last_abs_x
                                if abs(diff) < 1500:
                                    acc_x += diff * trackpad_speed * sign * 0.5
                            last_abs_x = value
                        elif code == ABS_Y:
                            if last_abs_y is not None:
                                diff = value - last_abs_y
                                if abs(diff) < 1500:
                                    acc_y += diff * trackpad_speed * sign * 0.5
                            last_abs_y = value
                        wakeup_event.set()
                    elif btn_left:
                        if code == ABS_X:
                            last_abs_x = value
                        elif code == ABS_Y:
                            last_abs_y = value
                        refresh_event.set()
                    else:
                        last_abs_x = None
                        last_abs_y = None
        except:
            break

def get_active_window(clients):
    for w in clients:
        if w.get('focused', False):
            return w
    return None

def sync_positions(floating_windows):
    global window_positions
    current_addresses = {w['address'] for w in floating_windows}
    window_positions = {addr: pos for addr, pos in window_positions.items() if addr in current_addresses}
    for w in floating_windows:
        addr = w['address']
        ax, ay = float(w['at'][0]), float(w['at'][1])
        aw, ah = float(w['size'][0]), float(w['size'][1])
        fs = bool(w.get('fullscreen', False))
        if addr not in window_positions:
            window_positions[addr] = {
                'target_x': ax,
                'target_y': ay,
                'sx': ax,
                'sy': ay,
                'w': aw,
                'h': ah,
                'fullscreen': fs
            }
        else:
            window_positions[addr]['w'] = aw
            window_positions[addr]['h'] = ah
            window_positions[addr]['fullscreen'] = fs
            dev_x = abs(ax - window_positions[addr]['sx'])
            dev_y = abs(ay - window_positions[addr]['sy'])
            if dev_x > 5.0 or dev_y > 5.0:
                is_anim = abs(window_positions[addr]['target_x'] - window_positions[addr]['sx']) > 1.0 or \
                          abs(window_positions[addr]['target_y'] - window_positions[addr]['sy']) > 1.0
                if not is_anim or (btn_left and (addr == dragged_window_addr or w.get('focused', False))):
                    window_positions[addr]['target_x'] = ax
                    window_positions[addr]['target_y'] = ay
                    window_positions[addr]['sx'] = ax
                    window_positions[addr]['sy'] = ay

def resolve_collisions(tracked, active_addr):
    for _ in range(8):
        moved = False
        for addr1 in list(tracked.keys()):
            for addr2 in list(tracked.keys()):
                if addr1 == addr2:
                    continue
                w1 = tracked[addr1]
                w2 = tracked[addr2]
                if w1.get('fullscreen') or w2.get('fullscreen'):
                    continue
                x1_1, y1_1 = w1['target_x'], w1['target_y']
                x1_2, y1_2 = x1_1 + w1['w'], y1_1 + w1['h']
                x2_1, y2_1 = w2['target_x'], w2['target_y']
                x2_2, y2_2 = x2_1 + w2['w'], y2_1 + w2['h']
                overlap_x = min(x1_2, x2_2) - max(x1_1, x2_1) + GAP
                overlap_y = min(y1_2, y2_2) - max(y1_1, y2_1) + GAP
                if overlap_x > 0 and overlap_y > 0:
                    if overlap_x < overlap_y:
                        cx1 = x1_1 + w1['w'] / 2.0
                        cx2 = x2_1 + w2['w'] / 2.0
                        dx = overlap_x
                        if cx2 < cx1:
                            dx = -dx
                        if addr1 == active_addr:
                            w2['target_x'] += dx
                        elif addr2 == active_addr:
                            w1['target_x'] -= dx
                        else:
                            w1['target_x'] -= dx * 0.5
                            w2['target_x'] += dx * 0.5
                    else:
                        cy1 = y1_1 + w1['h'] / 2.0
                        cy2 = y2_1 + w2['h'] / 2.0
                        dy = overlap_y
                        if cy2 < cy1:
                            dy = -dy
                        if addr1 == active_addr:
                            w2['target_y'] += dy
                        elif addr2 == active_addr:
                            w1['target_y'] -= dy
                        else:
                            w1['target_y'] -= dy * 0.5
                            w2['target_y'] += dy * 0.5
                    moved = True
        if not moved:
            break

def update_cache():
    global cached_workspace_id, cached_clients, cached_monitors, last_workspace_id, window_positions
    try:
        r = subprocess.run(['hyprctl', 'activeworkspace', '-j'], capture_output=True, text=True, timeout=0.1)
        ws = json.loads(r.stdout)
        workspace_id = ws['id']
        r = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=0.1)
        clients = json.loads(r.stdout)
        r = subprocess.run(['hyprctl', 'monitors', '-j'], capture_output=True, text=True, timeout=0.1)
        monitors = json.loads(r.stdout)
        with cache_lock:
            cached_workspace_id = workspace_id
            cached_clients = clients
            cached_monitors = monitors
        with lock:
            if workspace_id != last_workspace_id:
                window_positions.clear()
                last_workspace_id = workspace_id
            floating_windows = [w for w in clients if w.get('floating') and w.get('workspace', {}).get('id') == workspace_id]
            sync_positions(floating_windows)
    except:
        pass

def cache_manager():
    while True:
        refresh_event.wait(timeout=2.0)
        refresh_event.clear()
        with lock:
            skip = panning
        if not skip:
            update_cache()
            time.sleep(0.1)

def hyprland_event_listener():
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return
    path = None
    if xdg_runtime:
        p = os.path.join(xdg_runtime, "hypr", sig, ".socket2.sock")
        if os.path.exists(p):
            path = p
    if not path:
        p = os.path.join("/tmp/hypr", sig, ".socket2.sock")
        if os.path.exists(p):
            path = p
    if not path:
        return
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            while True:
                data = s.recv(4096)
                if not data:
                    break
                refresh_event.set()
        except:
            time.sleep(1.0)

def get_all_keyboards():
    kbds = []
    for dev in sorted(glob.glob('/dev/input/event*')):
        try:
            with open('/sys/class/input/' + os.path.basename(dev) + '/device/name') as f:
                name = f.read().strip().lower()
            if 'keyboard' in name or 'kbd' in name or 'receiver' in name or 'at translated' in name:
                kbds.append(dev)
        except: pass
    return list(set(kbds))

def get_all_mice():
    mice = []
    for dev in sorted(glob.glob('/dev/input/event*')):
        try:
            with open('/sys/class/input/' + os.path.basename(dev) + '/device/name') as f:
                name = f.read().strip().lower()
            if 'touchpad' in name or 'mouse' in name or 'receiver' in name:
                mice.append(dev)
        except: pass
    return list(set(mice))

update_cache()

active_keyboards = set()
active_mice = set()

def hotplug_monitor():
    while True:
        current_kbds = set(get_all_keyboards() if kbd_dev == "auto" else [kbd_dev])
        current_mice = set(get_all_mice() if mouse_dev == "auto" else [mouse_dev])
        new_kbds = current_kbds - active_keyboards
        for kb in new_kbds:
            active_keyboards.add(kb)
            threading.Thread(target=kbd_reader, args=(kb,), daemon=True).start()
        new_mice = current_mice - active_mice
        for m in new_mice:
            active_mice.add(m)
            threading.Thread(target=mouse_reader, args=(m,), daemon=True).start()
        time.sleep(2.0)

threading.Thread(target=hotplug_monitor, daemon=True).start()
threading.Thread(target=cache_manager, daemon=True).start()
threading.Thread(target=hyprland_event_listener, daemon=True).start()

was_active_or_animating = False

while True:
    is_active = False
    with lock:
        if (super_pressed and alt_pressed) or btn_left:
            is_active = True
    idx = 0
    idy = 0
    with lock:
        if super_pressed and alt_pressed:
            idx = int(round(acc_x))
            idy = int(round(acc_y))
            acc_x -= idx
            acc_y -= idy
        else:
            acc_x = 0.0
            acc_y = 0.0
    try:
        with cache_lock:
            workspace_id = cached_workspace_id
            clients = cached_clients
        if btn_left:
            if not dragged_window_addr:
                focused = next((w for w in clients if w.get('focused', False)), None)
                if focused:
                    dragged_window_addr = focused['address']
        else:
            dragged_window_addr = None
        floating_windows = [w for w in clients if w.get('floating') and w.get('workspace', {}).get('id') == workspace_id]
        if not floating_windows:
            wakeup_event.clear()
            wakeup_event.wait(timeout=0.2)
            continue
        if dragged_window_addr:
            active = next((w for w in floating_windows if w['address'] == dragged_window_addr), None)
        else:
            active = get_active_window(floating_windows)
        native_drag = False
        if active and btn_left and not (super_pressed and alt_pressed):
            native_drag = True
        if not active and btn_left:
            try:
                focused_client = next((w for w in clients if w.get('focused', False)), None)
                if focused_client and not focused_client.get('floating', False):
                    addr = focused_client['address']
                    if addr not in auto_floated_windows:
                        auto_floated_windows.add(addr)
                        with cache_lock:
                            monitors = cached_monitors
                        mon = next((m for m in monitors if m.get('id') == focused_client.get('monitor', 0)), monitors[0])
                        scale = mon.get('scale', 1.0)
                        full_w = int(mon['width'] / scale) - 2
                        full_h = int(mon['height'] / scale) - 2
                        def float_and_resize():
                            subprocess.run(['hyprctl', 'dispatch', 'togglefloating', f'address:{addr}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            time.sleep(0.1)
                            cmds = [
                                f"dispatch resizewindowpixel exact {full_w} {full_h},address:{addr}",
                                f"dispatch centerwindow"
                            ]
                            subprocess.run(['hyprctl', '--batch', ';'.join(cmds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        threading.Thread(target=float_and_resize, daemon=True).start()
            except:
                pass
        batch_cmds = []
        if active and btn_left and (super_pressed and alt_pressed):
            addr = active['address']
            if addr in window_positions:
                window_positions[addr]['target_x'] += idx
                window_positions[addr]['target_y'] += idy
                window_positions[addr]['sx'] += idx
                window_positions[addr]['sy'] += idy
                batch_cmds.append(f"dispatch movewindowpixel {idx} {idy},address:{addr}")
        elif (idx != 0 or idy != 0) and (super_pressed and alt_pressed):
            for w in floating_windows:
                addr = w['address']
                if addr in window_positions:
                    window_positions[addr]['target_x'] += idx
                    window_positions[addr]['target_y'] += idy
                    window_positions[addr]['sx'] += idx
                    window_positions[addr]['sy'] += idy
                batch_cmds.append(f"dispatch movewindowpixel {idx} {idy},address:{addr}")
        if active:
            resolve_collisions(window_positions, active_addr=active['address'])
        else:
            resolve_collisions(window_positions, active_addr=None)
        k = 0.25
        for addr, win in window_positions.items():
            if native_drag and addr == active['address']:
                continue
            tx, ty = win['target_x'], win['target_y']
            sx, sy = win['sx'], win['sy']
            step_x = (tx - sx) * k
            step_y = (ty - sy) * k
            if abs(tx - sx) < 0.5:
                step_x = tx - sx
            if abs(ty - sy) < 0.5:
                step_y = ty - sy
            if abs(step_x) > 0.01 or abs(step_y) > 0.01:
                prev_ix = int(round(sx))
                prev_iy = int(round(sy))
                win['sx'] += step_x
                win['sy'] += step_y
                new_ix = int(round(win['sx']))
                new_iy = int(round(win['sy']))
                ix = new_ix - prev_ix
                iy = new_iy - prev_iy
                if ix != 0 or iy != 0:
                    batch_cmds.append(f"dispatch movewindowpixel {ix} {iy},address:{addr}")
        if batch_cmds:
            subprocess.Popen(['hyprctl', '--batch', ';'.join(batch_cmds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
    wakeup_event.clear()
    is_active = False
    with lock:
        if (super_pressed and alt_pressed) or btn_left:
            is_active = True
    animating = False
    for addr, win in window_positions.items():
        if abs(win['target_x'] - win['sx']) > 0.1 or abs(win['target_y'] - win['sy']) > 0.1:
            animating = True
            break
    with lock:
        is_animating = animating
        panning = bool(super_pressed and alt_pressed and btn_left)
    current_active_or_animating = is_active or animating
    if was_active_or_animating and not current_active_or_animating:
        refresh_event.set()
    was_active_or_animating = current_active_or_animating
    if is_active or animating:
        wakeup_event.wait(timeout=0.016)
    else:
        wakeup_event.wait(timeout=0.2)