import os
import tempfile
import unittest
from pathlib import Path

from stock_strategy.restricted_runtime import restricted_audit


class RestrictedRuntimeTest(unittest.TestCase):
    def test_network_and_process_creation_are_blocked(self):
        for event in ("socket.connect", "subprocess.Popen", "ctypes.dlopen"):
            with self.subTest(event=event):
                with self.assertRaises(PermissionError):
                    restricted_audit(event, (), ())

    def test_writes_are_limited_to_declared_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            allowed = Path(directory, "output").resolve()
            allowed.mkdir()

            restricted_audit("open", (allowed / "summary.json", "w", 0), (allowed,))
            restricted_audit(
                "open",
                (allowed / "summary.json", os.O_CREAT | os.O_WRONLY, 0),
                (allowed,),
            )
            with self.assertRaises(PermissionError):
                restricted_audit(
                    "open",
                    (Path(directory, "outside.txt"), "w", 0),
                    (allowed,),
                )


if __name__ == "__main__":
    unittest.main()
