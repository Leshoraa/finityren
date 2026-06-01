import sys, struct, threading, time, subprocess, json, math
import fcntl, select

kbd_dev   = sys.argv[1]
mouse_dev = sys.argv[2]
speed     = float(sys.argv[3])
EVENT_SIZE = struct.calcsize('llHHi')

EV_KEY=1; EV_REL=2; REL_X=0; REL_Y=1
KEY_LEFTMETA=125; KEY_RIGHTMETA=126
KEY_LEFTALT=56; KEY_RIGHTALT=100
KEY_LEFTCTRL=29; KEY_RIGHTCTRL=97
KEY_UP=103; KEY_LEFT=105; KEY_RIGHT=106; KEY_DOWN=108
BTN_LEFT=272

STATE_FILE = "/tmp/infinite-desktop-state"
PROTECTED_APPS = ['brave-browser', 'chromium', 'chromium-browser', 'google-chrome',
                  'firefox', 'firefoxdeveloperedition', 'librewolf', 'vivaldi',
                  'opera', 'microsoft-edge']

lock=threading.Lock()
super_pressed=False; alt_pressed=False; ctrl_pressed=False; btn_left=False
acc_x=0.0; acc_y=0.0
last_nav_time = 0
NAV_COOLDOWN = 0.2

def read_inverted():
    try:
        with open(STATE_FILE) as f:
            return f.read().strip() == 'inverse'
    except:
        return False

def get_monitor_center():
    try:
        r = subprocess.run(['hyprctl', 'monitors', '-j'], capture_output=True, text=True, timeout=0.1)
        monitors = json.loads(r.stdout)
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
    except:
        pass
    return 960.0, 600.0

def get_floating_windows(workspace_id):
    try:
        r = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=0.1)
        return [w for w in json.loads(r.stdout) if w.get('floating') and w.get('workspace', {}).get('id') == workspace_id]
    except:
        return []

def is_protected_app(window):
    if not window:
        return False
    return any(app in window.get('class', '').lower() for app in PROTECTED_APPS)

def pan_to_window(floating_windows, target_addr, center_x, center_y):
    target_window = next((w for w in floating_windows if w['address'] == target_addr), None)
    if not target_window:
        return
    
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
        
    subprocess.Popen(['hyprctl', '--batch', ';'.join(batch_cmds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not is_protected_app(target_window):
        subprocess.Popen(['hyprctl', 'dispatch', 'focuswindow', f'address:{target_addr}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def change_focus(direction):
    global last_nav_time
    current_time = time.time()
    if current_time - last_nav_time < NAV_COOLDOWN:
        return
    last_nav_time = current_time
    try:
        r = subprocess.run(['hyprctl', 'activeworkspace', '-j'], capture_output=True, text=True, timeout=0.1)
        workspace_id = json.loads(r.stdout)['id']
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

def kbd_reader():
    global super_pressed, alt_pressed, ctrl_pressed
    fd = open(kbd_dev, 'rb')
    while True:
        data = fd.read(EVENT_SIZE)
        if not data or len(data) < EVENT_SIZE:
            break
        _, _, etype, code, value = struct.unpack('llHHi', data)
        if etype != EV_KEY or value == 2:
            continue
        with lock:
            if code in (KEY_LEFTMETA, KEY_RIGHTMETA):
                super_pressed = (value == 1)
            elif code in (KEY_LEFTALT, KEY_RIGHTALT):
                alt_pressed = (value == 1)
            elif code in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
                ctrl_pressed = (value == 1)

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

def mouse_reader():
    global acc_x, acc_y, btn_left
    fd = open(mouse_dev, 'rb')
    while True:
        data = fd.read(EVENT_SIZE)
        if not data or len(data) < EVENT_SIZE:
            break
        _, _, etype, code, value = struct.unpack('llHHi', data)
        with lock:
            if etype == EV_KEY and code == BTN_LEFT:
                btn_left = (value == 1)
            elif etype == EV_REL:
                if super_pressed and alt_pressed and btn_left:
                    sign = -1 if read_inverted() else 1
                    if code == REL_X:
                        acc_x += value * speed * sign
                    elif code == REL_Y:
                        acc_y += value * speed * sign

print("Preloading...", flush=True)
try:
    subprocess.run(['hyprctl', 'activeworkspace', '-j'], capture_output=True, text=True, timeout=0.5)
    subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=0.5)
except:
    pass
print("Ready! Moving windows...", flush=True)

threading.Thread(target=kbd_reader, daemon=True).start()
threading.Thread(target=mouse_reader, daemon=True).start()

while True:
    time.sleep(0.016)
    with lock:
        active_drag = super_pressed and alt_pressed and btn_left
        if not active_drag:
            acc_x = 0.0
            acc_y = 0.0
            continue

        idx = int(round(acc_x))
        idy = int(round(acc_y))

        if idx == 0 and idy == 0:
            continue

        acc_x -= idx
        acc_y -= idy

    try:
        r = subprocess.run(['hyprctl', 'activeworkspace', '-j'], capture_output=True, text=True, timeout=0.1)
        ws = json.loads(r.stdout)
        workspace_id = ws['id']
        r = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=0.1)
        clients = json.loads(r.stdout)
        
        batch_cmds = []
        for w in clients:
            if w.get('floating') and w.get('workspace', {}).get('id') == workspace_id:
                batch_cmds.append(f"dispatch movewindowpixel {idx} {idy},address:{w['address']}")
                
        if batch_cmds:
            subprocess.Popen(['hyprctl', '--batch', ';'.join(batch_cmds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass