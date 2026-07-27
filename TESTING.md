# Testing status and procedure

## What has actually been verified

All on one machine: Fedora 41, GNOME 47, Wayland, Python 3.13.

| Check | Result |
|---|---|
| Wheel builds, installs into a fresh venv | pass |
| `vox2txt` entry point resolves from outside the repo | pass |
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
| `vox2txt setup` dry run (stdin closed) | lists correct, copy-pasteable commands |
| Dependency tree size | 388 MB |
| `base` model download | 142 MB |

The shortcut results are why `paste.shortcut` exists: no combination covers both
terminals and GUI apps, and they are exact inverses of each other.

> Testing paste by spawning windows is unreliable on a machine someone is using
> — a stray window steals focus and the text lands somewhere else. Close every
> test window between runs, and check for orphans with
> `pgrep -af "read -r line"` before trusting a negative result.

## What has never been exercised

Be explicit about this, because it is most of the surface area.

- **Real microphone capture on Linux.** The transcription test fed a numpy
  array straight to `Transcriber`; `Recorder` and its `sounddevice` stream
  have never run there. They do work on Windows — see below — so the code is
  not wrong, but PortAudio is a different backend on each platform.
- **`vox2txt setup` actually executing.** Only the dry run was tested; the
  sudo steps were never run, so the udev rule and `modules-load.d` file have
  never been written by the tool.
- **The systemd user unit.** Never installed, never enabled, never confirmed
  to start at login. `graphical-session.target` is reached under GNOME and
  KDE but not under every bare window manager.
- **Windows.** Barely started — see the section below.
- **X11.** A different code path end to end: `pynput` for the hotkey (needs
  the `x11` extra) and `xdotool` for the paste.
- **Distros without systemd.** The `GROUP="input"` udev fallback is written
  but has never run.
- **CUDA**, models other than `base`, languages other than Spanish.
- **`uv tool install vox2txt`** from a real index — the package is unpublished.
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
| Dictation into Notepad, Alt Gr held, no config file | pass |
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

Those two dictation runs are the first end-to-end use of the tool on any
platform, and they cover more than every Linux check combined: `Recorder` and
its `sounddevice` stream, a real microphone, the pynput hotkey and the pynput
paste. They ran with no config file at all, on the built-in defaults.

Ctrl+V is the right default on Windows, unlike on Linux: it pastes in GUI apps
*and* in Windows Terminal, so `paste.shortcut` has no reason to be touched there.

Still untested on Windows: `vox2txt setup` and the startup shortcut it writes,
and the `plyer` notification — whether one appeared during those runs was not
recorded.

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
GitHub, which is the same path as PyPI minus the index:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install git+https://github.com/Dan-Araya/vox2txt
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
[ ] type @ or [ with an AltGr layout    -> does the default hotkey misfire?
[ ] autostart, if enabled               -> running after a reboot
```
