# finityren
<img width="1600" height="1000" alt="finityren" src="https://github.com/user-attachments/assets/46595fe9-6822-4175-90bd-c6489de3ff54" />

A highly optimized tool designed to transform your Hyprland workspace into an infinite canvas. This project refactors the core python daemon to introduce intelligent spatial navigation, tear-free window panning, and pixel-perfect absolute centering for all floating windows.

## Why this fork? (Comparison with Original)

| Feature | Original (`hyprland-infinite-desktop`) | This Fork (`finityren`) |
| :--- | :--- | :--- |
| **Navigation Logic** | Array-index based (cycles like Alt-Tab, ignores visual layout). | True spatial geometry (Euclidean distance & cone-angle detection). |
| **Window Movement** | Sequential dispatching (causes visual tearing/desync during rapid pans). | Atomic batch movements (`hyprctl --batch`) for perfect 1:1 synchronization. |
| **Centering Accuracy** | Relative center (pushes windows off-center if a top-bar like Waybar is present). | Absolute physical monitor centering utilizing logical pixels. |
| **Touchpad Support** | None (requires physical mouse clicks). | Native support for absolute-coordinate touchpads (touch-to-pan). |
| **Device Setup** | Manual configuration of raw event files (`/dev/input/event*`). | Automated zero-config input device detection (`auto` mode). |
| **State & Performance** | Repeated expensive IPC requests on every movement tick. | Optimized state caching and event-driven background refresh. |

## Features

- **Infinite Canvas Panning:** Move the entire layout of floating windows simultaneously by holding a modifier combination and moving the mouse or touchpad.
- **Intelligent Spatial Navigation:** Uses a directional geometric calculation to seamlessly transfer focus and fly to the physically closest window in the pressed direction.
- **Synchronized Batch Movements:** Ensures all floating windows shift atomically in a single frame, preventing desynced window coordinates.
- **Absolute Centering:** Calculates the exact physical center of the monitor, guaranteeing targeted windows align perfectly in the middle of the screen.
- **Application Protection:** Prevents specific applications (such as browsers) from losing focus accidentally during high-speed navigation.
- **Zero-Config Input Detection:** Automatically detects mouse, touchpad, and keyboard devices without requiring manual path entry.
- **State Caching & IPC Optimization:** Caches monitors and client states with background socket listeners to guarantee low latency and minimal resource usage.
- **Pseudo-Fullscreen Support:** Toggle floating, automatically resize, and center windows with custom scaling metrics.
- **Inverted Panning Toggle:** Toggle between normal and inverted movement physics dynamically.

## Requirements

The core daemon requires Python 3 and root-level input access to monitor device events.

### Dependencies
* **Arch Linux:**
  ```bash
  sudo pacman -S python
  ```
* **Fedora:**
  ```bash
  sudo dnf install python3
  ```
* **Ubuntu / Debian:**
  ```bash
  sudo apt install python3
  ```

### Permissions
The daemon reads raw events from `/dev/input/`. Your user must be a member of the input group:
```bash
sudo usermod -aG input $USER
```
*Note: A session restart or system reboot is required for group permission changes to take effect.*

## Installation

Clone the repository into your preferred directory and ensure execution permissions are granted to the shell scripts:

```bash
git clone https://github.com/Leshoraa/finityren.git
cd finityren
chmod +x *.sh
```

Copy the core files (`infinite-desktop.sh`, `infinite_desktop_core.py`, `infinite-desktop-toggle.sh`) to your dedicated scripts path, for example:
```bash
cp * ~/.config/hypr/UserScripts/
```

## Configuration

Integrate the daemon into your Hyprland initialization files (e.g., `Startup_Apps.conf` or `hyprland.conf`):

```hyprlang
# Launch the infinite desktop daemon
exec-once = python ~/.config/hypr/UserScripts/infinite_desktop_core.py auto auto 1.0
```

*Tip: For the cleanest aesthetic experience, consider disabling or lowering the `windowsMove` animation duration in your Hyprland decoration rules to eliminate rubber-banding or trailing effects during quick panning actions.*

## Usage

- **Panning (Mouse):** Hold `SUPER + ALT + Left Click` and move the mouse.
- **Panning (Touchpad):** Hold `SUPER + ALT` and slide your fingers on the touchpad (no click required).
- **Navigation:** Press `SUPER + ALT + Up/Down/Left/Right Arrow` to fly directly to the nearest window located in that visual direction.
- **Pseudo-Fullscreen:** Press `SUPER + ALT + SPACE` or `SUPER + ALT + F` to toggle floating, scale, and center the active window.
- **Invert Panning:** Run `infinite-desktop-toggle.sh` to toggle inverted panning coordinates on the fly.

## License

Distributed under the MIT License. Original repository logic by carlosareyesv204-cpu.