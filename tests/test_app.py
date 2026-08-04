import io
import unittest
from unittest import mock

import numpy as np

from vox2txt import app


CONFIG = {
    "hotkey": {"key": "scroll_lock"},
    "transcription": {
        "model": "base",
        "language": "auto",
        "device": "auto",
        "compute_type": "auto",
        "vad_filter": True,
    },
    "paste": {"mode": "auto", "notify": False, "shortcut": "ctrl+v"},
}


class DummyRecorder:
    def start(self):
        pass

    def stop(self):
        return np.zeros(16, dtype=np.float32)


class DummyTranscriber:
    def __init__(self, **_kwargs):
        pass

    def transcribe(self, _audio):
        return "hello"


class AppRecoveryTests(unittest.TestCase):
    def common_patches(self):
        return (
            mock.patch.object(app.cfg_module, "load", return_value=CONFIG),
            mock.patch.object(app, "Recorder", DummyRecorder),
            mock.patch.object(app, "Transcriber", DummyTranscriber),
            mock.patch.object(app.paster, "validate_shortcut"),
            mock.patch.object(app.paster, "warm_up"),
            mock.patch.object(app.paster, "paste"),
            mock.patch.object(app.signal, "signal"),
        )

    def test_lost_hotkey_returns_failure_for_supervisor(self):
        patches = self.common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                mock.patch.object(app.paster, "virtual_keyboard_failed", return_value=False), \
                mock.patch.object(
                    app.hotkey,
                    "start",
                    side_effect=lambda _key, _press, _release, on_lost: on_lost("gone"),
                ), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(app.run(), 1)

    def test_lost_virtual_keyboard_returns_failure_for_supervisor(self):
        def exercise_one_recording(_key, on_press, on_release, on_lost=None):
            on_press()
            on_release()

        patches = self.common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                mock.patch.object(
                    app.paster,
                    "virtual_keyboard_failed",
                    side_effect=[False, True],
                ), \
                mock.patch.object(app.hotkey, "start", side_effect=exercise_one_recording), \
                mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(app.run(), 1)


if __name__ == "__main__":
    unittest.main()
