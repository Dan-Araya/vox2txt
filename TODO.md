# Pending

## Before the first release

- [x] **Replace the placeholder URLs.** Now `github.com/Dan-Araya/vox2txt`
      everywhere: `pyproject.toml`, `README.md` and `TESTING.md`.
- [x] **Add an MIT license file** and include it in both distribution formats.
- [x] **Add hardware-free automated tests** for config, platform-specific
      diagnostics, X11 setup and supervisor recovery.
- [x] **Update CI for current uv.** It now installs into setup-uv's active
      environment and uses `uvx` for `twine`; the next push must confirm that
      the GitHub Actions matrix is green.
- [x] **Confirm the default hotkey.** `alt_gr` remains the maintainer's choice.
      Its collision with normal typing on Spanish, Latin American and European
      layouts is documented, with `scroll_lock` and `right_ctrl` as alternatives.
- [x] **Do not configure PyPI trusted publishing.** GitHub-only
      for now. `publish.yml` has been removed.
- [ ] **Run the remaining manual release checks.** Real-microphone dictation on
      Linux now passes. Still needed: a clean GitHub install, autostart after a
      login/reboot, and a clean install of the release candidate on Windows.
      See `TESTING.md`.
- [ ] **Confirm external release state.** CI green after push, repository
      description/topics set, then create and install-test a `v0.1.0` tag.

## Open decisions

- [ ] **Ship a `.exe`?** Decided against for now. An unsigned PyInstaller build
      that installs a global keyboard hook and synthesises keystrokes is very
      likely to be flagged by Defender/SmartScreen, would weigh 300-500 MB
      because of the CTranslate2 native libraries, and a console `.exe` is no
      better than a terminal command without a tray icon. Revisit only if
      non-developer Windows users actually ask.
- [ ] **X11 could use uinput too.** The Wayland paste path (`/dev/uinput`)
      works just as well under X11, so the `xdotool` dependency could be
      dropped. Currently X11 still shells out to `xdotool`.

## Missing functionality

- [ ] **No way to test the pipeline without a microphone.** This matters for
      VM testing, where audio input is often unavailable. A `vox2txt doctor
      --paste-test` (inject Ctrl+V and report) or a "transcribe this WAV"
      subcommand would make the tool testable on a machine with no mic.
      See `TESTING.md` for the manual workaround.
- [ ] `hotkey.py` supports exactly three keys (`alt_gr`, `right_ctrl`,
      `scroll_lock`). Arbitrary keys and combinations are not supported, and
      the three cannot be combined with each other either. Deliberately left
      as is: the three work, and push-to-talk needs a key that can be held
      without doing anything else, which excludes most of the keyboard.
      Adding more is a small change — one entry in each of the two maps in
      `hotkey.py` — so this is only worth doing when someone actually wants a
      key that is not on the list.

## Known rough edges

- **No paste shortcut works everywhere.** Measured on GNOME 47: `ctrl+v` pastes
  in GTK entries but not in VTE terminals (readline treats it as
  quoted-insert); `ctrl+shift+v` is the exact inverse; `shift+insert` pastes the
  primary selection rather than the clipboard, so it is useless here. The
  shortcut is configurable via `paste.shortcut` and defaults to `ctrl+v`.
  Auto-detecting the focused window would solve it, but
  `org.gnome.Shell.Introspect.GetWindows` refuses unlisted callers, and no
  Wayland protocol exposes the focused app. A GNOME extension could, at the
  cost of shipping an extension. The recommended way out is rebinding the
  terminal's paste to Ctrl+V, which the README documents.

- Paste lands wherever focus is when transcription *finishes*, not where it was
  when recording started. Inherent to the design; worth documenting rather than
  fixing.
- The `input` group only takes effect at next login. `vox2txt setup` warns, but
  people will still miss it.
- **vox2txt cannot start before someone logs in.** It needs a graphical session
  for the hotkey, the paste and the clipboard, so the systemd unit hangs off
  `graphical-session.target`. On a machine that boots to the login screen and
  waits, vox2txt waits too. Only GDM autologin would change that, and that is
  the user's security tradeoff to make, not ours.
- A transcription that fails is reported and dropped; the audio is not retried.
  Three failures in a row are treated as "this process is wedged" and it exits
  for the supervisor to restart, which loses nothing but is a guess.
- A `config.toml` in the working directory shadows the user config. Intentional
  for development, confusing if you run `vox2txt` from a checkout by accident.
- `av` (102 MB) and `onnxruntime` (53 MB) are hard dependencies of
  faster-whisper. We decode no files and only `onnxruntime` is genuinely used
  (for VAD), but neither can be dropped without vendoring.

## Things about the dev machine that will skew testing

**GNOME Terminal's paste has been rebound to Ctrl+V** there
(`org.gnome.Terminal.Legacy.Keybindings` → `paste`). That is the recommended
setup, but it means the `^V` problem will *not* reproduce on that machine.
Test the default shortcut behaviour on a fresh VM, or temporarily restore
`'<Control><Shift>v'`.

`/etc/udev/rules.d/51-android.rules` is malformed: a missing line-continuation
backslash turns its second line into an unconditional rule, so **236 of 254**
character devices end up mode `0666` — including `/dev/input/event*`,
`/dev/video0`, `/dev/snd/*` and `/dev/sda`. This is why hotkey capture works on
that machine without an active `input` group membership. Fixing it (put the
rule on one line) will break the hotkey until the next login. Not a vox2txt
bug, but it invalidates any permission testing done on that machine.
