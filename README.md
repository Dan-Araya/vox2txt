# vox2txt

Global push-to-talk dictation. Hold a key, speak, release — the text is pasted straight into whatever window has focus.

Runs fully offline using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Nothing is sent anywhere.

## Install

Both platforms use [uv](https://docs.astral.sh/uv/), which also installs Python for you if you don't have it.

**Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install vox2txt
vox2txt setup      # one-time: input permissions + optional autostart
vox2txt
```

**Windows** (PowerShell)

`winget` is the path that has actually been used. The `irm | iex` installer that
uv's own docs give works too, but it depends on the execution policy allowing it.

```powershell
winget install --id=astral-sh.uv -e
uv tool install vox2txt
vox2txt
```

Reopen PowerShell after the `winget` line, otherwise `uv` is not on `PATH` yet.

Until the package is on PyPI, install it from the repository instead — that needs
git, which a fresh Windows box does not have either:

```powershell
winget install --id Git.Git -e
uv tool install git+https://github.com/Dan-Araya/vox2txt
```

Windows needs no permission setup. Run `vox2txt setup` only if you want it to start automatically at login.

Prefer `pipx`? `pipx install vox2txt` works the same way.

## Use

Hold **Alt Gr**, speak, release. The transcription lands in the focused window.

First run downloads the model (142 MB for `base`). After that everything is local.

```
vox2txt            # start it
vox2txt doctor     # check microphone, hotkey, paste and clipboard
vox2txt config     # print the config file path
vox2txt setup      # permissions and autostart
```

## Configuration

`vox2txt config` prints the path — `~/.config/vox2txt/config.toml` on Linux, `%APPDATA%\vox2txt\config.toml` on Windows.

```toml
[hotkey]
key = "alt_gr"          # "alt_gr" | "right_ctrl" | "scroll_lock" -- these three only

[transcription]
model = "base"          # tiny | base | small | medium | large
language = "auto"       # "auto", or a code like "es", "en", "fr"
device = "auto"         # "auto" | "cpu" | "cuda"
compute_type = "auto"   # "auto" = int8 on CPU, float16 on CUDA
vad_filter = true       # trim silence so Whisper stops inventing text

[paste]
mode = "auto"           # "auto" = paste immediately | "clipboard_only" = just copy
shortcut = "ctrl+v"     # "ctrl+v" for GUI apps | "ctrl+shift+v" for terminals
notify = true
```

The hotkey is a closed list of three keys, not an arbitrary key name, and it
cannot be a combination — push-to-talk needs a key that is held down and does
nothing else while held, which rules out most of the keyboard. Anything outside
that list fails at startup with `Unsupported key`.

### Choosing the paste shortcut

There is no combination that works everywhere. Measured on GNOME 47:

| Shortcut | GUI apps (GTK entry) | Terminal (VTE) |
|---|---|---|
| `ctrl+v` | pastes | **no** — readline shows a literal `^V` |
| `ctrl+shift+v` | **no** | pastes |
| `shift+insert` | — | pastes the *primary selection*, not the clipboard |

The default is `ctrl+v` because most dictation targets are GUI apps. If you
mostly dictate into a terminal, set `shortcut = "ctrl+shift+v"`.

If you split your time, the better fix is on the terminal side: rebind the
terminal's paste to Ctrl+V and then `ctrl+v` works everywhere. For GNOME
Terminal:

```bash
gsettings set \
  org.gnome.Terminal.Legacy.Keybindings:/org/gnome/terminal/legacy/keybindings/ \
  paste '<Control>v'
```

Leave `copy` alone — Ctrl+C must stay SIGINT. The only thing you give up is
readline's quoted-insert, which almost nobody uses. Other terminals have the
equivalent setting in their config (kitty, alacritty, foot, wezterm all do).

Setting `language` explicitly is noticeably faster than `auto`, which spends time detecting.

A `config.toml` in the current working directory takes precedence, which is handy when running from a checkout.

| Model  | Download | Speed    | Accuracy |
|--------|----------|----------|----------|
| tiny   | ~75 MB   | fastest  | lowest   |
| base   | 142 MB   | fast     | good     |
| small  | ~480 MB  | medium   | better   |
| medium | ~1.5 GB  | slow     | great    |
| large  | ~3 GB    | slowest  | best     |

Only `base` has been measured; the rest are approximate. `large` resolves to
`large-v3`.

## How it works on Linux

Wayland deliberately gives applications no way to read the keyboard globally or to synthesise keystrokes, so vox2txt goes to the kernel instead:

- **Hotkey** — reads `/dev/input` directly via evdev, which needs your user in the `input` group.
- **Paste** — creates a virtual keyboard on `/dev/uinput` and presses the configured shortcut on it. A udev rule tags that device `uaccess`, so logind grants access to whoever owns the active session; no group needed.

`vox2txt setup` does both. It prints every privileged command and asks before running anything:

```
/etc/udev/rules.d/99-vox2txt.rules   uinput access for the active session
/etc/modules-load.d/vox2txt.conf     load the uinput module at boot
usermod -aG input $USER              read access to /dev/input
```

The `input` group only takes effect on a **new login session** — log out and back in before the hotkey works.

A clipboard tool must be installed — `wl-clipboard` on Wayland, `xclip` on X11:

```bash
sudo dnf install wl-clipboard      # Fedora
sudo apt install wl-clipboard      # Debian, Ubuntu
sudo pacman -S wl-clipboard        # Arch
```

`vox2txt doctor` names the right package for your distro if it is missing.

### On X11

The hotkey uses `pynput` there instead of evdev, and it is **not** installed by
default. Add it:

```bash
uv tool install --with pynput vox2txt
```

Pasting uses `xdotool` if present and falls back to the same `/dev/uinput` path
as Wayland otherwise.

### Why not wtype or ydotool?

`wtype` needs the `zwp_virtual_keyboard_manager_v1` protocol, which GNOME/mutter does not implement. `ydotool` works but requires you to keep a `ydotoold` daemon running. Going straight to `/dev/uinput` needs neither.

## Troubleshooting

Start with `vox2txt doctor` — it checks each piece separately.

**In a terminal I get a literal `^V` instead of my text.** Ctrl+V is not paste
in a terminal — readline reads it as quoted-insert. See
[Choosing the paste shortcut](#choosing-the-paste-shortcut); either set
`shortcut = "ctrl+shift+v"` or rebind your terminal's paste to Ctrl+V.

**Nothing is pasted, but the text is on the clipboard.** Either the virtual keyboard could not be created — check `/dev/uinput` is writable and the `uinput` module is loaded (`lsmod | grep uinput`) — or the shortcut is wrong for the app you are pasting into.

**The hotkey does nothing.** You are probably not in the `input` group yet, or you have not logged out since being added.

**The hotkey fires while I am typing normally.** The default is Alt Gr, which on
Spanish, Latin American and most European layouts is how you type `@ \ | ~ [ ] { }`.
Set `key = "scroll_lock"` instead.

**It pastes into the wrong window.** The paste goes wherever focus is when transcription *finishes*, not when you started talking.

## Status

Developed and verified on Fedora 41 / GNOME 47 / Wayland. The core is not tied
to that: the hotkey reads `/dev/input` and the paste writes to `/dev/uinput`,
both kernel interfaces that work under any desktop, X11 or Wayland. Distros
without systemd fall back to a `GROUP="input"` udev rule.

Windows is **confirmed working**: install with uv, `doctor` green, and dictation
into Notepad and Google Docs with the default settings. Its `setup` — the
autostart shortcut — is still untested.

X11 and non-systemd distros are **implemented but not yet tested**.
See [TESTING.md](TESTING.md) for exactly what has been verified and
[TODO.md](TODO.md) for open items.

## Contributing

```bash
git clone https://github.com/Dan-Araya/vox2txt
cd vox2txt
uv venv && uv pip install -e .
.venv/bin/vox2txt doctor
```

For daily use from a checkout, `uv tool install --editable .` puts `vox2txt` on
your PATH while still pointing at the working tree.

## License

MIT
