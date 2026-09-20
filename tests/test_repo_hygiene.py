import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("check_no_game_files", os.path.join(ROOT, "tools", "check_no_game_files.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class HygieneTests(unittest.TestCase):
    def test_repository_is_clean(self):
        self.assertEqual(guard.scan(guard.candidates()), [])

    def test_scanner_catches_game_data(self):
        with tempfile.TemporaryDirectory() as d:
            files = {"disc.iso": b"x", "blob.dat": b"PS-X EXE" + bytes(100),
                     "sect.dat": b"\x00" + b"\xff" * 10 + b"\x00" + bytes(50),
                     "SLUS_014.11": b"\x01\x02", "huge.dat": bytes(1_100_000), "ok.py": b"print(1)\n"}
            for name, data in files.items():
                with open(os.path.join(d, name), "wb") as f:
                    f.write(data)
            found = " ".join(guard.scan(sorted(files), root=d))
            for name in ("disc.iso", "blob.dat", "sect.dat", "SLUS_014.11", "huge.dat"):
                self.assertIn(name, found)
            self.assertNotIn("ok.py", found)


if __name__ == "__main__":
    unittest.main()
