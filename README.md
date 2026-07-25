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

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install vox2txt
vox2txt
```

Windows needs no permission setup. Run `vox2txt setup` only if you want it to start automatically at login.

Prefer `pipx`? `pipx install vox2txt` works the same way.

## Use

Hold **Alt Gr**, speak, release. The transcription lands in the focused window.

First run downloads the model (~145 MB for `base`). After that everything is local.

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
key = "alt_gr"          # "alt_gr" | "right_ctrl" | "scroll_lock"

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
| base   | ~145 MB  | fast     | good     |
| small  | ~480 MB  | medium   | better   |
| medium | ~1.5 GB  | slow     | great    |
| large  | ~3 GB    | slowest  | best     |

## How it works on Linux

Wayland deliberately gives applications no way to read the keyboard globally or to synthesise keystrokes, so vox2txt goes to the kernel instead:

- **Hotkey** — reads `/dev/input` directly via evdev, which needs your user in the `input` group.
- **Paste** — creates a virtual keyboard on `/dev/uinput` and types Ctrl+V into it. A udev rule tags that device `uaccess`, so logind grants access to whoever owns the active session; no group needed.

`vox2txt setup` does both. It prints every privileged command and asks before running anything:

```
/etc/udev/rules.d/99-vox2txt.rules   uinput access for the active session
/etc/modules-load.d/vox2txt.conf     load the uinput module at boot
usermod -aG input $USER              read access to /dev/input
```

The `input` group only takes effect on a **new login session** — log out and back in before the hotkey works.

`wl-clipboard` (Wayland) or `xclip` (X11) must be installed: `sudo dnf install wl-clipboard`.

### Why not wtype or ydotool?

`wtype` needs the `zwp_virtual_keyboard_manager_v1` protocol, which GNOME/mutter does not implement. `ydotool` works but requires you to keep a `ydotoold` daemon running. Going straight to `/dev/uinput` needs neither.

## Troubleshooting

Start with `vox2txt doctor` — it checks each piece separately.

**Nothing is pasted, but the text is on the clipboard.** The virtual keyboard could not be created. Check `/dev/uinput` is writable and the `uinput` module is loaded (`lsmod | grep uinput`).

**The hotkey does nothing.** You are probably not in the `input` group yet, or you have not logged out since being added.

**It pastes into the wrong window.** The paste goes wherever focus is when transcription *finishes*, not when you started talking.

## Status

Developed and verified on Fedora 41 / GNOME 47 / Wayland. The core is not tied
to that: the hotkey reads `/dev/input` and the paste writes to `/dev/uinput`,
both kernel interfaces that work under any desktop, X11 or Wayland. Distros
without systemd fall back to a `GROUP="input"` udev rule.

Windows, X11 and non-systemd distros are **implemented but not yet tested**.
See [TESTING.md](TESTING.md) for exactly what has been verified and
[TODO.md](TODO.md) for open items.

## Contributing

```bash
git clone https://github.com/your-username/vox2txt
cd vox2txt
uv venv && uv pip install -e .
.venv/bin/vox2txt doctor
```

For daily use from a checkout, `uv tool install --editable .` puts `vox2txt` on
your PATH while still pointing at the working tree.

## License

MIT
