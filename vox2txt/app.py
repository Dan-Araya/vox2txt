import signal
import subprocess
import threading

from . import config as cfg_module
from . import hotkey, paster
from .recorder import Recorder
from .transcriber import Transcriber

_IDLE = "idle"
_RECORDING = "recording"
_TRANSCRIBING = "transcribing"


def run() -> int:
    cfg = cfg_module.load()
    tcfg = cfg["transcription"]

    transcriber = Transcriber(
        model_name=tcfg["model"],
        language=tcfg["language"],
        device=tcfg.get("device", "auto"),
        compute_type=tcfg.get("compute_type", "auto"),
        vad_filter=tcfg.get("vad_filter", True),
    )
    recorder = Recorder()
    state = _IDLE
    state_lock = threading.Lock()

    paste_mode = cfg["paste"]["mode"]
    notify = cfg["paste"]["notify"]
    paste_shortcut = cfg["paste"].get("shortcut", paster.DEFAULT_SHORTCUT)

    def on_press():
        nonlocal state
        with state_lock:
            if state != _IDLE:
                return
            state = _RECORDING
        recorder.start()

    def on_release():
        nonlocal state
        with state_lock:
            if state != _RECORDING:
                return
            state = _TRANSCRIBING
        audio = recorder.stop()

        def _work():
            nonlocal state
            try:
                text = transcriber.transcribe(audio)
                if text:
                    paster.paste(text, mode=paste_mode, notify=notify,
                                 shortcut=paste_shortcut)
                elif notify:
                    try:
                        subprocess.run(
                            ["notify-send", "-a", "vox2txt", "vox2txt", "No speech detected"],
                            check=False,
                        )
                    except FileNotFoundError:
                        print("[vox2txt] No speech detected")
            finally:
                # Without this a failed transcription would wedge the state
                # machine and the hotkey would go dead.
                with state_lock:
                    state = _IDLE

        threading.Thread(target=_work, daemon=True).start()

    # Create the virtual keyboard now: the compositor needs a moment to notice
    # a new input device, and that wait should not land on the first paste.
    if paste_mode != "clipboard_only":
        try:
            # Fail here on a typo, rather than silently at the first paste.
            paster.validate_shortcut(paste_shortcut)
        except ValueError as exc:
            print(f"[vox2txt] Bad paste.shortcut in config: {exc}")
            return 1
        paster.warm_up()

    key = cfg["hotkey"]["key"]
    try:
        hotkey.start(key, on_press, on_release)
    except RuntimeError as exc:
        print(f"[vox2txt] {exc}")
        return 1

    print(f"vox2txt ready — hold [{key}] to record, release to transcribe.")
    if paste_mode != "clipboard_only":
        print(f"Pasting with [{paste_shortcut}].")
    print("Press Ctrl+C to exit.\n")

    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    stop_event.wait()
    print("\nBye.")
    return 0
