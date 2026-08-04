import io
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from vox2txt import config, setup_cmd


VALID_CONFIG = {
    "hotkey": {"key": "scroll_lock"},
    "paste": {"mode": "auto"},
}


class FakeDevice:
    name = "test keyboard"

    def capabilities(self):
        return {1: [70]}


class DoctorTests(unittest.TestCase):
    def sounddevice(self):
        return types.SimpleNamespace(
            query_devices=lambda: [{"max_input_channels": 1}],
        )

    def test_wayland_checks_the_configured_hotkey(self):
        fake_evdev = types.SimpleNamespace(
            ecodes=types.SimpleNamespace(
                EV_KEY=1,
                KEY_RIGHTALT=100,
                KEY_RIGHTCTRL=101,
                KEY_SCROLLLOCK=70,
            ),
            list_devices=lambda: ["/dev/input/fake"],
            InputDevice=lambda _path: FakeDevice(),
        )
        output = io.StringIO()
        with mock.patch.object(setup_cmd.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True), \
                mock.patch.dict(sys.modules, {
                    "sounddevice": self.sounddevice(),
                    "evdev": fake_evdev,
                }), \
                mock.patch.object(config, "effective_config_path", return_value=Path("/tmp/config.toml")), \
                mock.patch.object(config, "load", return_value=VALID_CONFIG), \
                mock.patch.object(setup_cmd.os, "access", return_value=True), \
                mock.patch.object(setup_cmd.shutil, "which", return_value="/usr/bin/tool"), \
                mock.patch("sys.stdout", output):
            result = setup_cmd.run_doctor()

        self.assertEqual(result, 0)
        self.assertIn("configured keyboard key readable via evdev (1 found)", output.getvalue())

    def test_x11_checks_pynput_xdotool_and_clipboard_not_evdev(self):
        output = io.StringIO()

        def which(name):
            return f"/usr/bin/{name}" if name in ("xdotool", "xclip") else None

        with mock.patch.object(setup_cmd.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.dict(sys.modules, {
                    "sounddevice": self.sounddevice(),
                    "pynput": types.SimpleNamespace(),
                }), \
                mock.patch.object(config, "effective_config_path", return_value=Path("/tmp/config.toml")), \
                mock.patch.object(config, "load", return_value=VALID_CONFIG), \
                mock.patch.object(setup_cmd.os, "access", return_value=False), \
                mock.patch.object(setup_cmd.shutil, "which", side_effect=which), \
                mock.patch("sys.stdout", output):
            result = setup_cmd.run_doctor()

        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("pynput available for the global hotkey", text)
        self.assertIn("paste injection available", text)
        self.assertNotIn("evdev", text)


class SetupTests(unittest.TestCase):
    def test_x11_setup_does_not_request_kernel_input_permissions(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(setup_cmd.shutil, "which", return_value="/tmp/vox2txt"), \
                mock.patch.object(setup_cmd, "_root_steps") as root_steps, \
                mock.patch.object(setup_cmd, "_has_systemd", return_value=False), \
                mock.patch.object(config, "write_default_config", return_value=Path("/tmp/config.toml")), \
                mock.patch("sys.stdout", output):
            result = setup_cmd._setup_linux()

        self.assertEqual(result, 0)
        root_steps.assert_not_called()
        self.assertIn("X11 needs no kernel input permissions", output.getvalue())

    def test_declining_optional_autostart_still_finishes_setup(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(setup_cmd.shutil, "which", return_value="/tmp/vox2txt"), \
                mock.patch.object(setup_cmd, "_root_steps") as root_steps, \
                mock.patch.object(setup_cmd, "_has_systemd", return_value=True), \
                mock.patch.object(setup_cmd, "_confirm", return_value=False), \
                mock.patch.object(config, "write_default_config", return_value=Path("/tmp/config.toml")), \
                mock.patch("sys.stdout", output):
            result = setup_cmd._setup_linux()

        self.assertEqual(result, 0)
        root_steps.assert_not_called()
        self.assertIn("Autostart is optional", output.getvalue())
        self.assertIn("\nDone.", output.getvalue())
        self.assertNotIn("Setup did not finish", output.getvalue())

    def test_wayland_does_not_start_service_before_group_is_active(self):
        output = io.StringIO()
        root_action = mock.Mock(return_value=True)
        root_steps = [("add input permission", "sudo usermod test", root_action)]
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True), \
                mock.patch.object(setup_cmd.shutil, "which", return_value="/tmp/vox2txt"), \
                mock.patch.object(setup_cmd, "_root_steps", return_value=root_steps), \
                mock.patch.object(setup_cmd, "_has_logind", return_value=True), \
                mock.patch.object(setup_cmd, "_has_systemd", return_value=True), \
                mock.patch.object(setup_cmd, "_input_group_member", return_value=True), \
                mock.patch.object(setup_cmd, "_input_group_active", return_value=False), \
                mock.patch.object(setup_cmd, "_confirm", side_effect=[True, False]), \
                mock.patch.object(config, "write_default_config", return_value=Path("/tmp/config.toml")), \
                mock.patch("sys.stdout", output):
            result = setup_cmd._setup_linux()

        self.assertEqual(result, 0)
        root_action.assert_called_once_with()
        text = output.getvalue()
        self.assertIn("systemctl --user enable vox2txt.service", text)
        self.assertNotIn("systemctl --user enable --now vox2txt.service", text)
        self.assertIn("will start next login", text)


if __name__ == "__main__":
    unittest.main()
