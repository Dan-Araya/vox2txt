"""`vox2txt setup` and `vox2txt doctor`.

Everything privileged lives here, and nothing runs without showing the exact
command first and asking.

Saying no is a supported way to use this command, not a dead end. Handing your
sudo password to a program you downloaded is a fair thing to refuse, so both
decision points spell out the do-it-yourself route *before* asking, and print
the full list of commands if you take it. The rule that keeps that honest: what
setup would run and what it tells you to run must be the same commands.
"""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-vox2txt.rules")
MODULE_CONF_PATH = Path("/etc/modules-load.d/vox2txt.conf")
UINPUT_DEVICE = Path("/dev/uinput")
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

# Restart=on-failure and not 'always': 'systemctl --user stop' and Ctrl+C both
# exit 0 and must stay stopped. StartLimit* caps the damage when the failure is
# instant and permanent (a bad config, say), which would otherwise retry every
# five seconds forever. PYTHONUNBUFFERED matters more than it looks: with no tty
# Python buffers stdout, so without it none of the diagnostics reach the journal
# until the process dies.
UNIT_TEMPLATE = """\
[Unit]
Description=vox2txt push-to-talk transcription
PartOf=graphical-session.target
After=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart={exec_path}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
SyslogIdentifier=vox2txt

[Install]
WantedBy=graphical-session.target
"""

# The Windows counterpart of Restart=on-failure. The launcher has to *wait* on
# the process to notice it died, so unlike the previous version it cannot use
# 'start /min' -- a console window stays visible.
WINDOWS_LAUNCHER = """\
@echo off
set tries=0
:loop
"{exec_path}"
if not errorlevel 1 exit /b 0
set /a tries+=1
if %tries% geq 5 exit /b 1
timeout /t 5 /nobreak >nul
goto loop
"""


# grp and pwd only exist on POSIX, so they are imported where they are used.
# Everything below is reached from the Linux path alone; importing them at the
# top would make this module unloadable on Windows, taking 'doctor' with it.


def _username() -> str:
    import pwd

    return pwd.getpwuid(os.getuid()).pw_name


def _input_group_member() -> bool:
    """Listed in /etc/group. True as soon as usermod runs."""
    import grp

    try:
        return _username() in grp.getgrnam("input").gr_mem
    except KeyError:
        return False


def _input_group_active() -> bool:
    """Actually granted to *this* process. Only true after a fresh login."""
    import grp

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


def _root_steps(udev_rule: str) -> list[tuple[str, str, object]]:
    """What still needs doing, as (description, visible command, thunk).

    The applying commands (modprobe, udevadm) belong in here rather than in the
    'yes' branch: a list you are invited to run by hand has to be sufficient on
    its own, and writing a udev rule without reloading it does nothing.
    """
    steps: list[tuple[str, str, object]] = []

    wrote_rule = not UDEV_RULE_PATH.exists()
    if wrote_rule:
        steps.append((
            f"write {UDEV_RULE_PATH} so /dev/uinput is usable without root",
            f"printf '%s\\n' {shlex.quote(udev_rule)} | sudo tee {UDEV_RULE_PATH}",
            lambda: _sudo_write(UDEV_RULE_PATH, udev_rule),
        ))
    if _has_systemd() and not MODULE_CONF_PATH.exists():
        steps.append((
            f"write {MODULE_CONF_PATH} so the uinput module loads at boot",
            f"printf '%s\\n' {shlex.quote(MODULE_CONF)} | sudo tee {MODULE_CONF_PATH}",
            lambda: _sudo_write(MODULE_CONF_PATH, MODULE_CONF),
        ))
    if not _input_group_member():
        usermod = ["sudo", "usermod", "-aG", "input", _username()]
        steps.append((
            "add you to the 'input' group so the hotkey can read /dev/input",
            shlex.join(usermod),
            lambda cmd=usermod: _run(cmd),
        ))

    if not UINPUT_DEVICE.exists():
        modprobe = ["sudo", "modprobe", "uinput"]
        steps.append((
            "load the uinput module now, without waiting for a reboot",
            shlex.join(modprobe),
            lambda cmd=modprobe: _run(cmd),
        ))
    if wrote_rule:
        for cmd in (["sudo", "udevadm", "control", "--reload-rules"],
                    ["sudo", "udevadm", "trigger"]):
            steps.append((
                "apply the rule just written",
                shlex.join(cmd),
                lambda cmd=cmd: _run(cmd),
            ))

    return steps


def _print_commands(commands, indent: str = "  ") -> None:
    for command in commands:
        print(f"{indent}{command}")


def _autostart_script(unit_text: str, enable_cmd: list[str]) -> str:
    """The autostart install as something you can paste into a shell."""
    return (
        f"mkdir -p {UNIT_PATH.parent}\n"
        f"cat > {UNIT_PATH} <<'EOF'\n"
        f"{unit_text}"
        "EOF\n"
        "systemctl --user daemon-reload\n"
        f"{shlex.join(enable_cmd)}"
    )


def _setup_linux() -> int:
    exec_path = shutil.which("vox2txt") or f"{sys.executable} -m vox2txt"

    udev_rule = UDEV_RULE_UACCESS if _has_logind() else UDEV_RULE_GROUP
    root_steps = _root_steps(udev_rule)

    # Commands the user is left to run themselves, gathered as we go.
    pending: list[str] = []

    if root_steps:
        print("\nThese steps need root:\n")
        for description, display, _action in root_steps:
            print(f"  - {description}")
            print(f"      {display}")
        print("\nYou can do this either way:\n")
        print("  a) Let setup run them. It calls sudo, so your password is typed")
        print("     here, inside vox2txt.")
        print("  b) Say no and run the commands above yourself, in another")
        print("     terminal. Nothing later in setup depends on having done it")
        print("     here.\n")

        if not _confirm("Run them now with sudo?"):
            pending = [display for _d, display, _a in root_steps]
            print("\nSkipped -- nothing was changed. Run these yourself, in order:\n")
            _print_commands(pending)
        else:
            for index, (_description, _display, action) in enumerate(root_steps):
                if not action():
                    print("\n[!] That step failed. Stopping. Still to do, by hand:\n")
                    _print_commands([d for _x, d, _y in root_steps[index:]])
                    return 1
    else:
        print("\n[ok] System permissions already in place.")

    print()
    autostart_pending = False
    if not _has_systemd():
        print("[--] No systemd here, so no autostart unit. Launch vox2txt from")
        print("     whatever your desktop uses for startup programs.")
    else:
        unit_text = UNIT_TEMPLATE.format(exec_path=exec_path)
        # '--now' would start vox2txt immediately, which cannot work while the
        # permission steps are still pending: it would fail, be restarted, and
        # hit the start limit. Without it the unit waits for the next login,
        # which is when the 'input' group takes effect anyway.
        enable_cmd = ["systemctl", "--user", "enable"]
        if not pending:
            enable_cmd.append("--now")
        enable_cmd.append("vox2txt.service")

        print(f"Autostart writes this unit to {UNIT_PATH}:\n")
        for line in unit_text.splitlines():
            print(f"  {line}")
        print("\nand then runs:\n")
        _print_commands(["systemctl --user daemon-reload", shlex.join(enable_cmd)])
        if pending:
            print("\n('--now' is left out: starting vox2txt before the permission")
            print(" steps above are done would only fail. Next login will do it.)")
        print("\nYou can do this either way:\n")
        print("  a) Let setup do it.")
        print("  b) Say no and write the file yourself with the block below.")
        print("     No sudo either way -- this is a user unit, under your home.\n")

        if _confirm("Start vox2txt automatically when you log in?"):
            UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            UNIT_PATH.write_text(unit_text, encoding="utf-8")
            print(f"  wrote {UNIT_PATH}")
            _run(["systemctl", "--user", "daemon-reload"])
            _run(enable_cmd)
            print("\n  It restarts itself on failure. To check on it:")
            print("    systemctl --user status vox2txt")
            print("    journalctl --user -u vox2txt -f")
        else:
            autostart_pending = True
            print("\nSkipped. To install it yourself, paste this:\n")
            print(_autostart_script(unit_text, enable_cmd))

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

    if pending or autostart_pending:
        print("\n[!] Setup did not finish -- you chose to do part of it yourself.")
        print("    Still to do:\n")
        if pending:
            _print_commands(pending, indent="      ")
        if autostart_pending:
            print("      the autostart block printed just above")
        if pending:
            print("\n    Then log out and back in: the 'input' group only applies")
            print("    to new sessions.")
        print("\n    'vox2txt doctor' will tell you when it is all in place.")
    else:
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
        launcher.write_text(
            WINDOWS_LAUNCHER.format(exec_path=exec_path).replace("\n", "\r\n"),
            encoding="utf-8",
        )
        print(f"  wrote {launcher}")
        print("  (a console window stays open; the launcher needs it to restart")
        print("   vox2txt if it exits with an error, up to 5 times)")

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
