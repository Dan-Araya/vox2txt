import signal
import threading
import traceback

from . import config as cfg_module
from . import hotkey, paster
from .recorder import Recorder
from .transcriber import Transcriber

_IDLE = "idle"
_RECORDING = "recording"
_TRANSCRIBING = "transcribing"

# One bad transcription is bad luck; three in a row suggests the model or the
# device is in a state a fresh process would clear.
_MAX_CONSECUTIVE_FAILURES = 3


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

    # Anything that leaves the process alive but useless has to be turned into a
    # non-zero exit, otherwise the supervisor (systemd on Linux, the launcher on
    # Windows) has nothing to react to. Only failures a restart can actually
    # clear go through here.
    stop_event = threading.Event()
    fatal_reason: str | None = None
    fatal_lock = threading.Lock()
    consecutive_failures = 0

    def die(reason: str) -> None:
        nonlocal fatal_reason
        with fatal_lock:
            if fatal_reason is None:  # the first cause is the interesting one
                fatal_reason = reason
        stop_event.set()

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
            nonlocal state, consecutive_failures
            try:
                text = transcriber.transcribe(audio)
                if text:
                    paster.paste(text, mode=paste_mode, notify=notify,
                                 shortcut=paste_shortcut)
                    # The uinput device is created once and the failure flag is
                    # sticky, so from here on every paste would silently degrade
                    # to clipboard-only. A restart recreates it.
                    if (paste_mode != "clipboard_only"
                            and not keyboard_failed_at_start
                            and paster.virtual_keyboard_failed()):
                        die("virtual keyboard lost")
                elif notify:
                    paster.notify("vox2txt", "No speech detected")
                consecutive_failures = 0
            except Exception as exc:
                # This runs in a worker thread: an escaping exception would only
                # print a traceback and kill the thread, leaving the process
                # looking healthy. Report it and count it instead.
                consecutive_failures += 1
                print(f"[vox2txt] Transcription failed "
                      f"({consecutive_failures}/{_MAX_CONSECUTIVE_FAILURES}): {exc}")
                traceback.print_exc()
                if notify:
                    detail = str(exc).strip() or exc.__class__.__name__
                    paster.notify("vox2txt — failed", detail.splitlines()[0])
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    die(f"transcription failed {consecutive_failures} times in a row")
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

    # If uinput was already unavailable at startup, restarting will not conjure
    # it up — better to stay running and degrade to clipboard-only than to
    # restart-loop. Only *losing* it while running is worth dying over.
    keyboard_failed_at_start = paster.virtual_keyboard_failed()

    key = cfg["hotkey"]["key"]
    try:
        hotkey.start(key, on_press, on_release, on_lost=die)
    except (RuntimeError, ValueError) as exc:
        print(f"[vox2txt] {exc}")
        return 1

    print(f"vox2txt ready — hold [{key}] to record, release to transcribe.")
    if paste_mode != "clipboard_only":
        print(f"Pasting with [{paste_shortcut}].")
    print("Press Ctrl+C to exit.\n")

    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    stop_event.wait()

    if fatal_reason:
        print(f"\n[vox2txt] Fatal: {fatal_reason}")
        print("[vox2txt] Exiting so the supervisor can restart us.")
        return 1
    print("\nBye.")
    return 0
