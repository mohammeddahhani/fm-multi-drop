import dataclasses
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import helpers  # noqa: E402
from fm_multi_drop import cave_data, patch as P  # noqa: E402
from fm_multi_drop.disc import DiscError, RawDisc  # noqa: E402
from fm_multi_drop.sector import (check_sector, compute_ecc, fill_edc_ecc, is_form1_mode2)  # noqa: E402


class SectorTests(unittest.TestCase):
    def test_fill_then_check(self):
        s = bytearray(helpers.sector(5, b"hello"))
        self.assertEqual(check_sector(bytes(s)), (True, True))
        s[100] ^= 1
        self.assertEqual(check_sector(bytes(s)), (False, False))

    def test_ecc_detects_ecc_damage_only(self):
        s = bytearray(helpers.sector(5, b"hello"))
        s[2300] ^= 0x55
        self.assertEqual(check_sector(bytes(s)), (True, False))

    def test_ecc_ignores_header_address(self):
        s = bytearray(helpers.sector(5, b"hello"))
        before = compute_ecc(bytes(s))
        s[12:15] = b"\x99\x99\x99"
        self.assertEqual(compute_ecc(bytes(s)), before)

    def test_form_detection(self):
        self.assertTrue(is_form1_mode2(helpers.sector(1)))
        self.assertFalse(is_form1_mode2(helpers.sector(1, submode=0x20)))


class DiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.slus = helpers.make_slus()
        cls.path = os.path.join(cls.tmp, "disc.bin")
        helpers.build_disc(cls.path, cls.slus)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_find_files(self):
        with RawDisc(self.path) as d:
            self.assertEqual(d.find_file("SLUS_014.11"), (helpers.SLUS_LBA, len(self.slus)))
            self.assertEqual(d.find_file("slus_014.11"), (helpers.SLUS_LBA, len(self.slus)))
            self.assertEqual(d.find_file("DATA/FILE.BIN"), (60, 10))
            self.assertIsNone(d.find_file("NOPE.BIN"))
            self.assertIsNone(d.find_file("SLUS_014.11/x"))

    def test_rejects_bad_sizes(self):
        bad = os.path.join(self.tmp, "bad.iso")
        helpers.write_file(bad, b"x" * 1000)
        with self.assertRaises(DiscError):
            RawDisc(bad)
        helpers.write_file(bad, b"x" * 2048 * 4)
        with self.assertRaisesRegex(DiscError, "2048-byte"):
            RawDisc(bad)

    def test_rejects_non_disc_with_valid_size(self):
        bad = os.path.join(self.tmp, "zeros.bin")
        helpers.write_file(bad, bytes(2352 * 40))
        with RawDisc(bad) as d, self.assertRaises(DiscError):
            d.find_file("SLUS_014.11")

    def test_overwrite_touches_only_changed_sectors(self):
        work = os.path.join(self.tmp, "work.bin")
        shutil.copy(self.path, work)
        new = bytearray(self.slus)
        new[5000] ^= 0xFF
        new[1_000_000] ^= 0xFF
        with RawDisc(work, writable=True) as d:
            modified = d.overwrite_file_data(helpers.SLUS_LBA, bytes(new))
        self.assertEqual(modified, [helpers.SLUS_LBA + 2, helpers.SLUS_LBA + 488])
        self.assertEqual(helpers.differing_sectors(self.path, work), set(modified))
        with RawDisc(work) as d:
            for lba in modified:
                self.assertEqual(check_sector(d.read_sector(lba)), (True, True))
            self.assertEqual(d.read_data(helpers.SLUS_LBA, 929)[:len(new)], bytes(new))

    def test_refuses_non_form1_sector(self):
        work = os.path.join(self.tmp, "form2.bin")
        shutil.copy(self.path, work)
        with open(work, "r+b") as f:
            f.seek(helpers.SLUS_LBA * 2352)
            f.write(helpers.sector(helpers.SLUS_LBA, b"", submode=0x20))
        with RawDisc(work, writable=True) as d, self.assertRaises(DiscError):
            d.overwrite_file_data(helpers.SLUS_LBA, b"\x01" * 2048)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.slus = helpers.make_slus()
        self.spec = helpers.spec_for(self.slus)

    def test_vanilla_detected(self):
        i = P.inspect(self.slus, self.spec)
        self.assertEqual(i.state, P.State.VANILLA)

    def test_apply_roundtrip(self):
        patched = P.apply(self.slus, 10, self.spec)
        i = P.inspect(patched, self.spec)
        self.assertEqual((i.state, i.drops), (P.State.PATCHED, 10))
        self.assertEqual(P.revert(patched, self.spec), self.slus)

    def test_only_hook_and_cave_change(self):
        patched = P.apply(self.slus, 3, self.spec)
        diff = [i for i in range(len(self.slus)) if self.slus[i] != patched[i]]
        ho, co = self.spec.offset(self.spec.hook_addr), self.spec.offset(self.spec.cave_addr)
        self.assertTrue(all(ho <= i < ho + 4 or co <= i < co + len(self.spec.cave) for i in diff))
        self.assertEqual(patched[co], 3)

    def test_repatch_changes_count(self):
        again = P.apply(P.apply(self.slus, 3, self.spec), 8, self.spec)
        self.assertEqual(again, P.apply(self.slus, 8, self.spec))

    def test_drop_range(self):
        for bad in (0, 256, -1):
            with self.assertRaises(P.PatchError):
                P.apply(self.slus, bad, self.spec)
        for good in (1, 255):
            P.apply(self.slus, good, self.spec)

    def test_foreign_executables_rejected(self):
        tampered = bytearray(self.slus)
        tampered[123456] ^= 1
        self.assertEqual(P.inspect(bytes(tampered), self.spec).state, P.State.FOREIGN)
        junk = bytearray(self.slus)
        junk[self.spec.offset(self.spec.cave_addr) + 300] = 7
        self.assertEqual(P.inspect(bytes(junk), self.spec).state, P.State.FOREIGN)
        patched = bytearray(P.apply(self.slus, 4, self.spec))
        patched[99999] ^= 1
        self.assertEqual(P.inspect(bytes(patched), self.spec).state, P.State.FOREIGN)
        self.assertEqual(P.inspect(self.slus[:-1], self.spec).state, P.State.FOREIGN)
        with self.assertRaises(P.PatchError):
            P.apply(bytes(tampered), 5, self.spec)

    def test_default_hook_encoding(self):
        self.assertEqual(P.DEFAULT.hook_patched, bytes.fromhex("0f6c0708"))  # j 0x801db03c


class CaveDataTests(unittest.TestCase):
    def test_checksum_and_size(self):
        self.assertEqual(hashlib.sha256(cave_data.CAVE).hexdigest(), cave_data.CAVE_SHA256)
        self.assertLessEqual(len(cave_data.CAVE), P.DEFAULT.cave_region_size)
        self.assertEqual(cave_data.CAVE[0], 0)

    @unittest.skipUnless(shutil.which("mips-linux-gnu-as"), "MIPS binutils not installed")
    def test_matches_assembly_source(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(root, "tools"))
        import build_cave
        self.assertEqual(build_cave.assemble(), cave_data.CAVE)


if __name__ == "__main__":
    unittest.main()
