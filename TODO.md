# Pending

## Before the first release

- [ ] **Replace the placeholder URLs.** `pyproject.toml` says `github.com/dan/vox2txt`
      and `README.md` says `your-username`. Both are wrong.
- [ ] **Configure PyPI trusted publishing** before pushing the first tag, at
      <https://pypi.org/manage/account/publishing/>: owner/repo, workflow
      `publish.yml`, environment `pypi`. Without it `publish.yml` fails at the
      last step. The name `vox2txt` was free on PyPI as of 2026-07-25.
- [ ] **Create the `pypi` environment** in the GitHub repo settings, or the
      workflow's `environment: pypi` will not resolve.
- [ ] Publishing is effectively irreversible: a yanked version cannot be
      reused. Tag `v0.1.0` only when the Windows run has been confirmed.

## Open decisions

- [ ] **Default hotkey.** `alt_gr` is a poor default outside US layouts. On
      Spanish and Latin American layouts AltGr produces `@ \ | ~ [ ] { }`, so
      ordinary typing starts a recording; the clip is near-silent, VAD returns
      `""` and the user gets a "No speech detected" notification. `scroll_lock`
      is unused on virtually every layout and would be a safer default, with
      `alt_gr` documented as an option. One line in `config.py` and one in
      `DEFAULT_CONFIG_TOML`. Not changed yet — this is the maintainer's call.
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
- [ ] No tests in CI beyond imports and entry-point resolution. There is no
      pytest suite; `ci.yml` only smoke-tests.
- [ ] `hotkey.py` supports exactly three keys (`alt_gr`, `right_ctrl`,
      `scroll_lock`). Arbitrary keys and combinations are not supported.

## Known rough edges

- **No paste shortcut works everywhere.** Measured on GNOME 47: `ctrl+v` pastes
  in GTK entries but not in VTE terminals (readline treats it as
  quoted-insert); `ctrl+shift+v` is the exact inverse; `shift+insert` pastes the
  primary selection rather than the clipboard, so it is useless here. The
  shortcut is configurable via `paste.shortcut` and defaults to `ctrl+v`.
  Auto-detecting the focused window would solve it, but
  `org.gnome.Shell.Introspect.GetWindows` refuses unlisted callers, and no
  Wayland protocol exposes the focused app. A GNOME extension could, at the
  cost of shipping an extension.

- Paste lands wherever focus is when transcription *finishes*, not where it was
  when recording started. Inherent to the design; worth documenting rather than
  fixing.
- The `input` group only takes effect at next login. `vox2txt setup` warns, but
  people will still miss it.
- A `config.toml` in the working directory shadows the user config. Intentional
  for development, confusing if you run `vox2txt` from a checkout by accident.
- `av` (102 MB) and `onnxruntime` (53 MB) are hard dependencies of
  faster-whisper. We decode no files and only `onnxruntime` is genuinely used
  (for VAD), but neither can be dropped without vendoring.

## Unrelated, but found on the dev machine

`/etc/udev/rules.d/51-android.rules` is malformed: a missing line-continuation
backslash turns its second line into an unconditional rule, so **236 of 254**
character devices end up mode `0666` — including `/dev/input/event*`,
`/dev/video0`, `/dev/snd/*` and `/dev/sda`. This is why hotkey capture works on
that machine without an active `input` group membership. Fixing it (put the
rule on one line) will break the hotkey until the next login. Not a vox2txt
bug, but it invalidates any permission testing done on that machine.
