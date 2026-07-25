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

- **Real microphone capture.** The transcription test fed a numpy array
  straight to `Transcriber`. `Recorder` and its `sounddevice` stream have
  never run. Daily use covers this immediately.
- **`vox2txt setup` actually executing.** Only the dry run was tested; the
  sudo steps were never run, so the udev rule and `modules-load.d` file have
  never been written by the tool.
- **The systemd user unit.** Never installed, never enabled, never confirmed
  to start at login. `graphical-session.target` is reached under GNOME and
  KDE but not under every bare window manager.
- **Windows.** Nothing at all.
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
uv tool install git+https://github.com/your-username/vox2txt
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
[ ] uv tool install git+https://github.com/your-username/vox2txt
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
