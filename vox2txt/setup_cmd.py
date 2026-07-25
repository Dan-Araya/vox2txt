"""`vox2txt setup` and `vox2txt doctor`.

Everything privileged lives here, and nothing runs without showing the exact
command first and asking.
"""

import grp
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-vox2txt.rules")
MODULE_CONF_PATH = Path("/etc/modules-load.d/vox2txt.conf")
UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / "vox2txt.service"

# uaccess makes logind hand an ACL to whoever owns the active local session,
# so the paste works without adding anyone to a group. It needs logind, so
# distros without systemd or elogind get the plain group form instead.
# Stored without a trailing newline: printf's format string supplies it, which
# is the only form that survives being copy-pasted into a shell.
UDEV_RULE_UACCESS = (
    'KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", TAG+="uaccess"'
)
UDEV_RULE_GROUP = (
    'KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", '
    'GROUP="input", MODE="0660"'
)
MODULE_CONF = "uinput"

_PKG_COMMANDS = {
    "dnf": "sudo dnf install",
    "apt": "sudo apt install",
    "pacman": "sudo pacman -S",
    "zypper": "sudo zypper install",
    "apk": "sudo apk add",
    "xbps-install": "sudo xbps-install",
    "emerge": "sudo emerge",
}

# Same package, different name depending on who is packaging it.
_PKG_NAMES = {
    "wl-copy": {"default": "wl-clipboard"},
    "xclip": {"default": "xclip"},
}


def _has_logind() -> bool:
    """uaccess ACLs come from logind; without it we must fall back to a group."""
    return Path("/run/systemd/seats").is_dir() or Path("/run/elogind").exists()


def _has_systemd() -> bool:
    return Path("/run/systemd/system").is_dir()


def _install_hint(binary: str) -> str:
    names = _PKG_NAMES.get(binary, {})
    for manager, command in _PKG_COMMANDS.items():
        if shutil.which(manager):
            return f"{command} {names.get(manager, names.get('default', binary))}"
    return f"install '{binary}' with your package manager"

UNIT_TEMPLATE = """\
[Unit]
Description=vox2txt push-to-talk transcription
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart={exec_path}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
"""


def _username() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def _input_group_member() -> bool:
    """Listed in /etc/group. True as soon as usermod runs."""
    try:
        return _username() in grp.getgrnam("input").gr_mem
    except KeyError:
        return False


def _input_group_active() -> bool:
    """Actually granted to *this* process. Only true after a fresh login."""
    try:
        return grp.getgrnam("input").gr_gid in os.getgroups()
    except KeyError:
        return False


def _confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _run(cmd: list[str]) -> bool:
    print(f"  $ {shlex.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


def _sudo_write(path: Path, content: str) -> bool:
    """Write a root-owned file without going through a shell.

    Piping into `sudo tee` keeps the content out of the command line entirely,
    so nothing has to survive shell quoting.
    """
    print(f"  $ printf '%s\\n' {shlex.quote(content)} | sudo tee {path}")
    proc = subprocess.run(
        ["sudo", "tee", str(path)],
        input=(content + "\n").encode(),
        stdout=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _setup_linux() -> int:
    exec_path = shutil.which("vox2txt") or f"{sys.executable} -m vox2txt"

    udev_rule = UDEV_RULE_UACCESS if _has_logind() else UDEV_RULE_GROUP

    # (description, copy-pasteable command, thunk that performs it)
    root_steps = []
    if not UDEV_RULE_PATH.exists():
        root_steps.append((
            f"write {UDEV_RULE_PATH} so /dev/uinput is usable without root",
            f"printf '%s\\n' {shlex.quote(udev_rule)} | sudo tee {UDEV_RULE_PATH}",
            lambda: _sudo_write(UDEV_RULE_PATH, udev_rule),
        ))
    if _has_systemd() and not MODULE_CONF_PATH.exists():
        root_steps.append((
            f"write {MODULE_CONF_PATH} so the uinput module loads at boot",
            f"printf '%s\\n' {shlex.quote(MODULE_CONF)} | sudo tee {MODULE_CONF_PATH}",
            lambda: _sudo_write(MODULE_CONF_PATH, MODULE_CONF),
        ))
    if not _input_group_member():
        usermod = ["sudo", "usermod", "-aG", "input", _username()]
        root_steps.append((
            "add you to the 'input' group so the hotkey can read /dev/input",
            shlex.join(usermod),
            lambda cmd=usermod: _run(cmd),
        ))

    if root_steps:
        print("\nThese steps need root:\n")
        for description, display, _action in root_steps:
            print(f"  - {description}")
            print(f"      {display}")
        print()
        if not _confirm("Run them now with sudo?"):
            print("Skipped. You can run the commands above by hand.")
        else:
            for _description, _display, action in root_steps:
                if not action():
                    print("\n[!] That step failed. Stopping.")
                    return 1
            _run(["sudo", "modprobe", "uinput"])
            _run(["sudo", "udevadm", "control", "--reload-rules"])
            _run(["sudo", "udevadm", "trigger"])
    else:
        print("\n[ok] System permissions already in place.")

    print()
    if not _has_systemd():
        print("[--] No systemd here, so no autostart unit. Launch vox2txt from")
        print("     whatever your desktop uses for startup programs.")
    elif _confirm("Start vox2txt automatically when you log in?"):
        UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        UNIT_PATH.write_text(UNIT_TEMPLATE.format(exec_path=exec_path), encoding="utf-8")
        print(f"  wrote {UNIT_PATH}")
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", "vox2txt.service"])

    from .config import write_default_config

    print(f"\n[ok] Config file: {write_default_config()}")

    # Being listed in /etc/group is not the same as the session having the gid.
    # usermod takes effect only at the next login, so check both.
    if _input_group_member() and not _input_group_active():
        print(
            "\n[!] You are in the 'input' group, but this session predates that\n"
            "    change and does not have it yet. Log out and back in, otherwise\n"
            "    the hotkey will only work if /dev/input happens to be readable\n"
            "    by everyone."
        )
    print("\nDone. Run 'vox2txt' to start, or 'vox2txt doctor' to check everything.")
    return 0


def _setup_windows() -> int:
    exec_path = shutil.which("vox2txt")
    if exec_path is None:
        print("[!] Could not find the 'vox2txt' command on PATH.")
        return 1

    print("\n[ok] Windows needs no special permissions for hotkeys or pasting.")
    print()

    if _confirm("Start vox2txt automatically when you log in?"):
        startup = (
            Path(os.environ["APPDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        startup.mkdir(parents=True, exist_ok=True)
        launcher = startup / "vox2txt.cmd"
        launcher.write_text(f'@echo off\r\nstart "" /min "{exec_path}"\r\n', encoding="utf-8")
        print(f"  wrote {launcher}")
        print("  (it starts minimised; a console window will still appear in the taskbar)")

    from .config import write_default_config

    print(f"\n[ok] Config file: {write_default_config()}")
    print("\nDone. Run 'vox2txt' to start, or 'vox2txt doctor' to check everything.")
    return 0


def run_setup() -> int:
    if sys.platform == "win32":
        return _setup_windows()
    if sys.platform.startswith("linux"):
        return _setup_linux()
    print(f"[!] 'setup' has nothing to do on {sys.platform}. Just run 'vox2txt'.")
    return 0


def _check(label: str, ok: bool, hint: str = "") -> bool:
    print(f"  [{'ok' if ok else '!!'}] {label}")
    if not ok and hint:
        print(f"       {hint}")
    return ok


def run_doctor() -> int:
    from .config import config_path

    print("vox2txt doctor\n")
    ok = True

    # Audio input
    try:
        import sounddevice as sd

        has_input = any(d["max_input_channels"] > 0 for d in sd.query_devices())
        ok &= _check("microphone available", has_input, "No input device found.")
    except Exception as exc:
        ok &= _check("microphone available", False, f"sounddevice failed: {exc}")

    if sys.platform.startswith("linux"):
        wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        print(f"  [--] session: {'Wayland' if wayland else 'X11 or console'}")

        # Hotkey capture
        try:
            import evdev

            readable = []
            for path in evdev.list_devices():
                try:
                    dev = evdev.InputDevice(path)
                    if evdev.ecodes.KEY_RIGHTALT in dev.capabilities().get(evdev.ecodes.EV_KEY, []):
                        readable.append(dev.name)
                except (PermissionError, OSError):
                    continue
            ok &= _check(
                f"keyboard readable via evdev ({len(readable)} found)",
                bool(readable),
                "Run 'vox2txt setup', then log out and back in.",
            )
        except ImportError:
            ok &= _check("evdev installed", False, "pip install evdev")

        # Paste injection
        ok &= _check(
            "/dev/uinput writable",
            os.access("/dev/uinput", os.W_OK),
            "Run 'vox2txt setup'. If it still fails, check that the uinput module is loaded.",
        )

        # Clipboard
        tool = "wl-copy" if os.environ.get("WAYLAND_DISPLAY") else "xclip"
        ok &= _check(
            f"{tool} installed",
            shutil.which(tool) is not None,
            f"Install it: {_install_hint(tool)}",
        )
    else:
        try:
            import pynput  # noqa: F401

            ok &= _check("pynput installed", True)
        except ImportError:
            ok &= _check("pynput installed", False, "pip install pynput")

    path = config_path()
    print(f"  [--] config: {path}{'' if path.exists() else '  (not created yet)'}")

    print("\nAll good." if ok else "\nSome checks failed; see the hints above.")
    return 0 if ok else 1
