import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    raise SystemExit(
        "faster-whisper is not installed. Run:\n"
        "  pip install faster-whisper"
    )

# faster-whisper wants an explicit revision for the big model.
_MODEL_ALIASES = {"large": "large-v3"}


def _pick_backend(device: str, compute_type: str):
    """Resolve 'auto' to something CTranslate2 will actually accept."""
    if device != "auto":
        return device, (compute_type if compute_type != "auto" else "default")

    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", (compute_type if compute_type != "auto" else "float16")
    except Exception:
        pass
    # int8 is several times faster than float32 on CPU and the quality loss is
    # not audible at these model sizes.
    return "cpu", (compute_type if compute_type != "auto" else "int8")


class Transcriber:
    def __init__(
        self,
        model_name: str = "base",
        language: str = "auto",
        device: str = "auto",
        compute_type: str = "auto",
        vad_filter: bool = True,
    ):
        model_name = _MODEL_ALIASES.get(model_name, model_name)
        device, compute_type = _pick_backend(device, compute_type)

        print(f"Loading Whisper model '{model_name}' ({device}/{compute_type})...")
        print("First run downloads the model; this can take a minute.")
        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self._language = None if language == "auto" else language
        self._vad_filter = vad_filter
        print("Model ready.")

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""

        # CTranslate2 needs contiguous float32 mono at 16 kHz, which is what
        # Recorder already produces.
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            # Push-to-talk clips often start or end on silence, and Whisper is
            # prone to inventing text for those. VAD trims them first.
            vad_filter=self._vad_filter,
            # Each clip is independent, so carrying context between them only
            # invites repetition loops.
            condition_on_previous_text=False,
        )
        # transcribe() is lazy: nothing runs until the generator is consumed.
        return "".join(segment.text for segment in segments).strip()
