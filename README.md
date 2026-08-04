# vox2txt

[![CI](https://github.com/Dan-Araya/vox2txt/actions/workflows/ci.yml/badge.svg)](https://github.com/Dan-Araya/vox2txt/actions/workflows/ci.yml)

Global push-to-talk dictation. Hold a key, speak, release — the text is pasted straight into whatever window has focus.

Runs fully offline using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Nothing is sent anywhere.

## Install

Both platforms need [uv](https://docs.astral.sh/uv/) (installs Python for you)
and Git. The commands below include both on a fresh machine.

Check your session type with `echo $XDG_SESSION_TYPE`, then use the matching
Linux path below.

**Linux — Wayland** (the default on current GNOME and KDE)

Install the two system libraries that Python cannot provide:

```bash
sudo dnf install git portaudio wl-clipboard          # Fedora
sudo apt install git libportaudio2 wl-clipboard      # Debian, Ubuntu
sudo pacman -S git portaudio wl-clipboard            # Arch
```

Then install vox2txt:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"  # make uv available in this terminal
uv tool install git+https://github.com/Dan-Araya/vox2txt
vox2txt setup      # one-time: input permissions + optional autostart
```

If setup added you to the `input` group, **log out and back in** so the new
permission takes effect. Then verify and start:

```bash
vox2txt doctor
vox2txt
```

On Wayland, `vox2txt setup` needs root for three things — a udev rule for `/dev/uinput`, the
`uinput` module, and adding you to the `input` group — and it calls `sudo`, so
your password would be typed inside vox2txt. You don't have to do that. It shows
you every command before asking, and if you say no it prints the complete list
for you to run in your own shell. Same for the autostart: it shows the unit file
and the commands, and declining leaves you a block you can paste. Nothing runs
without a yes.

**Linux — X11**

```bash
sudo dnf install git portaudio xclip xdotool          # Fedora
sudo apt install git libportaudio2 xclip xdotool      # Debian, Ubuntu
sudo pacman -S git portaudio xclip xdotool            # Arch

curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"  # make uv available in this terminal
uv tool install git+https://github.com/Dan-Araya/vox2txt --with pynput
vox2txt setup      # optional autostart; no kernel input permissions on X11
vox2txt
```

**Windows** (PowerShell)

```powershell
winget install --id=astral-sh.uv -e
winget install --id Git.Git -e
```

Close and reopen PowerShell so `uv` and `git` are on `PATH`, then run:

```powershell
uv tool install git+https://github.com/Dan-Araya/vox2txt
vox2txt
```

Windows needs no permission setup. Run `vox2txt setup` only if you want it to start automatically at login.

## Use

Hold **Alt Gr**, speak, release. The transcription lands in the focused window.

First run downloads the model (142 MB for `base`). After that everything is local.

```
vox2txt            # start it
vox2txt doctor     # check configuration and platform prerequisites
vox2txt config     # print the config file path
vox2txt setup      # permissions and autostart
```

## Running it in the background

`vox2txt setup` offers to start vox2txt automatically. It needs a logged-in
session — the hotkey, the paste and the clipboard all talk to your desktop — so
it starts at login, not at boot.

**Linux.** It writes a systemd user unit to
`~/.config/systemd/user/vox2txt.service`, hooked to `graphical-session.target`,
and enables it. To check on it:

```bash
systemctl --user status vox2txt        # is it running?
journalctl --user -u vox2txt -f        # what is it saying?
systemctl --user restart vox2txt       # after editing the config
```

Don't run `loginctl enable-linger` for this: it would have systemd start
vox2txt before a graphical session exists, and it would fail in a loop.

**Windows.** It writes `vox2txt.cmd` to the Startup folder. The console window
it opens has to stay: the launcher waits on the process so it can restart it.

### What restarts and what doesn't

vox2txt exits with a non-zero status — so the supervisor restarts it — only for
failures a fresh process actually fixes:

| | |
|---|---|
| Keyboard unplugged, hotkey listener dead | **restarts** (rescans `/dev/input`) |
| Virtual keyboard lost while running | **restarts** |
| Three failed transcriptions in a row | **restarts** |
| `wl-copy`/`xclip` not installed | stays up, notifies you |
| A single failed transcription | stays up, notifies you |
| Invalid config | exits; five attempts and it gives up |

Restarts are capped at 5 in 5 minutes, so a permanent failure ends in a stopped
service rather than a loop. Clearing it after fixing the cause:
`systemctl --user reset-failed vox2txt`.

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
that list fails at startup with `Unsupported key`. `alt_gr` is the default. On
Spanish, Latin American and many European layouts it also types symbols such as
`@`, `[` and `]`; choose `scroll_lock` or `right_ctrl` if that collision gets in
your way.

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

Membership in the `input` group allows reading all input devices assigned to
that group, not only the configured push-to-talk key. That commonly includes
full keyboard events. `vox2txt setup` shows the exact `usermod` command and lets
you decline so you can make that security decision yourself.

`vox2txt setup` does both. It prints every privileged command and asks before
running anything, and if you decline it prints the same list again for you to
run yourself:

```
/etc/udev/rules.d/99-vox2txt.rules   uinput access for the active session
/etc/modules-load.d/vox2txt.conf     load the uinput module at boot
usermod -aG input $USER              read access to /dev/input
modprobe uinput                      load the module now, not at next boot
udevadm control --reload-rules
udevadm trigger                      apply the rule just written
```

It only lists what is actually missing, so a second run is usually a no-op.

The `input` group only takes effect on a **new login session** — log out and back in before the hotkey works.

A clipboard tool must be installed — `wl-clipboard` on Wayland, `xclip` on X11.
The installation commands at the top include the appropriate one, and
`vox2txt doctor` names the right package if it is missing.

### On X11

The hotkey uses `pynput` there instead of evdev, and it is **not** installed by
default. If you already installed the Wayland variant, reinstall with the X11
dependency:

```bash
uv tool install --reinstall git+https://github.com/Dan-Araya/vox2txt --with pynput
```

Pasting uses `xdotool` if present and falls back to the same `/dev/uinput` path
as Wayland otherwise. The normal X11 path needs neither the `input` group nor
`/dev/uinput`; `vox2txt setup` only offers autostart there.

### Why not wtype or ydotool?

`wtype` needs the `zwp_virtual_keyboard_manager_v1` protocol, which GNOME/mutter does not implement. `ydotool` works but requires you to keep a `ydotoold` daemon running. Going straight to `/dev/uinput` needs neither.

## Troubleshooting

Start with `vox2txt doctor` — it checks each piece separately.

**In a terminal I get a literal `^V` instead of my text.** Ctrl+V is not paste
in a terminal — readline reads it as quoted-insert. See
[Choosing the paste shortcut](#choosing-the-paste-shortcut); either set
`shortcut = "ctrl+shift+v"` or rebind your terminal's paste to Ctrl+V.

**Nothing is pasted, but the text is on the clipboard.** Either the virtual keyboard could not be created — check `/dev/uinput` is writable and the `uinput` module is loaded (`lsmod | grep uinput`) — or the shortcut is wrong for the app you are pasting into.

**The hotkey does nothing.** Start with `vox2txt doctor`. On Wayland, you are
probably not in the `input` group yet or have not logged out since being added.
On X11, check that you installed the `pynput` variant. Running as a service,
`journalctl --user -u vox2txt` reports the fatal reason — vox2txt exits rather
than sitting there deaf.

**The hotkey fires while I am typing normally.** The default is Alt Gr, which on
Spanish, Latin American and most European layouts is how you type
`@ \ | ~ [ ] { }`. Set `key = "scroll_lock"` or `key = "right_ctrl"` if that
tradeoff does not suit you.

**It pastes into the wrong window.** The paste goes wherever focus is when transcription *finishes*, not when you started talking.

## Status

This is a personal tool — part of my [portfolio](https://dan-araya.github.io).
It solves *my* dictation needs and I publish it in case it solves yours too.
It is not a service, has no release schedule, and carries no support guarantees.

**What is verified:**

| Platform | Desktop | Path | Result |
|---|---|---|---|
| Fedora 41 | GNOME 47 / Wayland | evdev + uinput | dictation working end to end |
| Windows 11 | — | pynput | dictation working end to end |

**What should work but hasn't been tested:**

- **X11 sessions** — a different code path (pynput for the hotkey, xdotool or
  uinput for paste). The logic is there but no clean VM run yet.
- **Non-systemd distros** — the `GROUP="input"` udev fallback is written but
  hasn't run on a real machine without logind.
- **KDE / other Wayland compositors** — only GNOME/mutter has been exercised.

If you try it on one of those and it breaks, open an issue — I can't promise a
timeline, but I'll look into it.

[TESTING.md](TESTING.md) has the full list of what's been verified and
a checklist for anyone who wants to test on a different setup. [TODO.md](TODO.md)
tracks known rough edges and open decisions.

## Contributing

```bash
git clone https://github.com/Dan-Araya/vox2txt
cd vox2txt
uv venv && uv pip install -e .
.venv/bin/vox2txt doctor
.venv/bin/python -m unittest discover -v
```

For daily use from a checkout, `uv tool install --editable .` puts `vox2txt` on
your PATH while still pointing at the working tree.

## License

[MIT](LICENSE)
