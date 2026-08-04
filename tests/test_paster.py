import io
import sys
import types
import unittest
from unittest import mock

from vox2txt.paster import _VirtualKeyboard


class FailingUI:
    def __init__(self):
        self.closed = False

    def write(self, *_args):
        raise OSError("device disappeared")

    def syn(self):
        pass

    def close(self):
        self.closed = True


class VirtualKeyboardTests(unittest.TestCase):
    def test_write_failure_is_sticky_and_closes_device(self):
        fake_evdev = types.SimpleNamespace(
            ecodes=types.SimpleNamespace(EV_KEY=1),
        )
        keyboard = _VirtualKeyboard()
        ui = FailingUI()
        keyboard._ui = ui

        with mock.patch.dict(sys.modules, {"evdev": fake_evdev}), \
                mock.patch("sys.stdout", io.StringIO()):
            self.assertFalse(keyboard.tap(10, modifiers=[20]))

        self.assertTrue(keyboard._failed)
        self.assertIsNone(keyboard._ui)
        self.assertTrue(ui.closed)


if __name__ == "__main__":
    unittest.main()
