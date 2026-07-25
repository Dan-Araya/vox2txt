import numpy as np

try:
    import sounddevice as sd
except OSError:
    raise SystemExit(
        "PortAudio library not found (required by sounddevice). Install it with:\n"
        "  Fedora:  sudo dnf install portaudio\n"
        "  Ubuntu:  sudo apt install libportaudio2\n"
        "  macOS:   brew install portaudio\n"
        "  Windows: PortAudio is normally bundled with sounddevice — try reinstalling:\n"
        "           pip install --force-reinstall sounddevice"
    )

_SAMPLE_RATE = 16000  # Whisper expects 16 kHz


class Recorder:
    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def start(self):
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype="float32")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(self._chunks).flatten()

    def _callback(self, indata, frames, time, status):
        self._chunks.append(indata.copy())
