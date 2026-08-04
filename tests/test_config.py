import os
import tempfile
import unittest
from pathlib import Path

from vox2txt import config


class ConfigTests(unittest.TestCase):
    def test_default_config_round_trips(self):
        parsed = config.tomllib.loads(config.DEFAULT_CONFIG_TOML)
        self.assertEqual(parsed["hotkey"]["key"], "alt_gr")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            self.assertEqual(config.write_default_config(path), path)
            loaded = config.load(path)

        self.assertEqual(loaded["hotkey"]["key"], "alt_gr")
        self.assertEqual(loaded["paste"]["mode"], "auto")

    def test_local_config_is_the_effective_override(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                local = Path(directory) / "config.toml"
                local.write_text('[hotkey]\nkey = "right_ctrl"\n', encoding="utf-8")
                self.assertEqual(config.effective_config_path(), local)
                self.assertEqual(config.load()["hotkey"]["key"], "right_ctrl")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
