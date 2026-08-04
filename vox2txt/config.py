import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_DEFAULTS = {
    "hotkey": {"key": "alt_gr"},
    "transcription": {
        "model": "base",
        "language": "auto",
        "device": "auto",
        "compute_type": "auto",
        "vad_filter": True,
    },
    "paste": {"mode": "auto", "notify": True, "shortcut": "ctrl+v"},
}

DEFAULT_CONFIG_TOML = """\
[hotkey]
# Key to hold for push-to-talk. Supported: "alt_gr", "right_ctrl", "scroll_lock"
key = "alt_gr"

[transcription]
# Whisper model size: tiny, base, small, medium, large
# Larger = more accurate but slower and heavier
model = "base"

# Language hint for faster transcription. "auto" to detect automatically.
# Examples: "es", "en", "fr"
language = "auto"

# "auto" picks CUDA when available and falls back to CPU.
# Force it with "cpu" or "cuda" if you need to.
device = "auto"

# "auto" means int8 on CPU, float16 on CUDA.
compute_type = "auto"

# Trim silence before transcribing. Stops Whisper inventing text for
# near-empty clips, which push-to-talk produces a lot of.
vad_filter = true

[paste]
# "auto"           = transcribe -> clipboard -> press the shortcut below
# "clipboard_only" = transcribe -> clipboard only (no key simulation)
mode = "auto"

# Which key combination pastes. There is no single right answer: terminals and
# GUI apps disagree, and they do not overlap.
#
#   "ctrl+v"        pastes in GUI apps (browsers, editors, chat).
#                   In a terminal it does nothing useful -- readline treats it
#                   as quoted-insert and you see a literal ^V.
#   "ctrl+shift+v"  pastes in terminals. Does nothing in a plain GTK entry.
#
# Pick whichever matches where you dictate most. If you split your time, some
# terminals let you rebind paste to Ctrl+V, which lets you keep "ctrl+v" here.
shortcut = "ctrl+v"

# Show desktop notification after each transcription
notify = true
"""


def config_path() -> Path:
    """Where the user's config lives, per-platform."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "vox2txt" / "config.toml"


def effective_config_path() -> Path:
    """Config file load() will read, including the development override."""
    local = Path.cwd() / "config.toml"
    return local if local.exists() else config_path()


def write_default_config(path: Path | None = None) -> Path:
    """Create the config file if it is not there yet. Returns its path."""
    path = path or config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return path


def load(path: Path | None = None) -> dict:
    if path is None:
        # A config.toml in the working directory wins, so the repo stays
        # runnable from a checkout without touching the user's real config.
        path = effective_config_path()

    cfg = {k: dict(v) for k, v in _DEFAULTS.items()}

    if path.exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)
        for section, values in user.items():
            cfg.setdefault(section, {}).update(values)

    return cfg
