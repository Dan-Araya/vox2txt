# Testing status and procedure

> This document is a **testing log and reference guide**. It lists every scenario
> the code path touches, not a set of release gates. vox2txt is a personal tool
> — it ships when it works on my machines. The VM checklist below is here for
> anyone curious enough to test on their own setup.

## What has actually been verified

All on one machine: Fedora 41, GNOME 47, Wayland, Python 3.13. The latest
real-microphone check was run on 2026-08-04 after reinstalling the package.

| Check | Result |
|---|---|
| Wheel builds, installs into a fresh venv | pass |
| `vox2txt` entry point resolves from outside the repo | pass |
| `uv tool install git+https://github.com/Dan-Araya/vox2txt`, into an isolated `UV_TOOL_DIR` | pass — resolved `afb2f06`, 386 MB, `--help` and `doctor` green |
| Hardware-free unit suite (`python -m unittest discover -v`) | pass — config, Wayland/X11 doctor paths, X11 setup and supervisor recovery |
| `vox2txt doctor` | 5/5 |
| Transcription of synthetic speech (base, int8, CPU) | 2.3 s for 3.8 s of audio |
| 1 s of silence | returns `""` — VAD suppresses the hallucination |
| Ctrl+V into a focused GTK4 window | pass, marker text landed in the entry |
| Ctrl+Shift+V into a focused GTK4 window | does **not** paste |
| Ctrl+V into gnome-terminal | does **not** paste |
| Ctrl+Shift+V into gnome-terminal | pass |
| Shift+Insert into gnome-terminal | pastes the *primary selection*, not the clipboard |
| `paste.shortcut` parser, valid and invalid input | pass, bad values rejected with a reason |
| `vox2txt` starts and reaches "ready" | pass |
| Real microphone → Spanish transcription → paste into focused chat | pass |
| `vox2txt setup` dry run (stdin closed) | lists correct, copy-pasteable commands |
| `vox2txt setup` run for real, sudo steps included | wrote the udev rule and `modules-load.d`, ran `usermod`, `modprobe`, `udevadm` |
| The `uaccess` branch of the udev rule | works — `getfacl /dev/uinput` shows `user:dan:rw-`, no group needed |
| Autostart unit installed and enabled | `active (running)`, started by `enable --now` |
| Dependency tree size | 388 MB |
| `base` model download | 142 MB |

The shortcut results are why `paste.shortcut` exists: no combination covers both
terminals and GUI apps, and they are exact inverses of each other.

One caveat on the permission rows: the `uaccess` result is trustworthy —
`/dev/uinput` is `0660` plus an ACL, so the ACL is doing the work. The `input`
group is **not** validated on this machine, because the malformed
`51-android.rules` described in `TODO.md` leaves every `/dev/input/event*` at
`0666`. The hotkey would read them with or without the group.

> Testing paste by spawning windows is unreliable on a machine someone is using
> — a stray window steals focus and the text lands somewhere else. Close every
> test window between runs, and check for orphans with
> `pgrep -af "read -r line"` before trusting a negative result.

### Automated checks

The CI matrix runs on Ubuntu and Windows with Python 3.10 and 3.13. It checks
installation, imports, the command entry point, configuration round-tripping and
the hardware-free unit suite:

```bash
python -m unittest discover -v
```

Those tests use fake keyboards, audio devices and listeners. They verify failure
handling and platform routing without pretending to prove that a real desktop,
microphone or global hotkey works.

## What has never been exercised

Be explicit about this, because it is most of the surface area.

- **`vox2txt setup` declining the sudo steps.** The accept path has now been
  run for real; the decline path is covered only by the fake-`sudo`-on-`PATH`
  procedure below, never by someone actually installing that way.
- **Autostart surviving a reboot.** The unit is installed, enabled and running,
  but it was started by `enable --now`, not by reaching
  `graphical-session.target` at login. That target is reached under GNOME and
  KDE, not under every bare window manager.
- **A real restart after a real failure.** `systemd-analyze --user verify`
  accepts the unit and the exit codes it reacts to are covered by the fake
  hotkey and fake transcriber described below, but no keyboard has been
  unplugged and no process killed on a live session.
- **The Windows launcher's retry loop.** The `.cmd` was rewritten to wait on
  the process and relaunch it up to five times; never executed.
- **Additional Windows environments.** The one Windows 11 machine below works,
  and a clean reinstall of the v0.1.0 candidate now passes on it, but no second
  machine has ever run this.
- **X11.** A different code path end to end: `pynput` for the hotkey (needs
  the `x11` extra) and `xdotool` for the paste.
- **Distros without systemd.** The `GROUP="input"` udev fallback is written
  but has never run.
- **CUDA**, models other than `base`, languages other than Spanish.
- **The ydotool fallback.** `_ydotool_ready()` was confirmed to reject a stale
  socket, but the fallback never fires in practice because uinput always
  succeeds first.
- **`mode = "clipboard_only"`** and the `notify-send` path on a desktop without
  a notification daemon.

## Windows

First contact, on a machine with neither uv nor git installed.

| Check | Result |
|---|---|
| `winget install --id=astral-sh.uv -e` | pass — the `irm \| iex` installer in uv's docs did not work here |
| `winget install --id Git.Git -e` | pass — needed because the package is unpublished, so it installs from git |
| `uv tool install`, entry point on `PATH` | pass |
| `vox2txt --help` | pass |
| `vox2txt doctor` | **crashed**: `ModuleNotFoundError: No module named 'grp'` |
| `vox2txt doctor`, after the fix | pass — microphone found, pynput present |
| Dictation into Notepad, Alt Gr held, no config file | pass — current default |
| Dictation into Google Docs | pass |

The crash was `setup_cmd.py` importing `grp` and `pwd` at module level. Both are
POSIX-only, so the module could not be imported at all on Windows, which took
`doctor` and `setup` down with it — `--help` survived because `cli.py` imports
that module lazily, per subcommand. They are now imported inside the three Linux
helpers that use them.

Note how little a green `doctor` proves on Windows: it checks that a microphone
exists and that `pynput` imports, and that is all. It never presses a key, never
injects a paste, never records. The Linux branch checks four things because it
has four things that can be denied; the Windows branch has no permissions to
verify, so it verifies almost nothing.

Those two dictation runs were the first end-to-end use of the tool. They cover
`Recorder` and its `sounddevice` stream, a real microphone, the pynput hotkey
and the pynput paste. They ran with no config file at all, on the built-in
defaults. The Linux evdev/uinput path has since also passed a real-microphone
end-to-end check.

Ctrl+V is the right default on Windows, unlike on Linux: it pastes in GUI apps
*and* in Windows Terminal, so `paste.shortcut` has no reason to be touched there.

Still untested on Windows: `vox2txt setup` and the startup shortcut it writes,
and the `plyer` notification — whether one appeared during those runs was not
recorded.

### Clean reinstall of the v0.1.0 candidate, 2026-08-05

Same Windows 11 machine, with the previous version removed first: `uv tool
uninstall vox2txt`, no `vox2txt.cmd` in the Startup folder, no config file left
behind. Run from a non-elevated PowerShell.

| Check | Result |
|---|---|
| `uv tool install git+https://github.com/Dan-Araya/vox2txt` | pass — resolved `afb2f06`, the commit `v0.1.0` tags |
| Platform markers | pass — `pynput` and `plyer` installed here, absent on Linux |
| `vox2txt doctor` with no config file at all | pass — 3/3, config reported as not created yet |
| First-run download of the `base` model | pass — no cached copy existed on this machine |
| Dictation into Notepad, Alt Gr held | pass |
| Dictation into PowerShell | pass — the Ctrl+V default does cover GUI *and* terminal |

This is the first install that followed the README literally instead of working
from a developer checkout, so it covers the `git+URL` path that CI never
exercises: CI installs `-e .` from a checkout it already has. The same path was
run on Linux the same day, isolated in a throwaway `UV_TOOL_DIR`.

`doctor` printing `(not created yet)` next to a green `config valid` reads as a
contradiction on first contact. It is accurate — the defaults are what gets
validated — but the wording is worth revisiting.

## Testing in virtual machines

### Which guests are worth the time

| Guest | What it actually exercises |
|---|---|
| Ubuntu 24.04, GNOME Wayland | `apt`, the most common target |
| Fedora KDE | KWin instead of mutter — a different compositor reading the virtual keyboard |
| Debian 12, X11 | the whole untested X11 path: pynput + xdotool |
| Arch | `pacman`, rolling versions of libinput and evdev |
| Void or Alpine | no systemd: exercises the `GROUP="input"` fallback and the skipped unit |

### Test the install the way a user will

Do not copy the repo into the guest. Once the code is pushed, install from
GitHub, the canonical install path:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv tool install git+https://github.com/Dan-Araya/vox2txt
```

For an X11 guest, use the documented X11 variant instead:

```bash
uv tool install git+https://github.com/Dan-Araya/vox2txt --with pynput
```

That catches packaging mistakes — missing modules, a broken entry point, a
dependency that only resolved locally — which copying a directory hides.

### Audio is the hard part

Most VMs have **no microphone** by default, and `vox2txt doctor` will fail on
the first check.

- **virt-manager / QEMU** — Add Hardware → Sound, model `ich9`. The guest
  needs a duplex codec (`hda-duplex`) for capture; output-only is the default
  in some versions.
- **VirtualBox** — Settings → Audio → tick **Enable Audio Input**. Off by
  default.
- **GNOME Boxes** — audio input support is limited; prefer virt-manager.

### Testing without a microphone

Everything except `Recorder` can be tested with synthetic audio. This is the
script used to validate the faster-whisper migration:

```python
import subprocess, numpy as np
from vox2txt.transcriber import Transcriber

wav = subprocess.run(["espeak-ng", "-v", "es", "-s", "140", "--stdout",
                      "hola, esto es una prueba"],
                     capture_output=True, check=True).stdout
raw = subprocess.run(["ffmpeg", "-i", "pipe:0", "-f", "f32le", "-ac", "1",
                      "-ar", "16000", "pipe:1"],
                     input=wav, capture_output=True, check=True).stdout

print(Transcriber("base", "es").transcribe(np.frombuffer(raw, dtype=np.float32)))
print(repr(Transcriber("base", "es").transcribe(np.zeros(16000, dtype=np.float32))))
```

`ffmpeg` and `espeak-ng` are needed for the test only, not at runtime.

The paste path can be checked independently with a GTK window that receives the
injected Ctrl+V — see the approach in the project history, or simply focus a
text editor and run `vox2txt` with `mode = "auto"`.

### Testing the restart paths without hardware

The point of the exit codes is that a supervisor can act on them, so what needs
checking is which failures reach `run()` as a non-zero return. Both halves can
be faked.

`on_lost` must fire when the *last* keyboard reader dies, not the first — patch
`evdev.list_devices` and `evdev.InputDevice` with objects whose `read_loop()`
raises `OSError` after a delay, pass two of them to `hotkey._start_evdev`, and
confirm a single call:

```python
class FakeDevice:
    def __init__(self, name, die_after): self.name, self._t = name, die_after
    def capabilities(self): return {ecodes.EV_KEY: [ecodes.KEY_RIGHTALT]}
    def read_loop(self):
        time.sleep(self._t); raise OSError(19, "No such device")
        yield
```

For `app.run()`, replace `app.Transcriber` with one whose `transcribe()` raises,
`app.Recorder` with a no-op, and `app.hotkey.start` with a stub that either
calls `on_lost` or drives `on_press`/`on_release` a few times. Three cases,
three expected exits:

| stub does | expected `run()` |
|---|---|
| calls `on_lost(...)` | `1` |
| three press/release cycles with a failing transcriber | `1` |
| sends itself `SIGTERM` | `0` |

The third matters as much as the other two: `Restart=on-failure` means a clean
stop has to exit 0, or `systemctl --user stop` would fight the restart policy.

Validate the unit itself with `systemd-analyze --user verify` on the rendered
`UNIT_TEMPLATE` — it catches directives in the wrong section, which is easy to
get wrong with `StartLimitIntervalSec` (it belongs in `[Unit]`, not
`[Service]`).

### Testing `vox2txt setup` without touching the system

Everything with an effect goes through `sudo`, `systemctl`, `udevadm` or
`modprobe`, so a directory of fakes at the front of `PATH` intercepts all of it,
and `_confirm` reads stdin, so the answers come from a pipe:

```bash
d=$(mktemp -d)
for c in sudo systemctl udevadm modprobe; do
  printf '#!/bin/sh\necho "%s $*" >> '"$d"'/calls\n' "$c" > "$d/$c"
  chmod +x "$d/$c"
done

printf 'n\nn\n' | PATH="$d:$PATH" .venv/bin/python -m vox2txt setup
cat "$d/calls" 2>/dev/null || echo "nothing ran, as it should"
```

To reach the root steps on a machine where they are already done, point the
paths at a temporary directory before calling `_setup_linux()`:
`setup_cmd.UDEV_RULE_PATH`, `MODULE_CONF_PATH`, `UINPUT_DEVICE`, `UNIT_PATH`,
plus stubs for `_input_group_member` and `_username`.

The property worth asserting is that **the two branches agree**: answer `y` with
the fake `sudo` in place, and every command in `$d/calls` must appear in what
answering `n` printed. A list you are invited to run by hand is only useful if
it is the same list. Check too that declining leaves the unit file unwritten,
and that `enable` drops `--now` when the permission steps are still pending.

### Gotchas specific to VMs

- **The VM viewer eats keys.** SPICE and VNC clients intercept some
  combinations. Scroll Lock in particular is often grabbed by the viewer and
  never reaches the guest. If the hotkey seems dead, try another key before
  assuming the code is broken.
- **Key auto-repeat.** Holding a key generates `value=2` events. `hotkey.py`
  only acts on `1` and `0`, so this is handled — but it is worth confirming
  that a long hold produces exactly one recording.
- **`/dev/uinput` needs no passthrough.** It is a kernel feature and works
  inside a guest normally. Confirm the module is loaded: `lsmod | grep uinput`.
- **Wayland in a VM** falls back to software rendering. Slow, but functional.
- **Do not trust permission testing done on the dev machine.** See the udev
  note at the end of `TODO.md`; that machine has world-readable input devices,
  which masks any permission bug. A clean VM is the correct place to verify
  that `vox2txt setup` genuinely grants what is needed.

### Checklist per guest

```
[ ] uv tool install git+https://github.com/Dan-Araya/vox2txt
[ ] vox2txt doctor                      -> note which checks fail and why
[ ] vox2txt setup                       -> commands correct for this distro?
[ ] log out and back in
[ ] vox2txt doctor                      -> now all green?
[ ] vox2txt, hold the hotkey, speak     -> text pasted into a focused editor
[ ] same again, into a terminal         -> does the configured shortcut suit it?
[ ] long hold                           -> exactly one recording, not several
[ ] hold and release with no speech     -> "No speech detected", no invented text
[ ] default Alt Gr                      -> one recording per hold while dictating
[ ] type @ or [ with an AltGr layout    -> known collision is visible and documented
[ ] autostart, if enabled               -> running after a reboot
[ ] systemctl --user kill -s KILL vox2txt  -> back up within ~5s, NRestarts=1
[ ] unplug and replug the keyboard      -> "Fatal: keyboard ... disappeared" in
                                           the journal, hotkey works again
[ ] break paste.shortcut, restart       -> failed (start-limit-hit) after 5 tries,
                                           not an endless loop
```
