import atexit
import os
import platform
import subprocess
import threading
import time


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _copy_to_clipboard(text: str):
    system = platform.system()
    if system == "Windows":
        subprocess.run("clip", input=text.encode("utf-16-le"), check=True, shell=True)
        return
    encoded = text.encode()
    if _is_wayland():
        try:
            subprocess.run(["wl-copy"], input=encoded, check=True, timeout=3)
        except FileNotFoundError:
            raise SystemExit(
                "wl-clipboard not found. Install it:\n"
                "  Fedora:  sudo dnf install wl-clipboard\n"
                "  Ubuntu:  sudo apt install wl-clipboard"
            )
    else:
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=encoded, check=True, timeout=3)
            return
        except FileNotFoundError:
            pass
        try:
            subprocess.run(["xsel", "--clipboard", "--input"], input=encoded, check=True, timeout=3)
        except FileNotFoundError:
            raise SystemExit(
                "No clipboard tool found. Install one:\n"
                "  Fedora:  sudo dnf install xclip\n"
                "  Ubuntu:  sudo apt install xclip"
            )


def _notify(title: str, body: str):
    system = platform.system()
    if system == "Windows":
        try:
            from plyer import notification
            notification.notify(app_name="vox2txt", title=title, message=body, timeout=4)
            return
        except Exception:
            pass
    else:
        try:
            subprocess.run(["notify-send", "-a", "vox2txt", title, body], check=False)
            return
        except FileNotFoundError:
            pass
    print(f"[vox2txt] {title}: {body}")


class _VirtualKeyboard:
    """A persistent uinput keyboard for injecting key combos on Wayland.

    Two details matter and both were learned the hard way:

    1. The device must live for the whole process. Creating a uinput device is
       asynchronous from the compositor's point of view — udev has to process
       the new node and mutter only then opens it. Measured on GNOME 47 that
       takes ~200ms cold. A device created and destroyed around a single
       keystroke is gone before anyone is listening, and the events vanish
       silently with no error.
    2. It must advertise a full keycode range. udev's input_id builtin only
       sets ID_INPUT_KEYBOARD (which is what makes libinput treat it as a real
       keyboard rather than a bare key-emitting gadget) when the device claims
       roughly the first 32 keycodes.
    """

    # Time for udev to process the node and the compositor to open it. Paid
    # once at startup, not per paste.
    _SETTLE = 0.6

    def __init__(self):
        self._ui = None
        self._lock = threading.Lock()
        self._failed = False

    def _ensure(self):
        if self._ui is not None or self._failed:
            return self._ui
        try:
            from evdev import UInput, ecodes as e
            # KEY_ESC(1) .. KEY_MICMUTE(248): a plausible full keyboard.
            caps = {e.EV_KEY: list(range(e.KEY_ESC, e.KEY_MICMUTE))}
            self._ui = UInput(caps, name="vox2txt-virtual-kbd", vendor=0x1209, product=0x764B)
            time.sleep(self._SETTLE)
        except PermissionError:
            self._failed = True
            print(
                "[vox2txt] Cannot open /dev/uinput. Grant access with either:\n"
                "  sudo setfacl -m u:$USER:rw /dev/uinput      (this boot only)\n"
                "  sudo usermod -aG input $USER                (permanent; needs re-login)"
            )
        except Exception as exc:
            self._failed = True
            print(f"[vox2txt] Could not create virtual keyboard: {exc}")
        return self._ui

    def warm_up(self):
        """Create the device ahead of first use so no paste pays the settle cost."""
        with self._lock:
            self._ensure()

    def tap(self, key, modifiers=()) -> bool:
        """Press modifiers + key, then release in reverse order."""
        with self._lock:
            ui = self._ensure()
            if ui is None:
                return False
            from evdev import ecodes as e
            try:
                sequence = [(m, 1) for m in modifiers] + [(key, 1), (key, 0)]
                sequence += [(m, 0) for m in reversed(modifiers)]
                for code, value in sequence:
                    ui.write(e.EV_KEY, code, value)
                    ui.syn()
                    # Apps debounce; back-to-back events in one frame can be
                    # coalesced or dropped by the client toolkit.
                    time.sleep(0.02)
                return True
            except Exception as exc:
                print(f"[vox2txt] Key injection failed: {exc}")
                return False

    def close(self):
        with self._lock:
            if self._ui is not None:
                self._ui.close()
                self._ui = None


_keyboard = _VirtualKeyboard()

# Without this the device is torn down by the garbage collector during
# interpreter shutdown, which prints a spurious traceback from evdev.
atexit.register(_keyboard.close)


def warm_up():
    """Pre-create the virtual keyboard. Safe to call on non-Wayland; it no-ops."""
    if _is_wayland() and platform.system() == "Linux":
        _keyboard.warm_up()


def _ydotool_ready() -> bool:
    socket = os.environ.get("YDOTOOL_SOCKET") or os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/tmp"), ".ydotool_socket"
    )
    # A stale socket file outlives a dead daemon, so its presence proves
    # nothing — only a successful connect does.
    import socket as socket_module
    sock = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    try:
        sock.settimeout(0.5)
        sock.connect(socket)
        return True
    except OSError:
        return False
    finally:
        sock.close()


DEFAULT_SHORTCUT = "ctrl+v"

_MODIFIER_ALIASES = {
    "ctrl": "LEFTCTRL",
    "control": "LEFTCTRL",
    "shift": "LEFTSHIFT",
    "alt": "LEFTALT",
    "super": "LEFTMETA",
    "meta": "LEFTMETA",
    "win": "LEFTMETA",
}


def _parse_shortcut(spec: str):
    """'ctrl+shift+v' -> (KEY_V, [KEY_LEFTCTRL, KEY_LEFTSHIFT])."""
    from evdev import ecodes as e

    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty paste shortcut: {spec!r}")
    *modifiers, key = parts

    codes = []
    for modifier in modifiers:
        name = _MODIFIER_ALIASES.get(modifier)
        if name is None:
            raise ValueError(f"unknown modifier {modifier!r} in {spec!r}")
        codes.append(e.ecodes[f"KEY_{name}"])

    key_name = f"KEY_{key.upper()}"
    if key_name not in e.ecodes:
        raise ValueError(f"unknown key {key!r} in {spec!r}")
    return e.ecodes[key_name], codes


def validate_shortcut(spec: str) -> None:
    """Raise ValueError if the configured shortcut cannot be parsed."""
    if platform.system() == "Windows" or not _is_wayland():
        return  # those paths parse the string themselves
    _parse_shortcut(spec)


def _simulate_paste_uinput(shortcut: str = DEFAULT_SHORTCUT) -> bool:
    """Inject the paste shortcut via /dev/uinput, falling back to ydotool."""
    try:
        key, modifiers = _parse_shortcut(shortcut)
    except (ImportError, ValueError) as exc:
        print(f"[vox2txt] {exc}")
        return False

    if _keyboard.tap(key, modifiers=modifiers):
        return True

    if _ydotool_ready():
        # ydotool speaks raw keycodes: press modifiers, tap, release in reverse.
        sequence = [f"{m}:1" for m in modifiers] + [f"{key}:1", f"{key}:0"]
        sequence += [f"{m}:0" for m in reversed(modifiers)]
        try:
            subprocess.run(["ydotool", "key", *sequence], check=True, timeout=3)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    return False


def _simulate_paste_pynput(shortcut: str) -> bool:
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        return False

    pynput_modifiers = {
        "ctrl": Key.ctrl, "control": Key.ctrl,
        "shift": Key.shift,
        "alt": Key.alt,
        "super": Key.cmd, "meta": Key.cmd, "win": Key.cmd,
    }
    parts = [p.strip().lower() for p in shortcut.split("+") if p.strip()]
    if not parts:
        return False
    *modifier_names, key_name = parts

    try:
        modifiers = [pynput_modifiers[m] for m in modifier_names]
    except KeyError as exc:
        print(f"[vox2txt] unknown modifier {exc} in paste shortcut {shortcut!r}")
        return False
    key = getattr(Key, key_name, key_name) if len(key_name) > 1 else key_name

    try:
        keyboard = Controller()
        time.sleep(0.05)
        for modifier in modifiers:
            keyboard.press(modifier)
        keyboard.press(key)
        keyboard.release(key)
        for modifier in reversed(modifiers):
            keyboard.release(modifier)
        return True
    except Exception as exc:
        print(f"[vox2txt] paste failed: {exc}")
        return False


def _simulate_paste(shortcut: str = DEFAULT_SHORTCUT):
    if platform.system() == "Windows":
        return _simulate_paste_pynput(shortcut)
    elif _is_wayland():
        return _simulate_paste_uinput(shortcut)
    else:
        # xdotool's key syntax happens to match ours exactly.
        try:
            subprocess.run(["xdotool", "key", shortcut], check=True, timeout=3)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return _simulate_paste_uinput(shortcut)


def paste(text: str, mode: str = "auto", notify: bool = True,
          shortcut: str = DEFAULT_SHORTCUT):
    if not text:
        return

    _copy_to_clipboard(text)
    preview = text if len(text) <= 60 else text[:57] + "..."

    if mode == "clipboard_only":
        if notify:
            _notify("vox2txt", f"Copied: {preview}")
        return

    pasted = _simulate_paste(shortcut)
    if pasted:
        if notify:
            _notify("vox2txt", f"Pasted: {preview}")
    else:
        if _is_wayland():
            hint = "could not inject Ctrl+V — check access to /dev/uinput"
        else:
            hint = "xdotool not found — install it with: sudo dnf install xdotool"
        print(f"[vox2txt] Paste failed: {hint}")
        if notify:
            _notify("vox2txt — clipboard only", f"Copied: {preview}\n{hint}")
