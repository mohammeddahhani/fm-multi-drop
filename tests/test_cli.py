import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import helpers  # noqa: E402
from fm_multi_drop import cli, patch as P  # noqa: E402
from fm_multi_drop.disc import RawDisc  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.slus = helpers.make_slus()
        cls.spec = helpers.spec_for(cls.slus)
        cls.disc = os.path.join(cls.tmp, "game.iso")
        helpers.build_disc(cls.disc, cls.slus)
        cls.digest = hashlib.sha256(helpers.read_file(cls.disc)).hexdigest()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def setUp(self):
        p = mock.patch.object(P, "DEFAULT", self.spec)
        p.start()
        self.addCleanup(p.stop)

    def out(self, name):
        return os.path.join(self.tmp, name)

    def test_check(self):
        code, o, _ = run("--check", self.disc)
        self.assertEqual(code, 0)
        self.assertIn("can be patched", o)

    def test_patch_and_repatch(self):
        first = self.out("a.iso")
        code, o, e = run(self.disc, "-n", 4, "-o", first)
        self.assertEqual(code, 0, e)
        self.assertEqual(hashlib.sha256(helpers.read_file(self.disc)).hexdigest(), self.digest)  # input untouched
        self.assertEqual(helpers.differing_sectors(self.disc, first), {61, 944})
        with RawDisc(first) as d:
            _, slus = cli.read_slus(d)
        info = P.inspect(slus, self.spec)
        self.assertEqual((info.state, info.drops), (P.State.PATCHED, 4))
        second = self.out("b.iso")
        code, o, e = run(first, "-n", 9, "-o", second)
        self.assertEqual(code, 0, e)
        self.assertEqual(helpers.differing_sectors(first, second), {944})
        self.assertFalse(os.path.exists(second + ".partial"))

    def test_default_output_name(self):
        self.assertEqual(cli.default_output("/x/Game.iso", 10), "/x/Game.10drops.iso")
        self.assertEqual(cli.default_output("/x/Game.10drops.iso", 5), "/x/Game.5drops.iso")
        self.assertEqual(cli.default_output("/x/Game.bin", 2), "/x/Game.2drops.bin")

    def test_no_silent_overwrite(self):
        target = self.out("exists.iso")
        helpers.write_file(target, b"keep")
        code, _, e = run(self.disc, "-n", 2, "-o", target)
        self.assertEqual(code, 1)
        self.assertIn("already exists", e)
        self.assertEqual(helpers.read_file(target), b"keep")
        code, _, _ = run(self.disc, "-n", 2, "-o", target, "--force")
        self.assertEqual(code, 0)

    def test_refuses_input_as_output(self):
        code, _, e = run(self.disc, "-n", 2, "-o", self.disc, "--force")
        self.assertEqual(code, 1)
        self.assertIn("different file", e)

    def test_bad_arguments(self):
        self.assertEqual(run(self.disc, "-n", 0)[0], 2)
        self.assertEqual(run(self.disc, "-n", 256)[0], 2)
        self.assertEqual(run(self.disc)[0], 2)
        self.assertEqual(run("-n", 3)[0], 2)
        code, _, e = run(self.out("missing.iso"), "-n", 3)
        self.assertEqual(code, 1)
        self.assertIn("not found", e)

    def test_unsupported_executable_creates_nothing(self):
        modded = bytearray(self.slus)
        modded[4321] ^= 1
        bad = self.out("modded.iso")
        helpers.build_disc(bad, bytes(modded))
        target = self.out("never.iso")
        code, _, e = run(bad, "-n", 3, "-o", target)
        self.assertEqual(code, 1)
        self.assertIn("not supported", e)
        self.assertFalse(os.path.exists(target) or os.path.exists(target + ".partial"))

    def test_self_test(self):
        code, o, _ = run("--self-test")
        self.assertEqual(code, 0)
        self.assertIn("self-test ok", o)


if __name__ == "__main__":
    unittest.main()
