"""
Hotkey capture for X11 (pynput) and Wayland (evdev).

On Wayland this reads /dev/input directly, which needs read access to the
event devices — either group membership or an ACL:
    sudo usermod -aG input $USER   # permanent; then log out and back in
    sudo setfacl -m u:$USER:r /dev/input/event*   # this boot only
"""

import os
import threading
from typing import Callable

_KEY_MAP = {
    "alt_gr": "alt_gr",
    "right_ctrl": "right_ctrl",
    "scroll_lock": "scroll_lock",
}


def _start_pynput(key_name: str, on_press: Callable, on_release: Callable):
    try:
        from pynput import keyboard
    except ImportError:
        raise RuntimeError(
            "This session is not Wayland, so hotkey capture goes through pynput,\n"
            "which is not installed. Add it with:\n"
            "  uv tool install --with pynput vox2txt\n"
            "or, in a plain virtualenv:  pip install 'vox2txt[x11]'"
        )

    _PYNPUT_KEYS = {
        "alt_gr": keyboard.Key.alt_gr,
        "right_ctrl": keyboard.Key.ctrl_r,
        "scroll_lock": keyboard.Key.scroll_lock,
    }

    target = _PYNPUT_KEYS.get(key_name)
    if target is None:
        raise ValueError(f"Unsupported key: {key_name}")

    pressed = False

    def _on_press(key):
        nonlocal pressed
        if key == target and not pressed:
            pressed = True
            on_press()

    def _on_release(key):
        nonlocal pressed
        if key == target and pressed:
            pressed = False
            on_release()

    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.start()
    return listener


def _start_evdev(key_name: str, on_press: Callable, on_release: Callable):
    import evdev
    from evdev import ecodes

    _EVDEV_KEYS = {
        "alt_gr": ecodes.KEY_RIGHTALT,
        "right_ctrl": ecodes.KEY_RIGHTCTRL,
        "scroll_lock": ecodes.KEY_SCROLLLOCK,
    }

    target_code = _EVDEV_KEYS.get(key_name)
    if target_code is None:
        raise ValueError(f"Unsupported key: {key_name}")

    def find_keyboards():
        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if target_code in caps.get(ecodes.EV_KEY, []):
                    devices.append(dev)
            except (PermissionError, OSError):
                continue
        return devices

    keyboards = find_keyboards()
    if not keyboards:
        raise RuntimeError(
            "No keyboard found via evdev. Grant read access to /dev/input with either:\n"
            "  sudo usermod -aG input $USER   (permanent; log out and back in)\n"
            "  sudo setfacl -m u:$USER:r /dev/input/event*   (this boot only)"
        )

    pressed = False

    def _read(dev):
        nonlocal pressed
        try:
            for event in dev.read_loop():
                if event.type == ecodes.EV_KEY and event.code == target_code:
                    if event.value == 1 and not pressed:
                        pressed = True
                        on_press()
                    elif event.value == 0 and pressed:
                        pressed = False
                        on_release()
        except (OSError, evdev.device.EvdevError):
            pass

    threads = []
    for kb in keyboards:
        t = threading.Thread(target=_read, args=(kb,), daemon=True)
        t.start()
        threads.append(t)

    return threads


def start(key_name: str, on_press: Callable, on_release: Callable):
    """Start the global hotkey listener. Returns the listener object."""
    key_name = _KEY_MAP.get(key_name, key_name)

    if os.environ.get("WAYLAND_DISPLAY"):
        return _start_evdev(key_name, on_press, on_release)
    else:
        return _start_pynput(key_name, on_press, on_release)
